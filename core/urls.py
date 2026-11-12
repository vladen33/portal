"""Маршруты ядра портала."""

from django.urls import path

from core.views import HealthCheckView, HomeView

app_name = 'core'

urlpatterns = [
    # Главная страница: точка входа после входа в систему.
    path('', HomeView.as_view(), name='home'),
    # Проверка живости для мониторинга и приёмочных проверок.
    path('healthz/', HealthCheckView.as_view(), name='healthz'),
]
