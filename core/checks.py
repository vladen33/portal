"""Системные проверки production-настроек портала.

Проверки выполняет ``manage.py check`` (и ``check --deploy`` при
установке). Ошибка уровня ERROR не даёт выкатить конфигурацию,
которая заведомо небезопасна или неработоспособна.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

# Значение ключа по умолчанию из config/settings.py.
INSECURE_SECRET_KEY = 'dev-insecure-key-change-me'


@register(Tags.security)
def check_production_settings(app_configs, **kwargs):
    """Проверяет ключевые настройки production-контура.

    Локальная разработка (``DEBUG=True``) проверками не затрагивается:
    там допустимы и дефолтный ключ, и пустой ``ALLOWED_HOSTS``.
    """
    if settings.DEBUG:
        return []

    errors = []
    if (
        not settings.SECRET_KEY
        or settings.SECRET_KEY == INSECURE_SECRET_KEY
        or settings.SECRET_KEY.startswith('dev-insecure')
    ):
        errors.append(
            Error(
                'DJANGO_DEBUG=False требует собственный DJANGO_SECRET_KEY.',
                hint=(
                    'Сгенерируйте ключ и укажите его в .env: '
                    'venv/bin/python -c "from django.core.management'
                    '.utils import get_random_secret_key; '
                    'print(get_random_secret_key())"'
                ),
                id='core.E001',
            )
        )

    if not settings.ALLOWED_HOSTS:
        errors.append(
            Error(
                'DJANGO_ALLOWED_HOSTS пуст: Django отклонит все запросы.',
                hint=(
                    'Укажите доменное имя портала, например '
                    'portal.example.local.'
                ),
                id='core.E002',
            )
        )

    return errors
