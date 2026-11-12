"""Маршруты аутентификации портала."""

from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts.views import PortalLoginView

app_name = 'accounts'

urlpatterns = [
    # Вход по логину и паролю (режим выбирается в форме).
    path('login/', PortalLoginView.as_view(), name='login'),
    # Выход выполняется только POST-запросом: так его нельзя
    # инициировать чужой ссылкой или картинкой на стороннем сайте.
    path('logout/', LogoutView.as_view(), name='logout'),
]
