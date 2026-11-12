"""Корневая маршрутизация проекта portal."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Вход и выход: свои формы и вьюхи в приложении accounts.
    path('accounts/', include('accounts.urls')),
    # Документы СМК: список, карточка, файл редакции, ознакомление.
    path('documents/', include('documents.urls')),
    # Корень сайта ведёт на список документов.
    path(
        '',
        RedirectView.as_view(
            pattern_name='documents:list',
            permanent=False,
        ),
    ),
]

# Файлы редакций документов намеренно не раздаются как статика:
# их отдаёт только RevisionFileView после проверки входа, поэтому
# раздачи MEDIA_URL через static() здесь нет.
