"""Корневая маршрутизация проекта portal."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # Вход и выход: свои формы и вьюхи в приложении accounts.
    path('accounts/', include('accounts.urls')),
    # Главная страница портала и общая навигация.
    path('', include('core.urls')),
]

# Файлы, загруженные пользователями, намеренно не раздаются как статика:
# каталог MEDIA_ROOT на production размещается вне web-root nginx.
# Когда появится первый раздел с загрузками, для локальной разработки
# здесь можно будет добавить django.conf.urls.static.static() под
# условием DEBUG.
