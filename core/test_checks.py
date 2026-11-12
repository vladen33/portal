"""Тесты системных проверок production-настроек."""

from django.test import override_settings

from core.checks import check_production_settings

VALID_SETTINGS = {
    'DEBUG': False,
    'SECRET_KEY': 'x' * 60,
    'ALLOWED_HOSTS': ['portal.example.local'],
}


def test_checks_are_skipped_in_debug():
    """В разработке прод-проверки не срабатывают."""
    with override_settings(DEBUG=True):
        assert check_production_settings(None) == []


def test_default_secret_key_is_rejected():
    """С дефолтным ключом production не запускается."""
    with override_settings(
        DEBUG=False,
        SECRET_KEY='dev-insecure-key-change-me',
        ALLOWED_HOSTS=['portal.example.local'],
    ):
        errors = check_production_settings(None)

    assert [error.id for error in errors] == ['core.E001']


def test_empty_allowed_hosts_is_rejected():
    """Пустой ALLOWED_HOSTS — ошибка production-конфигурации."""
    with override_settings(
        DEBUG=False,
        SECRET_KEY='x' * 60,
        ALLOWED_HOSTS=[],
    ):
        errors = check_production_settings(None)

    assert [error.id for error in errors] == ['core.E002']


def test_valid_settings_pass_checks():
    """Корректные настройки проходят проверку без замечаний."""
    with override_settings(**VALID_SETTINGS):
        assert check_production_settings(None) == []
