"""
모바일 현장 UI URL 패턴
prefix: /mobile/
"""
from django.urls import path
from . import views

app_name = 'mobile'

urlpatterns = [
    path('',                    views.mobile_dashboard,       name='dashboard'),
    path('incidents/',          views.mobile_incident_list,   name='incident-list'),
    path('incidents/create/',   views.mobile_incident_create, name='incident-create'),
    path('incidents/<int:pk>/', views.mobile_incident_detail, name='incident-detail'),
    path('reports/cable/',      views.mobile_report_cable,    name='report-cable'),
    path('reports/switch/',     views.mobile_report_switch,   name='report-switch'),
    path('manifest.json',       views.mobile_manifest,        name='manifest'),
    path('sw.js',               views.mobile_sw,              name='sw'),
]
