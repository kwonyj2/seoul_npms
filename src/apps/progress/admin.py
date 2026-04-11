from django.contrib import admin
from .models import InspectionPlan, SchoolInspection


class SchoolInspectionInline(admin.TabularInline):
    model  = SchoolInspection
    extra  = 0
    fields = ['school', 'assigned_worker', 'status', 'scheduled_date', 'completed_date']


@admin.register(InspectionPlan)
class InspectionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_type', 'year', 'quarter', 'start_date', 'end_date', 'status']
    list_filter  = ['plan_type', 'status', 'year']
    inlines      = [SchoolInspectionInline]


@admin.register(SchoolInspection)
class SchoolInspectionAdmin(admin.ModelAdmin):
    list_display = ['plan', 'school', 'assigned_worker', 'status', 'scheduled_date', 'completed_date']
    list_filter  = ['status', 'plan__plan_type']
    search_fields = ['school__name', 'plan__name']
