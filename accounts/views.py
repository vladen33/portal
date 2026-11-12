"""Представления приложения accounts."""

from django.conf import settings
from django.contrib.auth.views import LoginView

from accounts.forms import PortalAuthenticationForm


class PortalLoginView(LoginView):
    """Страница входа с выбором режима аутентификации."""

    # Своя форма нужна ради переключателя «портал / Active Directory».
    authentication_form = PortalAuthenticationForm
    template_name = 'registration/login.html'
    # Уже вошедшего пользователя сразу отправляем на главную.
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        """Передаёт в шаблон признак доступности входа через AD.

        Выбор режима показывается всегда, но пока домен не настроен
        (``AD_ENABLED=False``), шаблон добавляет к нему пояснение:
        иначе пользователь узнает о проблеме только после отправки
        формы.
        """
        context = super().get_context_data(**kwargs)
        context['ad_enabled'] = settings.AD_ENABLED
        return context
