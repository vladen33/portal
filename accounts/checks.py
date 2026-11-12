"""Системные проверки настроек приложения accounts."""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_ad_tls(app_configs, **kwargs):
    """Не даёт запустить вход через AD без шифрования канала.

    Доменные пароли не должны передаваться по локальной сети
    открытым текстом, поэтому допускаются только ``ldaps://``
    либо ``ldap://`` вместе с StartTLS.
    """
    errors = []
    if not settings.AD_ENABLED:
        return errors

    uri = settings.AD_SERVER_URI.strip().lower()
    if uri.startswith('ldaps://'):
        return errors
    if uri.startswith('ldap://') and settings.AD_USE_STARTTLS:
        return errors

    errors.append(
        Error(
            'AD_ENABLED=True требует шифрованного LDAP.',
            hint=(
                'Укажите AD_SERVER_URI=ldaps://... либо '
                'ldap://... вместе с AD_USE_STARTTLS=True.'
            ),
            id='accounts.E001',
        )
    )
    return errors
