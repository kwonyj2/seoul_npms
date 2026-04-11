from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'assets'
router = DefaultRouter()
router.register(r'categories',    views.AssetCategoryViewSet,     basename='category')
router.register(r'models',        views.AssetModelViewSet,        basename='model')
router.register(r'assets',        views.AssetViewSet,             basename='asset')
router.register(r'inbound',       views.AssetInboundViewSet,      basename='inbound')
router.register(r'outbound',      views.AssetOutboundViewSet,     basename='outbound')
router.register(r'returns',       views.AssetReturnViewSet,       basename='return')
router.register(r'rma',           views.AssetRMAViewSet,          basename='rma')
router.register(r'asset_configs', views.DeviceNetworkConfigViewSet, basename='asset-config')
router.register(r'model_configs', views.AssetModelConfigViewSet,  basename='model-config')

urlpatterns = [
    path('',     views.assets_view, name='index'),
    path('api/', include(router.urls)),
]
