from rest_framework.routers import DefaultRouter
from .views import (
    NetworkDeviceViewSet, NetworkTopologyViewSet,
    NetworkEventViewSet, NetworkCommandViewSet
)

app_name = 'network'

router = DefaultRouter()
router.register(r'devices',    NetworkDeviceViewSet,   basename='network-device')
router.register(r'topology',   NetworkTopologyViewSet, basename='network-topology')
router.register(r'events',     NetworkEventViewSet,    basename='network-event')
router.register(r'commands',   NetworkCommandViewSet,  basename='network-command')

urlpatterns = router.urls
