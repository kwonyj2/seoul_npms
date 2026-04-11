from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WBSItemViewSet

app_name = 'wbs'

router = DefaultRouter()
router.register(r'items', WBSItemViewSet, basename='wbs-item')

urlpatterns = [
    path('', include(router.urls)),
]
