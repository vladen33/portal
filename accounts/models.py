"""Модели приложения accounts: пользователь портала."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Пользователь портала СМК.

    Расширяет стандартного пользователя Django полями кадрового
    учёта. Самостоятельная регистрация не предусмотрена: учётные
    записи создаёт администратор портала через админку.

    Модель подключена через ``AUTH_USER_MODEL`` и должна быть
    описана до первой миграции — заменить её позже крайне сложно.
    """

    class AuthSource(models.TextChoices):
        """Источник учётной записи.

        ``LOCAL`` — логин и пароль выдал администратор портала.
        ``AD`` — учётная запись домена Active Directory
        (вход по ней будет реализован позже отдельным backend).
        """

        LOCAL = 'local', 'Учётная запись портала'
        AD = 'ad', 'Учётная запись Active Directory'

    # Отчества нет в стандартной модели Django, добавляем своё поле.
    middle_name = models.CharField(
        'отчество',
        max_length=150,
        blank=True,
    )
    position = models.CharField(
        'должность',
        max_length=200,
        blank=True,
    )
    department = models.CharField(
        'подразделение',
        max_length=200,
        blank=True,
    )
    # Источник записи нужен, чтобы понимать, каким backend
    # проверять пароль пользователя.
    auth_source = models.CharField(
        'источник учётной записи',
        max_length=10,
        choices=AuthSource.choices,
        default=AuthSource.LOCAL,
    )

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'
        ordering = ['username']

    def get_full_name(self):
        """Возвращает ФИО в формате «Фамилия Имя Отчество»."""
        parts = [self.last_name, self.first_name, self.middle_name]
        full_name = ' '.join(part for part in parts if part)
        # Если ФИО не заполнено, показываем логин.
        return full_name or self.username

    def __str__(self):
        return self.get_full_name()
