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
        'ad_login',
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
                    'ad_login',
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
                    'ad_login',
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """Запрещает менять локальный пароль доменной учётной записи.

        Пароль доменного пользователя проверяется в Active Directory.
        Если оставить поле редактируемым, администратор может задать
        локальный пароль и обойти доменную аутентификацию.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.auth_source == User.AuthSource.AD:
            readonly.append('password')
        return readonly
