"""Конфигурация приложения documents."""

from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Документы СМК: карточки, редакции, ознакомление."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'
    verbose_name = 'Документы СМК'
