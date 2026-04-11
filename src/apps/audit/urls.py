from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AuditProjectViewSet, RequirementViewSet,
    ArtifactTemplateViewSet, ArtifactViewSet,
    AuditPlanViewSet, ChecklistItemViewSet, CorrectiveActionViewSet,
    ArtifactFileViewSet, export_rtm_excel,
)

app_name = 'audit'

router = DefaultRouter()
router.register(r'projects',       AuditProjectViewSet,     basename='audit-project')
router.register(r'requirements',   RequirementViewSet,      basename='requirement')
router.register(r'templates',      ArtifactTemplateViewSet, basename='artifact-template')
router.register(r'artifacts',      ArtifactViewSet,         basename='artifact')
router.register(r'plans',          AuditPlanViewSet,        basename='audit-plan')
router.register(r'checklist',      ChecklistItemViewSet,    basename='checklist')
router.register(r'corrective',     CorrectiveActionViewSet, basename='corrective')
router.register(r'artifact-files', ArtifactFileViewSet,     basename='artifact-file')

urlpatterns = [
    path('export/rtm/', export_rtm_excel, name='export-rtm'),
    path('', include(router.urls)),
]
