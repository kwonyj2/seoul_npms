from django.contrib import admin
from .models import IncidentCategory, IncidentSubcategory, Incident, IncidentAssignment, IncidentSLA, SLARule, SLAMonthly

@admin.register(IncidentCategory)
class IncidentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order', 'is_active')

@admin.register(IncidentSubcategory)
class IncidentSubcategoryAdmin(admin.ModelAdmin):
    list_display = ('category', 'name', 'is_other', 'is_active')
    list_filter = ('category',)

@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('incident_number', 'school', 'category', 'status', 'priority', 'received_at')
    list_filter = ('status', 'priority', 'category', 'school__support_center')
    search_fields = ('incident_number', 'school__name', 'requester_name')
    readonly_fields = ('incident_number', 'received_at')
    date_hierarchy = 'received_at'

@admin.register(SLARule)
class SLARuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'arrival_hours', 'resolve_hours', 'is_active', 'apply_from')

@admin.register(SLAMonthly)
class SLAMonthlyAdmin(admin.ModelAdmin):
    list_display = ('year', 'month', 'total_score', 'grade', 'uptime_pct', 'fault_count',
                    'recurrence_count', 'security_count', 'calculated_at')
    list_filter = ('year', 'grade')
    ordering = ('-year', '-month')
    readonly_fields = ('calculated_at', 'created_by')
