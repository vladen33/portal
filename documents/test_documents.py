"""Тесты доступа к документам и ознакомления с ними."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import User
from documents.models import Acknowledgement, Document, Revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    """Обычный пользователь портала."""
    return User.objects.create_user(
        username='sidorov',
        password='secret-pass-123',
    )


@pytest.fixture
def document():
    """Действующий документ СМК с одной действующей редакцией."""
    doc = Document.objects.create(
        code='СТО-01-2026',
        title='Управление документацией',
        doc_type=Document.DocType.PROCEDURE,
        status=Document.Status.ACTIVE,
    )
    Revision.objects.create(
        document=doc,
        number=1,
        is_current=True,
        change_note='Первая редакция',
    )
    return doc


def test_list_requires_login(client):
    """Анонимный пользователь перенаправляется на страницу входа."""
    response = client.get(reverse('documents:list'))
    assert response.status_code == 302
    assert reverse('accounts:login') in response.url


def test_list_shows_only_active_documents(client, user, document):
    """В списке видны только действующие документы."""
    Document.objects.create(
        code='СТО-02-2026',
        title='Черновик процедуры',
        status=Document.Status.DRAFT,
    )
    client.force_login(user)
    response = client.get(reverse('documents:list'))
    codes = [item.code for item in response.context['documents']]
    assert codes == ['СТО-01-2026']


def test_list_search_by_title(client, user, document):
    """Поиск по названию находит документ."""
    client.force_login(user)
    response = client.get(
        reverse('documents:list'),
        {'q': 'документацией'},
    )
    codes = [item.code for item in response.context['documents']]
    assert codes == ['СТО-01-2026']


def test_new_current_revision_resets_previous(document):
    """Новая действующая редакция снимает флаг с предыдущей."""
    new_revision = Revision.objects.create(
        document=document,
        number=2,
        is_current=True,
    )
    current = Revision.objects.filter(
        document=document,
        is_current=True,
    )
    assert current.count() == 1
    assert current.first().pk == new_revision.pk


def test_database_forbids_two_current_revisions(document):
    """Ограничение БД запрещает две действующие редакции.

    ``bulk_create`` не вызывает ``save()`` модели, поэтому проверяем
    именно частичный уникальный индекс на уровне базы данных.
    """
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Revision.objects.bulk_create(
                [Revision(document=document, number=2, is_current=True)]
            )


def test_view_marks_revision_viewed(
    client,
    user,
    document,
    settings,
    tmp_path,
):
    """Открытие файла редакции фиксирует просмотр и ведёт к файлу."""
    # Файлы тестов пишем во временный каталог, а не в media/ проекта.
    settings.MEDIA_ROOT = tmp_path
    revision = Revision.objects.create(
        document=document,
        number=2,
        is_current=True,
        file=SimpleUploadedFile('doc.pdf', b'%PDF-1.4 test'),
    )
    client.force_login(user)

    response = client.get(
        reverse('documents:detail', args=[document.pk]),
        {'view': revision.pk},
    )

    assert response.status_code == 302
    assert response.url == revision.file.url
    acknowledgement = Acknowledgement.objects.get(
        user=user,
        revision=revision,
    )
    assert acknowledgement.viewed_at is not None


def test_acknowledge_creates_single_record(client, user, document):
    """Ознакомление фиксируется один раз и не дублируется."""
    revision = document.current_revision
    client.force_login(user)
    url = reverse(
        'documents:acknowledge',
        args=[document.pk, revision.pk],
    )

    client.post(url)
    first = Acknowledgement.objects.get(user=user, revision=revision)
    assert first.acknowledged_at is not None
    assert first.viewed_at is not None

    client.post(url)
    assert (
        Acknowledgement.objects.filter(
            user=user,
            revision=revision,
        ).count()
        == 1
    )
    second = Acknowledgement.objects.get(user=user, revision=revision)
    assert second.acknowledged_at == first.acknowledged_at
