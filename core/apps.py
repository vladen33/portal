"""Конфигурация приложения core."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Главная страница портала и общая навигация.

    Своих моделей у приложения нет: здесь живут только точка входа
    после входа в систему и общие элементы, к которым подключаются
    будущие разделы портала.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Портал'

    def ready(self):
        """Подключает системные проверки production-настроек."""
        # Django не импортирует модуль checks автоматически:
        # регистрация происходит только при явном импорте.
        from core import checks  # noqa: F401
