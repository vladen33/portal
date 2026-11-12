"""Формы аутентификации портала."""

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm


class PortalAuthenticationForm(AuthenticationForm):
    """Форма входа с переключателем режима аутентификации.

    Пользователь выбирает, чем входить:

    * учётной записью портала — логин и пароль выдал администратор;
    * учётной записью Active Directory — пока не поддерживается.

    Выбранный режим передаётся в ``authenticate()`` как
    ``auth_source``, а нужный backend выбирает его из ``kwargs``.
    """

    AUTH_SOURCE_CHOICES = (
        ('local', 'Учётная запись портала'),
        ('ad', 'Учётная запись Active Directory'),
    )

    auth_source = forms.ChoiceField(
        label='Способ входа',
        choices=AUTH_SOURCE_CHOICES,
        initial='local',
        widget=forms.RadioSelect,
    )

    def clean(self):
        """Проверяет учётные данные с учётом выбранного режима.

        Повторяем стандартную логику ``AuthenticationForm``, но
        передаём в ``authenticate()`` режим входа. Иначе backend
        не сможет отличить локальную запись от доменной.
        """
        auth_source = self.cleaned_data.get('auth_source', 'local')

        # Режим Active Directory ещё не настроен: сообщаем явно,
        # а не показываем общее «неверный логин или пароль».
        if auth_source == 'ad':
            raise forms.ValidationError(
                'Вход через Active Directory пока не настроен. '
                'Используйте учётную запись портала.'
            )

        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
                auth_source=auth_source,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            # Проверяет, что учётная запись активна.
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
