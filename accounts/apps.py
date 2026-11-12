"""Конфигурация приложения accounts."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Пользователи портала и аутентификация."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Пользователи'
