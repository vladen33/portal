"""Маршруты ядра портала."""

from django.urls import path

from core.views import HomeView

app_name = 'core'

urlpatterns = [
    # Главная страница: точка входа после входа в систему.
    path('', HomeView.as_view(), name='home'),
]
