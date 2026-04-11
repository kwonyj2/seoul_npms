from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'workforce'
router = DefaultRouter()
router.register(r'schedule-types', views.WorkScheduleTypeViewSet, basename='schedule-type')
router.register(r'schedules',      views.WorkScheduleViewSet,      basename='schedule')
router.register(r'attendance',     views.AttendanceLogViewSet,     basename='attendance')

urlpatterns = [
    path('', include(router.urls)),
    path('center-tree/',  views.center_worker_tree, name='center-tree'),
    path('today-kpi/',    views.today_schedule_kpi, name='today-kpi'),
    # 인력 관리 (현장기사 전용)
    path('worker-tree/',                                     views.worker_only_tree,   name='worker-tree'),
    path('workers/<int:worker_id>/profile/',                 views.worker_profile_api, name='worker-profile'),
    path('workers/<int:worker_id>/photo/',                   views.worker_photo_api,   name='worker-photo'),
    path('workers/<int:worker_id>/docs/',                    views.worker_docs_api,    name='worker-docs'),
]
