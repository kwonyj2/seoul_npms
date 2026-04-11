from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'dashboard'

router = DefaultRouter()
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('',                   views.index,                     name='index'),
    path('summary/',           views.dashboard_summary,         name='summary'),
    path('zones/',             views.dashboard_zones,           name='zones'),
    path('schedule/',          views.dashboard_schedule,        name='schedule'),
    path('workers-gis/',       views.dashboard_workers_gis,     name='workers-gis'),
    path('vworld-sdk/',        views.vworld_sdk_proxy,          name='vworld-sdk'),
    path('incidents-stats/',   views.dashboard_incidents_stats, name='incidents-stats'),
    path('attendance-stats/',  views.dashboard_attendance_stats,name='attendance-stats'),
    path('checkin/',           views.dashboard_checkin,         name='checkin'),
    path('checkout/',          views.dashboard_checkout,        name='checkout'),
    # 알림센터
    path('', include(router.urls)),
]
