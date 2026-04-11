from rest_framework.routers import DefaultRouter
from .views import PhotoWorkTypeViewSet, PhotoViewSet

app_name = 'photos'

router = DefaultRouter()
router.register(r'work-types', PhotoWorkTypeViewSet, basename='photo-work-type')
router.register(r'photos',     PhotoViewSet,         basename='photo')

urlpatterns = router.urls
