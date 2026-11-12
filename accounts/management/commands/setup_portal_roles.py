"""Команда создания групп портала.

Запускается после миграций:

    venv/bin/python manage.py setup_portal_roles

Создаёт группу Django, в которую ADBackend добавляет всех
доменных пользователей при первом входе. Права на документы
администратор назначает этой группе уже в админке.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Идемпотентно создаёт группу начальных прав портала."""

    help = 'Создаёт группу портала для доменных пользователей.'

    def handle(self, *args, **options):
        """Создаёт группу из настройки AD_DEFAULT_GROUP."""
        group_name = (settings.AD_DEFAULT_GROUP or '').strip()
        if not group_name:
            self.stdout.write(
                self.style.WARNING(
                    'AD_DEFAULT_GROUP не задана, группа не создана.',
                ),
            )
            return

        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Создана группа «{group.name}».',
                ),
            )
        else:
            self.stdout.write(
                f'Группа «{group.name}» уже существует.',
            )
