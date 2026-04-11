from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'schools'

router = DefaultRouter()
router.register(r'centers',   views.SupportCenterViewSet, basename='center')
router.register(r'types',     views.SchoolTypeViewSet,    basename='schooltype')
router.register(r'schools',   views.SchoolViewSet,        basename='school')
router.register(r'buildings', views.SchoolBuildingViewSet,basename='building')

urlpatterns = [
    # 템플릿 뷰
    path('list/',        views.school_list_view,   name='list'),
    path('map/',         views.school_map_view,    name='map'),
    path('<int:pk>/',    views.school_detail_view, name='detail'),
    # 건물 정보 파일 API (구버전 호환)
    path('<int:pk>/building-docs/', views.building_docs_api, name='building-docs'),
    # 네트워크 문서 API
    path('<int:pk>/network-docs/', views.network_docs_api, name='network-docs'),
    # REST API
    path('', include(router.urls)),
]
