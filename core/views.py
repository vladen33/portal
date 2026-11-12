"""Представления ядра портала."""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class HomeView(LoginRequiredMixin, TemplateView):
    """Главная страница портала.

    Открывается сотруднику сразу после входа и служит точкой сбора
    разделов: каждый новый раздел — отдельное приложение, ссылку на
    которое добавляют в шаблон этой страницы и в меню ``base.html``.
    """

    template_name = 'core/home.html'


class HealthCheckView(View):
    """Проверка живости портала для мониторинга и приёмки.

    Доступна без авторизации: системе мониторинга нужен простой GET.
    Проверяет не только ответ приложения, но и доступность базы:
    при недоступной БД возвращает 503, чтобы проверка не считалась
    успешной при лежащей базе.
    """

    def get(self, request):
        """Возвращает 200, если приложение и БД в порядке, иначе 503."""
        try:
            connection.ensure_connection()
        except Exception:
            # Трассировку пишем в журнал: причина важна для дежурного.
            logger.exception('healthz: база данных недоступна')
            return JsonResponse(
                {'status': 'error', 'db': 'error'},
                status=503,
            )
        return JsonResponse({'status': 'ok', 'db': 'ok'})
