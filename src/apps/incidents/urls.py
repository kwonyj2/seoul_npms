from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import sla_indicator_api, sla_delete_api, sla_report_api
from .pattern_views import (
    vulnerable_assets_api, seasonal_pattern_api,
    sla_risk_api, monthly_insight_api,
)

app_name = 'incidents'

router = DefaultRouter()
router.register(r'categories',   views.IncidentCategoryViewSet,   basename='category')
router.register(r'incidents',    views.IncidentViewSet,            basename='incident')
router.register(r'assignments',  views.IncidentAssignmentViewSet,  basename='assignment')
router.register(r'sla-rules',    views.SLARuleViewSet,             basename='slarule')
router.register(r'work-orders',  views.WorkOrderViewSet,           basename='workorder')

urlpatterns = [
    # 템플릿 뷰
    path('list/',        views.incident_list_view,   name='list'),
    path('<int:pk>/',    views.incident_detail_view, name='detail'),
    path('create/',      views.incident_create_view, name='create'),
    path('sla/',         views.sla_view,             name='sla'),
    # SLA API
    path('sla/calculate/', views.sla_calculate_api, name='sla_calculate'),
    path('sla/report/',    sla_report_api,           name='sla_report'),
    path('sla/<int:year>/<int:month>/', views.sla_detail_api, name='sla_detail'),
    path('sla/<int:year>/<int:month>/delete/', sla_delete_api,    name='sla_delete'),
    path('sla/<int:year>/<int:month>/<str:indicator>/', sla_indicator_api, name='sla_indicator'),
    # 패턴 분석 API
    path('pattern/vulnerable-assets/', vulnerable_assets_api, name='pattern-vulnerable-assets'),
    path('pattern/seasonal/',          seasonal_pattern_api,  name='pattern-seasonal'),
    path('pattern/sla-risk/',          sla_risk_api,          name='pattern-sla-risk'),
    path('pattern/monthly-insight/',   monthly_insight_api,   name='pattern-monthly-insight'),
    # REST API
    path('', include(router.urls)),
]
