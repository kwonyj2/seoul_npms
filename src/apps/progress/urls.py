from rest_framework.routers import DefaultRouter
from .views import (
    InspectionPlanViewSet, SchoolInspectionViewSet,
    HolidayViewSet, WorkerAreaViewSet,
)

app_name = 'progress'

router = DefaultRouter()
router.register(r'plans',       InspectionPlanViewSet,   basename='plan')
router.register(r'inspections', SchoolInspectionViewSet, basename='inspection')
router.register(r'holidays',    HolidayViewSet,          basename='holiday')
router.register(r'worker-areas', WorkerAreaViewSet,      basename='worker-area')

urlpatterns = router.urls
