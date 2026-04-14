from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import PhotoWorkTypeViewSet, PhotoViewSet, switch_locations_api

app_name = 'photos'

router = DefaultRouter()
router.register(r'work-types', PhotoWorkTypeViewSet, basename='photo-work-type')
router.register(r'photos',     PhotoViewSet,         basename='photo')

urlpatterns = [
    path('switch-locations/', switch_locations_api, name='switch-locations'),
] + router.urls
