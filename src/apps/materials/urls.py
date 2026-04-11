from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'materials'
router = DefaultRouter()
router.register(r'categories',  views.MaterialCategoryViewSet,  basename='category')
router.register(r'items',       views.MaterialViewSet,          basename='material')
router.register(r'warehouse',   views.WarehouseInventoryViewSet,basename='warehouse')
router.register(r'center',      views.CenterInventoryViewSet,   basename='center-inv')
router.register(r'inbound',     views.MaterialInboundViewSet,   basename='inbound')
router.register(r'outbound',    views.MaterialOutboundViewSet,  basename='outbound')
router.register(r'returns',     views.MaterialReturnViewSet,    basename='return')
router.register(r'usage',       views.MaterialUsageViewSet,     basename='usage')

urlpatterns = [
    path('', include(router.urls)),
]
