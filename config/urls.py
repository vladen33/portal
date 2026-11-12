"""Корневая маршрутизация проекта portal-ksmk."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Вход и выход: свои формы и вьюхи в приложении accounts.
    path('accounts/', include('accounts.urls')),
    # Документы СМК: список, карточка, ознакомление.
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

# В режиме разработки Django сам отдаёт загруженные пользователями
# файлы (редакции документов). В production этим занимается nginx.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
