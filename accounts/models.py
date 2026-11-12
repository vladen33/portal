"""Модели приложения accounts: пользователь портала."""

from django.contrib.auth.models import AbstractUser
from django.db import models


def normalize_ad_login(value):
    """Приводит доменный логин к единому виду.

    Доменный логин (``sAMAccountName``) регистронезависим, но
    уникальный индекс SQLite регистрозависим, поэтому храним
    значение в нижнем регистре. UPN вида ``ivanov@example.local``
    сводим к ``ivanov``. Пустое значение превращаем в ``None``:
    несколько NULL уникальный индекс не нарушают, а несколько
    пустых строк — нарушают.
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if '@' in normalized:
        normalized = normalized.split('@', 1)[0]
    return normalized or None


class User(AbstractUser):
    """Пользователь портала.

    Расширяет стандартного пользователя Django полями кадрового
    учёта. Самостоятельная регистрация не предусмотрена: локальные
    учётные записи создаёт администратор портала, доменные —
    создаются автоматически при первом входе через Active Directory
    (JIT) по правилам ``accounts.backends.ADBackend``.

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
    # Доменный логин, по которому портал находит эту учётную запись
    # при входе через Active Directory. Может отличаться от username:
    # username — внутренний логин портала, ad_login — sAMAccountName.
    # Заполняется автоматически при JIT-создании либо вручную
    # администратором, когда логины не совпадают.
    ad_login = models.CharField(
        'доменный логин (AD)',
        max_length=150,
        null=True,
        blank=True,
        unique=True,
        help_text=(
            'Логин в домене (sAMAccountName), например ivanov. '
            'По нему портал находит учётную запись при входе '
            'через Active Directory.'
        ),
    )

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'
        ordering = ['username']

    def clean(self):
        """Нормализует доменный логин перед проверкой формы."""
        super().clean()
        self.ad_login = normalize_ad_login(self.ad_login)

    def save(self, *args, **kwargs):
        """Нормализует доменный логин перед сохранением.

        Поле заполняется и из админки, и backend'ом JIT-создания,
        поэтому нормализация нужна в модели, а не только в форме.
        """
        self.ad_login = normalize_ad_login(self.ad_login)
        super().save(*args, **kwargs)

    def get_full_name(self):
        """Возвращает ФИО в формате «Фамилия Имя Отчество»."""
        parts = [self.last_name, self.first_name, self.middle_name]
        full_name = ' '.join(part for part in parts if part)
        # Если ФИО не заполнено, показываем логин.
        return full_name or self.username

    def __str__(self):
        return self.get_full_name()
