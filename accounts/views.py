"""Представления приложения accounts."""

from django.contrib.auth.views import LoginView

from accounts.forms import PortalAuthenticationForm


class PortalLoginView(LoginView):
    """Страница входа с выбором режима аутентификации."""

    # Своя форма нужна ради переключателя «портал / Active Directory».
    authentication_form = PortalAuthenticationForm
    template_name = 'registration/login.html'
    # Уже вошедшего пользователя сразу отправляем к документам.
    redirect_authenticated_user = True
