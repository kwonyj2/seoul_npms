from django.contrib import admin
from .models import WBSItem


@admin.register(WBSItem)
class WBSItemAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'phase', 'depth', 'assignee', 'weight',
                     'planned_start', 'planned_end', 'progress', 'progress_source']
    list_filter   = ['project', 'phase', 'depth', 'progress_source', 'is_milestone']
    search_fields = ['code', 'name']
    raw_id_fields = ['parent', 'assignee', 'linked_template', 'linked_inspection']
