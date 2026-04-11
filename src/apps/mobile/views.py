"""
모바일 현장 UI 뷰
현장 작업자 전용 단순화 페이지
"""
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required


@login_required(login_url='/npms/accounts/login/')
def mobile_dashboard(request):
    return render(request, 'mobile/dashboard.html')


@login_required(login_url='/npms/accounts/login/')
def mobile_incident_list(request):
    return render(request, 'mobile/incident_list.html')


@login_required(login_url='/npms/accounts/login/')
def mobile_incident_create(request):
    from apps.incidents.models import Incident
    return render(request, 'mobile/incident_create.html', {
        'priority_choices':       Incident.PRIORITY_CHOICES,
        'fault_type_choices':     Incident.FAULT_TYPE_CHOICES,
        'contact_method_choices': Incident.CONTACT_METHOD_CHOICES,
    })


@login_required(login_url='/npms/accounts/login/')
def mobile_incident_detail(request, pk):
    from apps.incidents.models import Incident
    from apps.photos.models import Photo
    return render(request, 'mobile/incident_detail.html', {
        'pk': pk,
        'status_labels': dict(Incident.STATUS_CHOICES),
        'next_status': {
            'assigned':   'moving',
            'moving':     'arrived',
            'arrived':    'processing',
            'processing': 'completed',
        },
        'photo_stage_choices': Photo.PHOTO_STAGE_CHOICES,
    })


@login_required(login_url='/npms/accounts/login/')
def mobile_report_cable(request):
    from apps.reports.models import ReportTemplate
    tmpl = ReportTemplate.objects.filter(report_type='cable', is_active=True).first()
    return render(request, 'mobile/report_cable.html', {
        'template_id': tmpl.id if tmpl else '',
        'template_name': tmpl.name if tmpl else '소규모 네트워크 포설 확인서',
        'report_type': 'cable',
    })


def mobile_manifest(request):
    manifest = {
        "name": "NPMS 현장",
        "short_name": "NPMS",
        "description": "네트워크 장애관리 현장 시스템",
        "start_url": "/npms/mobile/",
        "scope": "/npms/mobile/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#1a5fa8",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/npms/static/mobile/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/npms/static/mobile/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return JsonResponse(manifest)


def mobile_sw(request):
    sw = """
const CACHE_NAME = 'npms-mobile-v1';
const OFFLINE_URL = '/npms/mobile/';

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.add(OFFLINE_URL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
  }
});
""".strip()
    return HttpResponse(sw, content_type='application/javascript; charset=utf-8')


@login_required(login_url='/npms/accounts/login/')
def mobile_report_switch(request):
    from apps.reports.models import ReportTemplate
    tmpl = ReportTemplate.objects.filter(report_type='switch_install', is_active=True).first()
    return render(request, 'mobile/report_switch.html', {
        'template_id': tmpl.id if tmpl else '',
        'template_name': tmpl.name if tmpl else '스위치 설치 확인서',
        'report_type': 'switch_install',
    })
