from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    StatisticsDailyViewSet, StatisticsMonthlyViewSet,
    SLARecordViewSet, SatisfactionSurveyViewSet,
    survey_respond, comprehensive_stats_api, comprehensive_stats_excel,
    pattern_api,
)

app_name = 'statistics'

router = DefaultRouter()
router.register(r'daily',       StatisticsDailyViewSet,    basename='stats-daily')
router.register(r'monthly',     StatisticsMonthlyViewSet,  basename='stats-monthly')
router.register(r'sla',         SLARecordViewSet,          basename='sla-record')
router.register(r'satisfaction',SatisfactionSurveyViewSet, basename='satisfaction')

urlpatterns = router.urls + [
    path('survey/respond/',        survey_respond,            name='survey-respond'),
    path('comprehensive/',         comprehensive_stats_api,   name='comprehensive'),
    path('comprehensive/excel/',   comprehensive_stats_excel, name='comprehensive-excel'),
    path('pattern/',               pattern_api,               name='pattern'),
]
