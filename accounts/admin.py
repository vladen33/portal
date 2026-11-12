"""Настройка модели пользователя в админке."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    """Админка пользователя портала.

    Наследуемся от стандартного ``UserAdmin``, чтобы сохранить
    работу с паролями и правами, и добавляем поля кадрового учёта.
    """

    list_display = (
        'username',
        'last_name',
        'first_name',
        'department',
        'position',
        'auth_source',
        'is_active',
    )
    list_filter = (
        'auth_source',
        'is_active',
        'is_staff',
        'department',
    )
    search_fields = (
        'username',
        'last_name',
        'first_name',
        'middle_name',
        'email',
    )

    # Стандартные секции UserAdmin дополняем данными сотрудника.
    fieldsets = UserAdmin.fieldsets + (
        (
            'Данные сотрудника',
            {
                'fields': (
                    'middle_name',
                    'position',
                    'department',
                    'auth_source',
                ),
            },
        ),
    )
    # Те же поля нужны на странице создания пользователя.
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Данные сотрудника',
            {
                'fields': (
                    'middle_name',
                    'position',
                    'department',
                    'auth_source',
                ),
            },
        ),
    )
