from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from core.error_views import custom_404, custom_500
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

handler404 = custom_404
handler500 = custom_500


def health_check(request):
    return JsonResponse({'status': 'ok', 'system': 'NPMS'})


# ─────────────────────────────────────────
# 템플릿 뷰 직접 임포트 (namespace 중복 방지)
# ─────────────────────────────────────────
from apps.accounts.views import LoginView, LogoutView, data_management_view
from apps.dashboard.views import index as dashboard_index, vworld_sdk_proxy
from apps.incidents.views import incident_list_view, incident_detail_view, incident_create_view, sla_view
from apps.schools.views import school_list_view, school_detail_view, school_map_view
from apps.workforce.views import schedule_view, attendance_view, worker_list_view
from apps.materials.views import materials_view
from apps.bulletin.views import bulletin_view
from apps.progress.views import progress_view
from apps.audit.views import audit_view
from apps.wbs.views import wbs_view
from apps.assets.views import assets_view
from apps.gps.views import gps_map_view
from apps.network.views import network_monitor_view, ap_analyzer_view
from apps.reports.views import (reports_view, performance_report_view,
                                performance_report_data_api, export_performance_excel)
from apps.nas.views import nas_view, deliverables_view, file_open_view
from apps.photos.views import photos_view
from apps.statistics.views import statistics_view, survey_respond
from apps.sysconfig.views import system_view, guide_view, guide_pptx_view
from apps.education.views import education_view
from apps.sysconfig.api import (
    system_info, module_matrix, nas_folders,
    user_role_update, user_active_toggle,
    update_module_min_role, update_module_role_perm, nas_role_perms,
    access_log, celery_status, backup_status,
    system_health, storage_usage, trigger_task,
)
from apps.sysconfig.security_api import (
    sec_dashboard, sec_blocked_ips, sec_block_config, sec_block_log,
    sec_login_analysis, sec_system_logs, sec_settings, sec_report,
)
from apps.sysconfig.exports import export_view
from apps.sysconfig.db_admin import db_schema, db_model_schema, db_crud, db_export
from apps.sysconfig.doc_viewer import doc_catalog, doc_data, doc_export as doc_excel_export
from core.permissions.roles import module_required

# ─────────────────────────────────────────
# 모듈 권한 적용 (MODULE_REGISTRY 기반)
# ─────────────────────────────────────────
incident_list_view      = module_required('incidents')(incident_list_view)
incident_create_view    = module_required('incidents')(incident_create_view)
incident_detail_view    = module_required('incidents')(incident_detail_view)
sla_view                = module_required('sla')(sla_view)
school_list_view        = module_required('schools')(school_list_view)
school_detail_view      = module_required('schools')(school_detail_view)
school_map_view         = module_required('school_map')(school_map_view)
worker_list_view        = module_required('worker_list')(worker_list_view)
schedule_view           = module_required('schedule')(schedule_view)
attendance_view         = module_required('attendance')(attendance_view)
gps_map_view            = module_required('gps')(gps_map_view)
materials_view          = module_required('materials')(materials_view)
assets_view             = module_required('assets')(assets_view)
network_monitor_view    = module_required('network')(network_monitor_view)
ap_analyzer_view        = module_required('ap_analyzer')(ap_analyzer_view)
progress_view           = module_required('progress')(progress_view)
audit_view              = module_required('audit')(audit_view)
wbs_view                = module_required('wbs')(wbs_view)
performance_report_view = module_required('performance')(performance_report_view)
reports_view            = module_required('reports')(reports_view)
statistics_view         = module_required('statistics')(statistics_view)
deliverables_view       = module_required('deliverables')(deliverables_view)
bulletin_view           = module_required('bulletin')(bulletin_view)
nas_view                = module_required('nas')(nas_view)
photos_view             = module_required('photos')(photos_view)
system_view             = module_required('system')(system_view)
education_view          = module_required('education')(education_view)


urlpatterns = [
    # 헬스체크
    path('health/', health_check),

    # Admin
    path('admin/', admin.site.urls),

    # ─────────────────────────────────────────
    # API 문서 (drf-spectacular)
    # ─────────────────────────────────────────
    path('api/schema/',  SpectacularAPIView.as_view(),      name='schema'),
    path('api/docs/',    SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/',   SpectacularRedocView.as_view(url_name='schema'),   name='redoc'),

    # ─────────────────────────────────────────
    # 앱별 REST API
    # ─────────────────────────────────────────
    path('api/accounts/',   include('apps.accounts.urls',   namespace='accounts')),
    path('api/schools/',    include('apps.schools.urls',    namespace='schools')),
    path('api/incidents/',  include('apps.incidents.urls',  namespace='incidents')),
    path('api/workforce/',  include('apps.workforce.urls',  namespace='workforce')),
    path('api/gps/',        include('apps.gps.urls',        namespace='gps')),
    path('api/materials/',  include('apps.materials.urls',  namespace='materials')),
    path('api/assets/',     include('apps.assets.urls',     namespace='assets')),
    path('api/network/',    include('apps.network.urls',    namespace='network')),
    path('api/reports/',    include('apps.reports.urls',    namespace='reports')),
    path('api/nas/',        include('apps.nas.urls',        namespace='nas')),
    path('api/photos/',     include('apps.photos.urls',     namespace='photos')),
    path('api/ai/',         include('apps.ai_engine.urls',  namespace='ai_engine')),
    path('api/statistics/', include('apps.statistics.urls', namespace='statistics')),
    path('api/dashboard/',  include('apps.dashboard.urls',  namespace='dashboard')),
    path('api/bulletin/',   include('apps.bulletin.urls',   namespace='bulletin')),
    path('api/progress/',   include('apps.progress.urls',   namespace='progress')),
    path('api/audit/',      include('apps.audit.urls',      namespace='audit')),
    path('api/wbs/',        include('apps.wbs.urls',        namespace='wbs')),
    path('api/education/',  include('apps.education.urls',  namespace='education')),

    # ─────────────────────────────────────────
    # 프론트엔드 템플릿 뷰 (직접 경로)
    # ─────────────────────────────────────────

    # 인증
    path('accounts/login/',  LoginView.as_view(),  name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),

    # 대시보드
    path('', dashboard_index, name='dashboard'),
    path('vworld-sdk.js', vworld_sdk_proxy, name='vworld-sdk'),

    # 장애
    path('incidents/list/',       incident_list_view,              name='incident-list'),
    path('incidents/create/',     incident_create_view,            name='incident-create'),
    path('incidents/<int:pk>/',   incident_detail_view,            name='incident-detail'),
    path('incidents/sla/',        sla_view,                        name='incident-sla'),

    # 학교
    path('schools/list/',         school_list_view,                name='school-list'),
    path('schools/map/',          school_map_view,                 name='school-map'),
    path('schools/<int:pk>/',     school_detail_view,              name='school-detail'),

    # 인력
    path('workforce/',            schedule_view,    name='workforce'),
    path('workforce/attendance/', attendance_view,  name='attendance'),
    path('workforce/workers/',    worker_list_view, name='worker-list'),

    # 자재/장비 (템플릿 뷰 — API는 /npms/api/materials/ 로 분리)
    path('materials/',            materials_view,                  name='materials'),
    path('bulletin/',             bulletin_view,                   name='bulletin'),
    path('progress/',             progress_view,                   name='progress'),
    path('audit/',                audit_view,                      name='audit'),
    path('wbs/',                  wbs_view,                        name='wbs'),
    path('assets/',               assets_view,                     name='assets'),

    # GPS / 네트워크 / 보고서 / NAS / 사진 / 통계
    path('gps/',                  gps_map_view,                    name='gps'),
    path('network/',              network_monitor_view,            name='network'),
    path('ap-analyzer/',          ap_analyzer_view,                name='ap-analyzer'),
    path('reports/',              reports_view,                    name='reports'),
    path('performance/',          performance_report_view,         name='performance'),
    path('performance/data/',     performance_report_data_api,     name='performance-data'),
    path('performance/export/',   export_performance_excel,        name='performance-export'),
    path('nas/',                  nas_view,                        name='nas'),
    path('nas/open/<str:token>/', file_open_view,                  name='nas-open'),
    path('deliverables/',         deliverables_view,               name='deliverables'),
    path('photos/',               photos_view,                     name='photos'),
    path('statistics/',           statistics_view,                 name='statistics'),

    # 만족도 응답 (인증 불필요)
    path('survey/respond/', survey_respond, name='survey-respond'),

    # 시스템 설정 (템플릿 뷰)
    path('system/',                system_view,          name='system'),
    # 사용 안내
    path('guide/',                              guide_view,      name='guide'),
    path('guide/pptx/<str:module_key>/',        guide_pptx_view, name='guide-pptx'),
    # 시스템 설정 API
    path('api/sysconfig/info/',                system_info,        name='sysconfig-info'),
    path('api/sysconfig/modules/',             module_matrix,      name='sysconfig-modules'),
    path('api/sysconfig/nas-folders/',         nas_folders,        name='sysconfig-nas-folders'),
    path('api/sysconfig/users/<int:user_id>/role/',   user_role_update,   name='sysconfig-user-role'),
    path('api/sysconfig/users/<int:user_id>/active/', user_active_toggle, name='sysconfig-user-active'),
    path('api/sysconfig/export/<str:module>/',        export_view,        name='sysconfig-export'),
    path('api/sysconfig/modules/<str:module_key>/min-role/', update_module_min_role, name='sysconfig-module-min-role'),
    path('api/sysconfig/modules/<str:module_key>/role-perm/', update_module_role_perm, name='sysconfig-module-role-perm'),
    path('api/sysconfig/nas-role-perms/',             nas_role_perms,     name='sysconfig-nas-role-perms'),
    path('api/sysconfig/access-log/',                 access_log,         name='sysconfig-access-log'),
    path('api/sysconfig/celery-status/',              celery_status,      name='sysconfig-celery-status'),
    path('api/sysconfig/backup-status/',              backup_status,      name='sysconfig-backup-status'),
    path('api/sysconfig/health/',                     system_health,      name='sysconfig-health'),
    path('api/sysconfig/storage/',                    storage_usage,      name='sysconfig-storage'),
    path('api/sysconfig/trigger-task/',               trigger_task,       name='sysconfig-trigger-task'),
    # 보안관제 API
    path('api/sysconfig/security/dashboard/',      sec_dashboard,      name='sec-dashboard'),
    path('api/sysconfig/security/blocked-ips/',    sec_blocked_ips,    name='sec-blocked-ips'),
    path('api/sysconfig/security/block-config/',   sec_block_config,   name='sec-block-config'),
    path('api/sysconfig/security/block-log/',      sec_block_log,      name='sec-block-log'),
    path('api/sysconfig/security/login-analysis/', sec_login_analysis, name='sec-login-analysis'),
    path('api/sysconfig/security/system-logs/',    sec_system_logs,    name='sec-system-logs'),
    path('api/sysconfig/security/settings/',       sec_settings,       name='sec-settings'),
    path('api/sysconfig/security/report/',         sec_report,         name='sec-report'),
    # DB 관리 (범용 CRUD)
    path('api/sysconfig/db/schema/',                              db_schema,        name='db-schema'),
    path('api/sysconfig/db/<str:app_label>/<str:model_name>/schema/', db_model_schema, name='db-model-schema'),
    # 산출물 통합 조회
    path('api/sysconfig/docs/catalog/',                     doc_catalog,      name='doc-catalog'),
    path('api/sysconfig/docs/<str:doc_id>/data/',           doc_data,         name='doc-data'),
    path('api/sysconfig/docs/<str:doc_id>/export/',         doc_excel_export, name='doc-export'),
    # DB 관리
    path('api/sysconfig/db/<str:app_label>/<str:model_name>/export/', db_export,    name='db-export'),
    path('api/sysconfig/db/<str:app_label>/<str:model_name>/',    db_crud,          name='db-crud-list'),
    path('api/sysconfig/db/<str:app_label>/<str:model_name>/<int:pk>/', db_crud,    name='db-crud-detail'),

    # 교육관리
    path('education/',            education_view,                  name='education'),

    # 모바일 현장 UI
    path('mobile/', include('apps.mobile.urls', namespace='mobile')),

    # 데이터 관리 (관리자 전용)
    path('admin/data-management/', data_management_view, name='data-management'),

    # QR 스캔 리다이렉트 (모바일 스캔 → 장비 상세)
    path('assets/scan/<str:tag>/', assets_view, name='asset-scan'),
]

# django-debug-toolbar (개발 환경 전용)
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    except ImportError:
        pass

# 개발 환경에서 미디어/정적 파일 제공
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
