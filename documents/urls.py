"""Маршруты приложения documents."""

from django.urls import path

from documents.views import (
    AcknowledgeView,
    DocumentDetailView,
    DocumentListView,
)

app_name = 'documents'

urlpatterns = [
    # Список действующих документов.
    path('', DocumentListView.as_view(), name='list'),
    # Карточка документа; ?view=<id> открывает файл редакции.
    path('<int:pk>/', DocumentDetailView.as_view(), name='detail'),
    # Подтверждение ознакомления (POST-форма с карточки).
    path(
        '<int:pk>/revisions/<int:revision_pk>/acknowledge/',
        AcknowledgeView.as_view(),
        name='acknowledge',
    ),
]
