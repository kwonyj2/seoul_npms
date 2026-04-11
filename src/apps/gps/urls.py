from rest_framework.routers import DefaultRouter
from .views import (
    GpsLogViewSet, WorkerLocationViewSet,
    RouteHistoryViewSet, GeoFenceViewSet, GeoFenceEventViewSet
)

app_name = 'gps'

router = DefaultRouter()
router.register(r'logs',      GpsLogViewSet,        basename='gps-log')
router.register(r'locations', WorkerLocationViewSet, basename='worker-location')
router.register(r'routes',    RouteHistoryViewSet,   basename='route-history')
router.register(r'fences',    GeoFenceViewSet,       basename='geo-fence')
router.register(r'events',    GeoFenceEventViewSet,  basename='geo-fence-event')

urlpatterns = router.urls
