from django.contrib import admin
from .models import AuditProject, Requirement, ArtifactTemplate, Artifact, AuditPlan, ChecklistItem, CorrectiveAction, ArtifactFile


@admin.register(AuditProject)
class AuditProjectAdmin(admin.ModelAdmin):
    list_display  = ['name', 'year', 'audit_firm', 'is_active']
    list_filter   = ['year', 'is_active']


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display  = ['code', 'category', 'name', 'status']
    list_filter   = ['project', 'category', 'status']
    search_fields = ['code', 'name']


@admin.register(ArtifactTemplate)
class ArtifactTemplateAdmin(admin.ModelAdmin):
    list_display  = ['code', 'audit_phase', 'submit_timing', 'name', 'is_required', 'is_additional']
    list_filter   = ['project', 'audit_phase', 'submit_timing', 'is_required', 'is_additional']
    search_fields = ['code', 'name']


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display  = ['code', 'audit_phase', 'name', 'status', 'submitted_at']
    list_filter   = ['project', 'audit_phase', 'status']
    search_fields = ['code', 'name']


@admin.register(AuditPlan)
class AuditPlanAdmin(admin.ModelAdmin):
    list_display  = ['project', 'phase', 'status', 'planned_start', 'planned_end']
    list_filter   = ['project', 'phase', 'status']


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display  = ['audit_plan', 'area', 'phase', 'seq', 'result']
    list_filter   = ['audit_plan', 'area', 'result']


@admin.register(CorrectiveAction)
class CorrectiveActionAdmin(admin.ModelAdmin):
    list_display  = ['checklist_item', 'action_type', 'status', 'due_date']
    list_filter   = ['action_type', 'status']


@admin.register(ArtifactFile)
class ArtifactFileAdmin(admin.ModelAdmin):
    list_display  = ['file_name', 'template', 'occurrence_date', 'location_note', 'file_size_display', 'is_scanned', 'uploaded_at']
    list_filter   = ['project', 'template__audit_phase', 'is_scanned']
    search_fields = ['file_name', 'location_note', 'display_name']
    readonly_fields = ['file_size_display', 'ext', 'uploaded_at']
