"""Backend'ы аутентификации портала."""

import logging
import ssl

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from ldap3 import NONE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from accounts.models import normalize_ad_login

logger = logging.getLogger(__name__)


class PortalBackend(ModelBackend):
    """Проверяет логин и пароль учётной записи портала.

    Форма входа передаёт в ``authenticate()`` дополнительный
    аргумент ``auth_source`` — режим входа, выбранный пользователем
    на странице входа.

    Сейчас поддерживается только режим ``local`` (учётная запись,
    созданная администратором портала). Режим ``ad`` будет
    обслуживать отдельный backend для Active Directory.
    """

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs,
    ):
        """Проверяет учётные данные, возвращает пользователя или None."""
        # Модель берём лениво, чтобы модуль можно было импортировать
        # до полной инициализации реестра приложений Django.
        user_model = get_user_model()
        auth_source = kwargs.get(
            'auth_source',
            user_model.AuthSource.LOCAL,
        )
        if auth_source != user_model.AuthSource.LOCAL:
            # Вход через Active Directory пока не реализован.
            return None
        # Дальше работает стандартная проверка пароля Django
        # (хеширование, is_active и т.п.).
        return super().authenticate(
            request,
            username=username,
            password=password,
            **kwargs,
        )


class ADBackend(ModelBackend):
    """Аутентификация по учётной записи Active Directory.

    Пароль проверяется в домене по LDAP поверх TLS и в Django
    не сохраняется. При первом успешном входе создаётся учётная
    запись портала (JIT) с членством в группе по умолчанию; связь
    с доменным логином хранится в ``User.ad_login``, поэтому
    внутренний логин портала может отличаться от доменного.
    """

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs,
    ):
        """Проверяет доменные учётные данные и возвращает пользователя."""
        # Backend обслуживает только режим «Active Directory»,
        # выбранный пользователем на странице входа.
        if kwargs.get('auth_source') != 'ad':
            return None
        if not settings.AD_ENABLED or not username or not password:
            return None

        ad_login = normalize_ad_login(username)
        entry = self._fetch_entry(ad_login, password)
        if entry is None:
            return None

        if not self._is_group_allowed(entry['groups']):
            logger.info(
                'AD: %s не входит в доменную группу %s',
                ad_login,
                settings.AD_REQUIRED_GROUP,
            )
            return None

        user = self._resolve_user(ad_login, entry)

        # Блокировка на портале важнее статуса в домене:
        # отключённого администратором сотрудника не пускаем.
        if not user.is_active:
            logger.info(
                'AD: учётная запись портала %s отключена',
                user.username,
            )
            return None
        return user

    def _validate_uri(self):
        """Запрещает работу без шифрования канала.

        Пароль доменной учётной записи нельзя передавать открытым
        текстом, поэтому разрешены только ``ldaps://`` и
        ``ldap://`` вместе с StartTLS.
        """
        uri = settings.AD_SERVER_URI.strip().lower()
        if uri.startswith('ldaps://'):
            return
        if uri.startswith('ldap://') and settings.AD_USE_STARTTLS:
            return
        raise ImproperlyConfigured(
            'AD_SERVER_URI должен использовать ldaps:// либо '
            'ldap:// вместе с AD_USE_STARTTLS=True.',
        )

    def _build_tls(self):
        """Собирает TLS-настройку для подключения к каталогу."""
        if not settings.AD_TLS_VERIFY:
            # Только для изолированных стендов: канал шифруется,
            # но подлинность контроллера домена не проверяется.
            logger.warning(
                'AD: проверка TLS-сертификата отключена (AD_TLS_VERIFY=False).',
            )
            return Tls(validate=ssl.CERT_NONE)
        return Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.AD_CA_CERT_FILE or None,
        )

    def _connect(self, user, password):
        """Открывает соединение с каталогом и выполняет bind."""
        server = Server(
            settings.AD_SERVER_URI,
            use_ssl=settings.AD_SERVER_URI.strip()
            .lower()
            .startswith('ldaps://'),
            tls=self._build_tls(),
            get_info=NONE,
            connect_timeout=10,
        )
        connection = Connection(
            server,
            user=user or None,
            password=password or None,
            raise_exceptions=True,
            receive_timeout=10,
        )
        if settings.AD_USE_STARTTLS:
            # StartTLS выполняется до bind: иначе пароль уйдёт
            # по незашифрованному каналу.
            connection.open()
            connection.start_tls()
        connection.bind()
        return connection

    def _fetch_entry(self, ad_login, password):
        """Ищет учётную запись в домене и проверяет её пароль.

        Возвращает словарь с DN, атрибутами и списком групп либо
        ``None``, если сотрудник не найден или пароль неверен.
        """
        self._validate_uri()

        search_filter = (
            '(&(objectClass=user)'
            f'(sAMAccountName={escape_filter_chars(ad_login)}))'
        )
        # Запрашиваем только нужные атрибуты: memberOf для проверки
        # членства в группе и поля из AD_ATTR_MAP.
        attributes = [
            'memberOf',
            *sorted(set(settings.AD_ATTR_MAP.values())),
        ]

        try:
            with self._connect(
                settings.AD_BIND_DN,
                settings.AD_BIND_PASSWORD,
            ) as connection:
                connection.search(
                    search_base=settings.AD_USER_SEARCH_BASE,
                    search_filter=search_filter,
                    search_scope=SUBTREE,
                    attributes=attributes,
                )
                if not connection.entries:
                    logger.info(
                        'AD: учётная запись %s не найдена',
                        ad_login,
                    )
                    return None
                entry = connection.entries[0]
                user_dn = entry.entry_dn
                raw_attributes = dict(entry.entry_attributes_as_dict)

            # Пароль проверяем отдельным bind от имени сотрудника:
            # успешный bind и есть доказательство верного пароля.
            with self._connect(user_dn, password):
                pass
        except LDAPException as error:
            logger.info(
                'AD: ошибка аутентификации %s: %s',
                ad_login,
                error,
            )
            return None

        return {
            'dn': user_dn,
            'attributes': {
                name: str(values[0])
                for name, values in raw_attributes.items()
                if values
            },
            'groups': list(raw_attributes.get('memberOf', [])),
        }

    def _is_group_allowed(self, groups):
        """Проверяет членство в доменной группе допуска."""
        required = settings.AD_REQUIRED_GROUP.strip().lower()
        if not required:
            # Группа не задана: допускается любой сотрудник домена.
            return True
        prefix = f'cn={required},'
        return any(str(group).lower().startswith(prefix) for group in groups)

    def _resolve_user(self, ad_login, entry):
        """Находит или создаёт учётную запись портала для доменной."""
        user_model = get_user_model()
        attributes = self._mapped_attributes(entry['attributes'])

        # 1. Связь уже настроена: логины портала и домена могут
        #    различаться, поиск идёт по ad_login.
        user = user_model.objects.filter(ad_login=ad_login).first()
        if user is not None:
            self._sync_attributes(user, attributes)
            return user

        # 2. Доменная учётка заведена администратором вручную,
        #    логин совпадает с доменным, но связь ещё не указана.
        user = user_model.objects.filter(
            username__iexact=ad_login,
            auth_source=user_model.AuthSource.AD,
            ad_login__isnull=True,
        ).first()
        if user is not None:
            user.ad_login = ad_login
            changed = self._apply_attributes(user, attributes)
            user.save(update_fields=['ad_login', *changed])
            return user

        # 3. JIT-создание. Локальная учётка с тем же логином
        #    не переиспользуется: это разные учётные записи.
        user = user_model(
            username=self._free_username(ad_login),
            auth_source=user_model.AuthSource.AD,
            ad_login=ad_login,
        )
        user.set_unusable_password()
        self._apply_attributes(user, attributes)
        user.save()
        self._add_default_group(user)
        logger.info(
            'AD: создана учётная запись портала %s (доменный логин %s)',
            user.username,
            ad_login,
        )
        return user

    def _free_username(self, ad_login):
        """Подбирает свободный логин портала на основе доменного."""
        user_model = get_user_model()
        candidate = ad_login
        counter = 0
        while user_model.objects.filter(username__iexact=candidate).exists():
            counter += 1
            suffix = '_ad' if counter == 1 else f'_ad{counter}'
            candidate = f'{ad_login}{suffix}'
        return candidate

    def _mapped_attributes(self, raw_attributes):
        """Переводит атрибуты каталога в поля модели User."""
        attributes = {}
        for field, ad_attribute in settings.AD_ATTR_MAP.items():
            value = raw_attributes.get(ad_attribute)
            if value:
                attributes[field] = str(value).strip()
        return attributes

    def _apply_attributes(self, user, attributes):
        """Записывает атрибуты в поля пользователя без сохранения.

        Возвращает список изменённых полей, чтобы вызывающий код
        мог сохранить только их (``update_fields``).
        """
        changed = []
        for field, value in attributes.items():
            if not hasattr(user, field):
                continue
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        return changed

    def _sync_attributes(self, user, attributes):
        """Обновляет кадровые поля существующего пользователя."""
        if not settings.AD_SYNC_ATTRIBUTES:
            return
        changed = self._apply_attributes(user, attributes)
        if changed:
            user.save(update_fields=changed)

    def _add_default_group(self, user):
        """Добавляет JIT-пользователя в группу начальных прав."""
        group_name = (settings.AD_DEFAULT_GROUP or '').strip()
        if not group_name:
            return
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
