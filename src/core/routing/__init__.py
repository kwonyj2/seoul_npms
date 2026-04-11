from django.urls import re_path
from core.consumers import DashboardConsumer, IncidentConsumer, NotificationConsumer

websocket_urlpatterns = [
    re_path(r'ws/dashboard/$',           DashboardConsumer.as_asgi()),
    re_path(r'ws/incidents/(?P<incident_id>\d+)/$', IncidentConsumer.as_asgi()),
    re_path(r'ws/notifications/$',       NotificationConsumer.as_asgi()),
]
