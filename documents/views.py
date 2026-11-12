"""Представления раздела документов СМК."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import FileResponse, Http404
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
    """Карточка документа: сведения, редакции, статус ознакомления."""

    model = Document
    template_name = 'documents/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        """Пользователь видит только действующие документы."""
        return Document.objects.filter(
            status=Document.Status.ACTIVE
        ).prefetch_related('revisions')

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


class RevisionFileView(LoginRequiredMixin, View):
    """Отдаёт файл редакции только авторизованному пользователю.

    Файлы документов СМК не раздаются как статика: обращение идёт
    через эту вьюху, поэтому Django проверяет вход и фиксирует факт
    просмотра. При переходе на nginx с ``X-Accel-Redirect`` меняется
    только способ отдачи байтов в конце метода.
    """

    def get(self, request, pk, revision_pk):
        """Возвращает файл редакции и отмечает просмотр."""
        revision = get_object_or_404(
            Revision,
            pk=revision_pk,
            document__pk=pk,
            document__status=Document.Status.ACTIVE,
        )
        if not revision.file:
            raise Http404('У этой редакции нет файла.')

        # Первое открытие файла создаёт запись ознакомления.
        acknowledgement, _ = Acknowledgement.objects.get_or_create(
            user=request.user,
            revision=revision,
        )
        acknowledgement.mark_viewed()

        # В пути upload_to есть каталоги, оставляем только имя файла.
        file_name = revision.file.name.rsplit('/', 1)[-1]
        return FileResponse(
            revision.file.open('rb'),
            as_attachment=False,
            filename=file_name,
        )
