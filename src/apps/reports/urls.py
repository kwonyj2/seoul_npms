from rest_framework.routers import DefaultRouter
from .views import ReportTemplateViewSet, ReportViewSet

app_name = 'reports'

router = DefaultRouter()
router.register(r'templates', ReportTemplateViewSet, basename='report-template')
router.register(r'reports',   ReportViewSet,         basename='report')

urlpatterns = router.urls
