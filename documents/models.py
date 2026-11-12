"""Модели документов системы менеджмента качества."""

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class Document(models.Model):
    """Документ СМК: политика, процедура, инструкция и т.п.

    Сам документ — это «карточка» с шифром и названием. Конкретные
    тексты хранятся в редакциях (:class:`Revision`): у документа
    может быть несколько последовательных редакций, действующая —
    ровно одна.
    """

    class DocType(models.TextChoices):
        """Тип документа СМК."""

        POLICY = 'policy', 'Политика'
        PROCEDURE = 'procedure', 'Процедура'
        INSTRUCTION = 'instruction', 'Инструкция'
        METHOD = 'method', 'Методика'
        FORM = 'form', 'Форма'
        RECORD = 'record', 'Запись'

    class Status(models.TextChoices):
        """Жизненный цикл документа."""

        DRAFT = 'draft', 'Черновик'
        ACTIVE = 'active', 'Действующий'
        ARCHIVED = 'archived', 'Архив'

    # Шифр документа, например СТО-01-2026. Уникален.
    code = models.CharField('шифр', max_length=50, unique=True)
    title = models.CharField('название', max_length=255)
    doc_type = models.CharField(
        'тип документа',
        max_length=20,
        choices=DocType.choices,
        default=DocType.PROCEDURE,
    )
    status = models.CharField(
        'статус',
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    summary = models.TextField('краткое описание', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_documents',
        verbose_name='создал',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField('создан', auto_now_add=True)
    updated_at = models.DateTimeField('изменён', auto_now=True)

    class Meta:
        verbose_name = 'документ'
        verbose_name_plural = 'документы'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.title}'

    @property
    def current_revision(self):
        """Возвращает действующую редакцию документа или ``None``.

        Метод читает связанные редакции без дополнительного запроса,
        если вызывающий код сделал ``prefetch_related('revisions')``.
        """
        for revision in self.revisions.all():
            if revision.is_current:
                return revision
        return None


class Revision(models.Model):
    """Редакция документа: версия текста и приложенного файла.

    Ограничение ``UniqueConstraint(document, number)`` запрещает
    две редакции с одинаковым номером. Частичный уникальный индекс
    гарантирует, что действующая (``is_current=True``) редакция
    у документа одна.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='revisions',
        verbose_name='документ',
    )
    number = models.PositiveSmallIntegerField('номер редакции')
    change_note = models.TextField('содержание изменений', blank=True)
    file = models.FileField(
        'файл',
        upload_to='documents/%Y/%m/',
        blank=True,
    )
    effective_date = models.DateField(
        'дата введения в действие',
        null=True,
        blank=True,
    )
    is_current = models.BooleanField('действующая', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_revisions',
        verbose_name='создал',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField('создана', auto_now_add=True)

    class Meta:
        verbose_name = 'редакция'
        verbose_name_plural = 'редакции'
        ordering = ['document', '-number']
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'number'],
                name='uniq_revision_number_per_document',
            ),
            # Частичный уникальный индекс: на MSSQL реализуется
            # фильтрованным индексом, на SQLite — частичным.
            models.UniqueConstraint(
                fields=['document'],
                condition=Q(is_current=True),
                name='uniq_current_revision_per_document',
            ),
        ]

    def __str__(self):
        return f'{self.document.code}, редакция {self.number}'

    def save(self, *args, **kwargs):
        """Сохраняет редакцию, поддерживая одну действующую.

        Перед сохранением новой действующей редакции снимаем флаг
        с остальных редакций документа — иначе сработает частичный
        уникальный индекс. Всё выполняется в одной транзакции.
        """
        with transaction.atomic():
            if self.is_current:
                (
                    Revision.objects.filter(
                        document=self.document, is_current=True
                    )
                    .exclude(pk=self.pk)
                    .update(is_current=False)
                )
            super().save(*args, **kwargs)


class Acknowledgement(models.Model):
    """Факт ознакомления сотрудника с редакцией документа.

    Запись создаётся при первом открытии редакции, затем фиксирует
    просмотр (``viewed_at``) и подтверждение (``acknowledged_at``).
    Уникальность пары (пользователь, редакция) не даёт дублировать
    запись.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='acknowledgements',
        verbose_name='пользователь',
    )
    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name='acknowledgements',
        verbose_name='редакция',
    )
    assigned_at = models.DateTimeField('назначено', auto_now_add=True)
    viewed_at = models.DateTimeField(
        'просмотрено',
        null=True,
        blank=True,
    )
    acknowledged_at = models.DateTimeField(
        'ознакомлен',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'ознакомление'
        verbose_name_plural = 'ознакомления'
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'revision'],
                name='uniq_ack_per_user_revision',
            ),
        ]

    def __str__(self):
        return f'{self.user} — {self.revision}'

    def mark_viewed(self):
        """Фиксирует первый просмотр редакции пользователем."""
        if self.viewed_at is None:
            self.viewed_at = timezone.now()
            self.save(update_fields=['viewed_at'])

    def mark_acknowledged(self):
        """Фиксирует ознакомление (повторный вызов дату не меняет)."""
        if self.acknowledged_at is None:
            self.acknowledged_at = timezone.now()
        # Ознакомление всегда означает и просмотр документа.
        if self.viewed_at is None:
            self.viewed_at = self.acknowledged_at
        self.save(update_fields=['acknowledged_at', 'viewed_at'])
