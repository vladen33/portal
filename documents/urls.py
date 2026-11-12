"""Маршруты приложения documents."""

from django.urls import path

from documents.views import (
    AcknowledgeView,
    DocumentDetailView,
    DocumentListView,
    RevisionFileView,
)

app_name = 'documents'

urlpatterns = [
    # Список действующих документов.
    path('', DocumentListView.as_view(), name='list'),
    # Карточка документа.
    path('<int:pk>/', DocumentDetailView.as_view(), name='detail'),
    # Файл редакции: только после проверки входа.
    path(
        '<int:pk>/revisions/<int:revision_pk>/file/',
        RevisionFileView.as_view(),
        name='file',
    ),
    # Подтверждение ознакомления (POST-форма с карточки).
    path(
        '<int:pk>/revisions/<int:revision_pk>/acknowledge/',
        AcknowledgeView.as_view(),
        name='acknowledge',
    ),
]
