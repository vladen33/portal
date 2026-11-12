"""Backend аутентификации для учётных записей портала."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


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
