"""Представления ядра портала."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class HomeView(LoginRequiredMixin, TemplateView):
    """Главная страница портала.

    Открывается сотруднику сразу после входа и служит точкой сбора
    разделов: каждый новый раздел — отдельное приложение, ссылку на
    которое добавляют в шаблон этой страницы и в меню ``base.html``.
    """

    template_name = 'core/home.html'
