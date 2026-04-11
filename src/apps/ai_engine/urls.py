from rest_framework.routers import DefaultRouter
from .views import (
    AiModelViewSet, AiJobViewSet,
    WorkerAssignmentPredictionViewSet, IncidentPatternViewSet,
    MaterialForecastViewSet,
)

app_name = 'ai_engine'

router = DefaultRouter()
router.register(r'models',      AiModelViewSet,                  basename='ai-model')
router.register(r'jobs',        AiJobViewSet,                    basename='ai-job')
router.register(r'predictions', WorkerAssignmentPredictionViewSet, basename='ai-prediction')
router.register(r'patterns',    IncidentPatternViewSet,          basename='incident-pattern')
router.register(r'material',    MaterialForecastViewSet,         basename='material-forecast')

urlpatterns = router.urls
