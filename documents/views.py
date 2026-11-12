"""Представления портала документов СМК."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView, View

from documents.models import Acknowledgement, Document, Revision


class DocumentListView(LoginRequiredMixin, ListView):
    """Список действующих документов с поиском и фильтром по типу."""

    model = Document
    template_name = 'documents/document_list.html'
    context_object_name = 'documents'
    paginate_by = 20

    def get_queryset(self):
        """Возвращает действующие документы с учётом фильтров.

        Поддерживаются параметры запроса:

        * ``q`` — поиск по шифру и названию (регистронезависимый);
        * ``doc_type`` — фильтр по типу документа.
        """
        queryset = (
            Document.objects.filter(status=Document.Status.ACTIVE)
            # Редакции нужны шаблону для вывода номера действующей;
            # prefetch избавляет от запроса на каждую строку списка.
            .prefetch_related('revisions')
        )

        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(code__icontains=query) | Q(title__icontains=query)
            )

        doc_type = self.request.GET.get('doc_type', '').strip()
        if doc_type:
            queryset = queryset.filter(doc_type=doc_type)

        return queryset

    def get_context_data(self, **kwargs):
        """Дополняет контекст данными фильтра для шаблона."""
        context = super().get_context_data(**kwargs)
        context['doc_types'] = Document.DocType.choices
        context['current_query'] = self.request.GET.get('q', '')
        context['current_doc_type'] = self.request.GET.get('doc_type', '')
        return context


class DocumentDetailView(LoginRequiredMixin, DetailView):
    """Карточка документа: сведения, редакции, статус ознакомления.

    Если в запросе есть параметр ``?view=<id редакции>``, фиксируем
    просмотр и перенаправляем пользователя на файл редакции.
    """

    model = Document
    template_name = 'documents/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        """Пользователь видит только действующие документы."""
        return Document.objects.filter(
            status=Document.Status.ACTIVE
        ).prefetch_related('revisions')

    def get(self, request, *args, **kwargs):
        """Отдаёт карточку документа или файл выбранной редакции."""
        self.object = self.get_object()

        revision_id = request.GET.get('view')
        if revision_id:
            revision = get_object_or_404(
                Revision,
                pk=revision_id,
                document=self.object,
            )
            # При первом открытии создаём запись ознакомления
            # и отмечаем факт просмотра.
            acknowledgement, _ = Acknowledgement.objects.get_or_create(
                user=request.user,
                revision=revision,
            )
            acknowledgement.mark_viewed()
            if revision.file:
                return redirect(revision.file.url)

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        """Добавляет редакции и статус ознакомления текущего пользователя."""
        context = super().get_context_data(**kwargs)

        current_revision = self.object.current_revision
        context['current_revision'] = current_revision
        context['revisions'] = self.object.revisions.all()

        acknowledgement = None
        if current_revision is not None:
            acknowledgement = Acknowledgement.objects.filter(
                user=self.request.user,
                revision=current_revision,
            ).first()
        context['acknowledgement'] = acknowledgement
        return context


class AcknowledgeView(LoginRequiredMixin, View):
    """Фиксирует ознакомление пользователя с редакцией (только POST)."""

    def post(self, request, pk, revision_pk):
        """Создаёт или обновляет запись ознакомления и возвращает
        пользователя на карточку документа.
        """
        document = get_object_or_404(
            Document,
            pk=pk,
            status=Document.Status.ACTIVE,
        )
        revision = get_object_or_404(
            Revision,
            pk=revision_pk,
            document=document,
        )
        acknowledgement, _ = Acknowledgement.objects.get_or_create(
            user=request.user,
            revision=revision,
        )
        acknowledgement.mark_acknowledged()
        messages.success(
            request,
            'Ознакомление с редакцией зафиксировано.',
        )
        return redirect('documents:detail', pk=document.pk)
