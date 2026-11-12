"""Админка документов СМК."""

from django.contrib import admin

from documents.models import Acknowledgement, Document, Revision


class RevisionInline(admin.TabularInline):
    """Редакции редактируются прямо в карточке документа."""

    model = Revision
    extra = 0
    fields = (
        'number',
        'is_current',
        'effective_date',
        'file',
        'change_note',
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Управление карточками документов СМК."""

    list_display = (
        'code',
        'title',
        'doc_type',
        'status',
        'updated_at',
    )
    list_filter = ('doc_type', 'status')
    search_fields = ('code', 'title')
    inlines = [RevisionInline]
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        """Запоминает автора документа при создании."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    """Управление редакциями документов."""

    list_display = (
        '__str__',
        'is_current',
        'effective_date',
        'created_at',
    )
    list_filter = ('is_current', 'document__doc_type')
    search_fields = ('document__code', 'document__title')
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        """Запоминает автора редакции при создании."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Acknowledgement)
class AcknowledgementAdmin(admin.ModelAdmin):
    """Просмотр фактов ознакомления сотрудников с документами."""

    list_display = (
        'user',
        'revision',
        'assigned_at',
        'viewed_at',
        'acknowledged_at',
    )
    list_filter = ('revision__document',)
    search_fields = ('user__username', 'user__last_name')
    # Даты выставляет система, менять их вручную нельзя.
    readonly_fields = ('assigned_at', 'viewed_at', 'acknowledged_at')
