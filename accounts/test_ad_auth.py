"""Тесты входа через Active Directory.

LDAP полностью замокан: реальный контроллер домена для тестов
не нужен. Проверяется логика JIT-создания, связывания учётных
записей и ограничений доступа.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured

from accounts.backends import ADBackend
from accounts.checks import check_ad_tls
from accounts.models import User, normalize_ad_login

pytestmark = pytest.mark.django_db

DEFAULT_GROUP = 'Пользователи портала'


@pytest.fixture
def ad_settings(settings):
    """Настройки портала с включённым входом через AD."""
    settings.AD_ENABLED = True
    settings.AD_SERVER_URI = 'ldaps://dc1.example.local:636'
    settings.AD_USE_STARTTLS = False
    settings.AD_TLS_VERIFY = True
    settings.AD_REQUIRED_GROUP = 'GG-PORTAL-USERS'
    settings.AD_DEFAULT_GROUP = DEFAULT_GROUP
    settings.AD_SYNC_ATTRIBUTES = True
    settings.AD_ATTR_MAP = {
        'last_name': 'sn',
        'first_name': 'givenName',
        'middle_name': 'middleName',
        'email': 'mail',
        'position': 'title',
        'department': 'department',
    }
    return settings


def make_entry(**overrides):
    """Готовит ответ каталога для подменённого LDAP-запроса."""
    entry = {
        'dn': 'CN=Ivanov,OU=Users,DC=example,DC=local',
        'attributes': {
            'sn': 'Иванов',
            'givenName': 'Иван',
            'middleName': 'Иванович',
            'mail': 'ivanov@example.local',
            'title': 'Инженер по качеству',
            'department': 'ОКК',
        },
        'groups': [
            'CN=GG-PORTAL-USERS,OU=Groups,DC=example,DC=local',
        ],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def ldap(monkeypatch):
    """Подменяет обращение к каталогу и запоминает параметры."""
    state = {'entry': make_entry(), 'calls': []}

    def fake_fetch(self, ad_login, password):
        state['calls'].append((ad_login, password))
        return state['entry']

    monkeypatch.setattr(ADBackend, '_fetch_entry', fake_fetch)
    return state


def authenticate_ad(username, password='Passw0rd!'):
    """Вызывает backend так же, как это делает форма входа."""
    return ADBackend().authenticate(
        None,
        username=username,
        password=password,
        auth_source='ad',
    )


def test_normalize_ad_login():
    """Доменный логин приводится к нижнему регистру и без UPN."""
    assert normalize_ad_login('  IVANOV@example.local ') == 'ivanov'
    assert normalize_ad_login('') is None
    assert normalize_ad_login(None) is None


def test_jit_creates_user_with_default_group(ad_settings, ldap):
    """Первый вход создаёт учётную запись с группой по умолчанию."""
    user = authenticate_ad('IVANOV')

    assert user is not None
    user.refresh_from_db()
    assert user.username == 'ivanov'
    assert user.ad_login == 'ivanov'
    assert user.auth_source == User.AuthSource.AD
    assert user.has_usable_password() is False
    assert user.first_name == 'Иван'
    assert user.last_name == 'Иванов'
    assert user.department == 'ОКК'
    assert list(user.groups.values_list('name', flat=True)) == [DEFAULT_GROUP]


def test_second_login_reuses_user(ad_settings, ldap):
    """Повторный вход не создаёт вторую учётную запись."""
    first = authenticate_ad('ivanov')
    second = authenticate_ad('ivanov')

    assert first.pk == second.pk
    assert User.objects.count() == 1


def test_linked_user_logs_in_by_ad_login(ad_settings, ldap):
    """Связанная учётка входит, даже если логины различаются."""
    linked = User.objects.create_user(
        username='i.ivanov',
        password='local-pass-123',
        ad_login='ivanov',
    )

    user = authenticate_ad('IVANOV@example.local')

    assert user.pk == linked.pk
    assert User.objects.count() == 1
    linked.refresh_from_db()
    # Кадровые поля обновляются при входе.
    assert linked.first_name == 'Иван'


def test_auto_link_by_username_for_ad_user(ad_settings, ldap):
    """Доменная учётка без ad_login связывается по username."""
    manual = User(username='ivanov', auth_source=User.AuthSource.AD)
    manual.set_unusable_password()
    manual.save()

    user = authenticate_ad('ivanov')

    assert user.pk == manual.pk
    manual.refresh_from_db()
    assert manual.ad_login == 'ivanov'


def test_local_username_is_not_hijacked(ad_settings, ldap):
    """Локальная учётка с тем же логином не переиспользуется."""
    local = User.objects.create_user(
        username='ivanov',
        password='local-pass-123',
    )

    user = authenticate_ad('ivanov')

    assert user.pk != local.pk
    assert user.username == 'ivanov_ad'
    assert user.ad_login == 'ivanov'
    local.refresh_from_db()
    assert local.auth_source == User.AuthSource.LOCAL
    assert local.check_password('local-pass-123')


def test_inactive_user_is_rejected(ad_settings, ldap):
    """Отключённая администратором учётка не входит."""
    User.objects.create(
        username='ivanov',
        auth_source=User.AuthSource.AD,
        ad_login='ivanov',
        is_active=False,
    )

    assert authenticate_ad('ivanov') is None


def test_required_group_is_checked(ad_settings, ldap):
    """Сотрудник вне разрешённой доменной группы не входит."""
    ldap['entry'] = make_entry(
        groups=['CN=OTHER-GROUP,OU=Groups,DC=example,DC=local'],
    )

    assert authenticate_ad('ivanov') is None
    assert User.objects.count() == 0


def test_attributes_not_synced_when_disabled(ad_settings, ldap):
    """При AD_SYNC_ATTRIBUTES=False поля пользователя не меняются."""
    ad_settings.AD_SYNC_ATTRIBUTES = False
    user = User.objects.create(
        username='ivanov',
        auth_source=User.AuthSource.AD,
        ad_login='ivanov',
        first_name='Пётр',
    )

    authenticate_ad('ivanov')

    user.refresh_from_db()
    assert user.first_name == 'Пётр'


def test_insecure_uri_is_rejected(ad_settings):
    """LDAP без TLS не должен использоваться для проверки пароля."""
    ad_settings.AD_SERVER_URI = 'ldap://dc1.example.local:389'
    ad_settings.AD_USE_STARTTLS = False

    with pytest.raises(ImproperlyConfigured):
        authenticate_ad('ivanov')


def test_check_ad_tls(ad_settings):
    """Системная проверка ловит небезопасную конфигурацию."""
    assert check_ad_tls(None) == []

    ad_settings.AD_SERVER_URI = 'ldap://dc1.example.local:389'
    errors = check_ad_tls(None)
    assert len(errors) == 1
    assert errors[0].id == 'accounts.E001'

    ad_settings.AD_USE_STARTTLS = True
    assert check_ad_tls(None) == []


def test_disabled_ad_backend_returns_none(settings, ldap):
    """При выключенном AD backend не аутентифицирует никого."""
    settings.AD_ENABLED = False

    assert authenticate_ad('ivanov') is None
    assert User.objects.count() == 0


def test_default_group_is_created_once(ad_settings, ldap):
    """Группа по умолчанию не дублируется между входами."""
    authenticate_ad('ivanov')
    authenticate_ad('ivanov')

    assert Group.objects.filter(name=DEFAULT_GROUP).count() == 1
