"""
sysconfig API views
- system_info : 서버/DB/모듈 현황
- module_matrix : 역할×모듈 접근 매트릭스
- nas_folders : NAS 최상위 폴더 접근권한 목록/수정
"""
import platform
import django
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from core.permissions.roles import IsAdmin
from core.modules import MODULE_REGISTRY, ROLE_HIERARCHY, ROLE_LABELS, get_access_matrix


def _admin_required(view_func):
    """관리자 전용 데코레이터 (세션 인증)"""
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': '로그인 필요'}, status=401)
        if request.user.role not in ('superadmin', 'admin'):
            return JsonResponse({'error': '권한 없음'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@_admin_required
def system_info(request):
    """시스템 정보 API — DB별 레코드 수 + 서버 환경"""
    from django.db import connection

    # ── 모듈별 레코드 수 ────────────────────────────
    counts = {}
    try:
        from apps.schools.models import School, SchoolBuilding, SchoolContact
        counts['schools']   = School.objects.count()
        counts['buildings'] = SchoolBuilding.objects.count()
        counts['contacts']  = SchoolContact.objects.count()
    except Exception:
        pass
    try:
        from apps.incidents.models import Incident, IncidentCategory, SLARule
        counts['incidents']   = Incident.objects.count()
        counts['inc_cats']    = IncidentCategory.objects.count()
        counts['sla_rules']   = SLARule.objects.count()
    except Exception:
        pass
    try:
        from apps.assets.models import Asset
        counts['assets'] = Asset.objects.count()
    except Exception:
        pass
    try:
        from apps.materials.models import Material, WarehouseInventory
        counts['materials'] = Material.objects.count()
        counts['inventory'] = WarehouseInventory.objects.count()
    except Exception:
        pass
    try:
        from apps.accounts.models import User
        counts['users']   = User.objects.count()
        counts['workers'] = User.objects.filter(role='worker').count()
    except Exception:
        pass
    try:
        from apps.workforce.models import WorkerProfile
        counts['worker_profiles'] = WorkerProfile.objects.count()
    except Exception:
        pass
    try:
        from apps.nas.models import Folder, File
        counts['nas_folders'] = Folder.objects.count()
        counts['nas_files']   = File.objects.count()
    except Exception:
        pass
    try:
        from apps.photos.models import Photo
        counts['photos'] = Photo.objects.count()
    except Exception:
        pass

    # ── DB 용량 (PostgreSQL) ────────────────────────
    db_size = None
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            db_size = cur.fetchone()[0]
    except Exception:
        pass

    # ── PostgreSQL 버전 ─────────────────────────────
    pg_version = None
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT version()")
            pg_version = cur.fetchone()[0].split(',')[0]
    except Exception:
        pass

    return JsonResponse({
        'server': {
            'python':  platform.python_version(),
            'django':  django.__version__,
            'os':      f'{platform.system()} {platform.release()}',
            'db_size': db_size,
            'pg':      pg_version,
        },
        'counts': counts,
    })


@login_required
@_admin_required
def module_matrix(request):
    """역할×모듈 접근 매트릭스"""
    from apps.sysconfig.models import ModuleRolePerm
    from core.modules import can_access
    # DB에 저장된 독립 권한을 반영하여 매트릭스 구성
    matrix = {}
    db_perms = {(p.module_key, p.role): p.allowed for p in ModuleRolePerm.objects.all()}
    for role_obj in [{'key': r} for r in ROLE_HIERARCHY]:
        r = role_obj['key']
        matrix[r] = {}
        for k in MODULE_REGISTRY:
            if (k, r) in db_perms:
                matrix[r][k] = db_perms[(k, r)]
            else:
                matrix[r][k] = can_access(r, k)
    modules_info = [
        {'key': k, 'label': v['label'], 'icon': v['icon'], 'min_role': v['min_role']}
        for k, v in MODULE_REGISTRY.items()
    ]
    return JsonResponse({
        'roles':   [{'key': r, 'label': ROLE_LABELS.get(r, r)} for r in ROLE_HIERARCHY],
        'modules': modules_info,
        'matrix':  matrix,
    })


@login_required
@_admin_required
def nas_folders(request):
    """NAS 최상위 폴더 목록 + 접근권한 수정"""
    from apps.nas.models import Folder

    if request.method == 'GET':
        folders = Folder.objects.filter(parent__isnull=True).order_by('name').values(
            'id', 'name', 'full_path', 'access_level', 'is_system'
        )
        return JsonResponse({'folders': list(folders)})

    elif request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        folder_id = body.get('id')
        access_level = body.get('access_level')
        if not folder_id or access_level not in ('public', 'admin', 'superadmin'):
            return JsonResponse({'error': '잘못된 값'}, status=400)
        updated = Folder.objects.filter(id=folder_id).update(access_level=access_level)
        return JsonResponse({'updated': updated})

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@login_required
@_admin_required
def user_role_update(request, user_id):
    """사용자 역할 변경 (PATCH)"""
    if request.method != 'PATCH':
        return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)
    from apps.accounts.models import User
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    new_role = body.get('role')
    valid_roles = [k for k, _ in User.ROLE_CHOICES]
    if new_role not in valid_roles:
        return JsonResponse({'error': '유효하지 않은 역할'}, status=400)
    # superadmin 보호: 자기 자신 또는 다른 superadmin 역할 변경 불가 (superadmin만 가능)
    if request.user.role != 'superadmin' and new_role == 'superadmin':
        return JsonResponse({'error': '슈퍼관리자 역할은 슈퍼관리자만 부여 가능'}, status=403)
    rows = User.objects.filter(id=user_id).update(role=new_role)
    if not rows:
        return JsonResponse({'error': '사용자 없음'}, status=404)
    return JsonResponse({'ok': True, 'role': new_role})


@login_required
@_admin_required
def user_active_toggle(request, user_id):
    """사용자 활성/비활성 토글 (PATCH)"""
    if request.method != 'PATCH':
        return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)
    from apps.accounts.models import User
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    is_active = body.get('is_active')
    if is_active is None:
        return JsonResponse({'error': 'is_active 필요'}, status=400)
    rows = User.objects.filter(id=user_id).update(is_active=bool(is_active))
    return JsonResponse({'ok': True, 'is_active': bool(is_active)})


@login_required
@_admin_required
def update_module_min_role(request, module_key):
    """모듈 최소 역할 변경 (PATCH)"""
    if request.method != 'PATCH':
        return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)
    from core.modules import MODULE_REGISTRY, ROLE_HIERARCHY
    if module_key not in MODULE_REGISTRY:
        return JsonResponse({'error': '알 수 없는 모듈'}, status=404)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    min_role = body.get('min_role')
    if min_role not in ROLE_HIERARCHY:
        return JsonResponse({'error': '유효하지 않은 역할'}, status=400)
    from apps.sysconfig.models import ModuleConfig
    ModuleConfig.objects.update_or_create(
        module_key=module_key,
        defaults={'min_role': min_role},
    )
    return JsonResponse({'ok': True, 'module_key': module_key, 'min_role': min_role})


@login_required
@_admin_required
def update_module_role_perm(request, module_key):
    """모듈 역할별 독립 접근 권한 변경 (PATCH) — 계층 없이 역할별 개별 제어"""
    if request.method != 'PATCH':
        return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)
    from core.modules import MODULE_REGISTRY, ROLE_HIERARCHY
    if module_key not in MODULE_REGISTRY:
        return JsonResponse({'error': '알 수 없는 모듈'}, status=404)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    role    = body.get('role')
    allowed = body.get('allowed')
    if role not in ROLE_HIERARCHY or allowed is None:
        return JsonResponse({'error': '유효하지 않은 값'}, status=400)
    from apps.sysconfig.models import ModuleRolePerm
    ModuleRolePerm.objects.update_or_create(
        module_key=module_key, role=role,
        defaults={'allowed': bool(allowed)},
    )
    return JsonResponse({'ok': True, 'module_key': module_key, 'role': role, 'allowed': bool(allowed)})


@login_required
@_admin_required
def access_log(request):
    """접속이력 API — LoginHistory + UserActivityLog + 현재접속자"""
    from apps.accounts.models import LoginHistory, UserActivityLog, UserSession

    kind = request.GET.get('kind', 'login')  # login | activity | session
    page = max(1, int(request.GET.get('page', 1)))
    page_size = 50
    offset = (page - 1) * page_size

    # 검색 필터
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '')
    date_to   = request.GET.get('to', '')

    from django.db.models import Q
    if kind == 'login':
        qs = LoginHistory.objects.select_related('user').order_by('-created_at')
        if q:
            qs = qs.filter(
                Q(user__name__icontains=q) | Q(user__username__icontains=q)
                | Q(ip_address__icontains=q) | Q(attempted_username__icontains=q)
            )
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        total = qs.count()
        rows = []
        for r in qs[offset:offset + page_size]:
            rows.append({
                'id':          r.id,
                'username':    r.attempted_username or (r.user.username if r.user else '-'),
                'name':        r.user.name if r.user else '(미등록 계정)',
                'ip':          r.ip_address or '-',
                'user_agent':  r.user_agent[:80] if r.user_agent else '-',
                'success':     r.success,
                'fail_reason': r.fail_reason or '',
                'created_at':  r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

    elif kind == 'activity':
        qs = UserActivityLog.objects.select_related('user').order_by('-created_at')
        if q:
            qs = qs.filter(
                Q(user__name__icontains=q) | Q(user__username__icontains=q) | Q(target__icontains=q)
            )
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        total = qs.count()
        ACTION_KO = {
            'login': '로그인', 'logout': '로그아웃', 'create': '생성',
            'update': '수정',  'delete': '삭제',    'view': '조회',
            'download': '다운로드', 'upload': '업로드',
        }
        rows = []
        for r in qs[offset:offset + page_size]:
            rows.append({
                'id':         r.id,
                'username':   r.user.username if r.user else '-',
                'name':       r.user.name    if r.user else '-',
                'action':     ACTION_KO.get(r.action, r.action),
                'target':     r.target or '-',
                'detail':     r.detail[:100] if r.detail else '-',
                'ip':         r.ip_address or '-',
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

    elif kind == 'session':
        from django.utils import timezone as tz
        cutoff = tz.now() - __import__('datetime').timedelta(minutes=30)
        qs = UserSession.objects.select_related('user').filter(
            is_active=True, last_active__gte=cutoff
        ).order_by('-last_active')
        if q:
            qs = qs.filter(Q(user__name__icontains=q) | Q(user__username__icontains=q))
        total = qs.count()
        rows = []
        for r in qs[offset:offset + page_size]:
            rows.append({
                'id':           r.id,
                'username':     r.user.username if r.user else '-',
                'name':         r.user.name    if r.user else '-',
                'ip':           r.ip_address or '-',
                'current_page': r.current_page or '-',
                'login_at':     r.login_at.strftime('%Y-%m-%d %H:%M:%S'),
                'last_active':  r.last_active.strftime('%Y-%m-%d %H:%M:%S'),
            })

    elif kind == 'security':
        import datetime
        from django.db.models import Count, Max, Min
        from django.utils import timezone as tz

        # 기간 필터 (기본: 최근 7일)
        if date_from:
            since = datetime.datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
        else:
            since = tz.now() - datetime.timedelta(days=7)
        if date_to:
            until = datetime.datetime.strptime(date_to, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59, tzinfo=datetime.timezone.utc)
        else:
            until = tz.now()

        fail_qs = LoginHistory.objects.filter(
            success=False, created_at__gte=since, created_at__lte=until
        )
        if q:
            fail_qs = fail_qs.filter(
                Q(ip_address__icontains=q) | Q(attempted_username__icontains=q)
            )

        # IP별 실패 집계
        ip_stats = fail_qs.values('ip_address').annotate(
            fail_count=Count('id'),
            last_attempt=Max('created_at'),
            first_attempt=Min('created_at'),
        ).order_by('-fail_count')

        # 각 IP의 시도 계정 목록
        total = ip_stats.count()
        rows = []
        for row in ip_stats[offset:offset + page_size]:
            ip = row['ip_address']
            # 해당 IP에서 시도한 계정명 목록 (중복 제거)
            usernames = sorted(set(
                fail_qs.filter(ip_address=ip)
                .exclude(attempted_username='')
                .values_list('attempted_username', flat=True)
            ))[:10]
            # 해당 IP의 성공 이력 유무
            has_success = LoginHistory.objects.filter(
                ip_address=ip, success=True,
                created_at__gte=since, created_at__lte=until,
            ).exists()
            # 위험도 판정
            if row['fail_count'] >= 20:
                threat = 'critical'
            elif row['fail_count'] >= 10:
                threat = 'high'
            elif row['fail_count'] >= 5:
                threat = 'medium'
            else:
                threat = 'low'

            rows.append({
                'ip':             ip or '-',
                'fail_count':     row['fail_count'],
                'attempted_users': ', '.join(u for u in usernames if u) or '-',
                'has_success':    has_success,
                'threat':         threat,
                'first_attempt':  row['first_attempt'].strftime('%Y-%m-%d %H:%M'),
                'last_attempt':   row['last_attempt'].strftime('%Y-%m-%d %H:%M'),
            })

        # 요약 통계
        total_fails = fail_qs.count()
        total_success = LoginHistory.objects.filter(
            success=True, created_at__gte=since, created_at__lte=until,
        ).count()
        unknown_user_fails = fail_qs.filter(user__isnull=True).count()
        locked_count = fail_qs.filter(fail_reason__icontains='잠금').count()

        return JsonResponse({
            'rows': rows,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'summary': {
                'period': f'{since.strftime("%Y-%m-%d")} ~ {until.strftime("%Y-%m-%d")}',
                'total_fails': total_fails,
                'total_success': total_success,
                'unique_ips': total,
                'unknown_user_fails': unknown_user_fails,
                'locked_count': locked_count,
            },
        })

    else:
        return JsonResponse({'error': '잘못된 kind'}, status=400)

    return JsonResponse({
        'rows': rows,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
    })


@login_required
@_admin_required
def nas_role_perms(request):
    """역할별 NAS 행위 권한 조회/수정"""
    from apps.sysconfig.models import NasRoleConfig
    from core.modules import ROLE_HIERARCHY
    ACTIONS = ['upload', 'delete', 'create_folder']
    DEFAULTS = {
        ('superadmin', 'upload'): True,  ('superadmin', 'delete'): True,  ('superadmin', 'create_folder'): True,
        ('admin',      'upload'): True,  ('admin',      'delete'): True,  ('admin',      'create_folder'): True,
        ('worker',     'upload'): True,  ('worker',     'delete'): False, ('worker',     'create_folder'): False,
        ('resident',   'upload'): False, ('resident',   'delete'): False, ('resident',   'create_folder'): False,
        ('customer',   'upload'): False, ('customer',   'delete'): False, ('customer',   'create_folder'): False,
    }
    if request.method == 'GET':
        db_perms = {(p.role, p.action): p.allowed for p in NasRoleConfig.objects.all()}
        result = {}
        for role in ROLE_HIERARCHY:
            result[role] = {
                action: db_perms.get((role, action), DEFAULTS.get((role, action), False))
                for action in ACTIONS
            }
        return JsonResponse({'perms': result, 'actions': ACTIONS, 'roles': ROLE_HIERARCHY})

    elif request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        role   = body.get('role')
        action = body.get('action')
        allowed = body.get('allowed')
        if role not in ROLE_HIERARCHY or action not in ACTIONS or allowed is None:
            return JsonResponse({'error': '잘못된 값'}, status=400)
        NasRoleConfig.objects.update_or_create(
            role=role, action=action,
            defaults={'allowed': bool(allowed)},
        )
        return JsonResponse({'ok': True, 'role': role, 'action': action, 'allowed': bool(allowed)})

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@login_required
@_admin_required
def celery_status(request):
    """Celery 워커 상태 + 스케줄 + 태스크 이력"""
    from django.conf import settings
    from config.celery import app as celery_app

    flower_url = getattr(settings, 'FLOWER_URL', '/npms/flower/')
    broker = settings.CELERY_BROKER_URL

    # ── 워커 상태 ────────────────────────────
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        active = inspector.active() or {}
        workers = [
            {'name': name, 'tasks': len(tasks)}
            for name, tasks in active.items()
        ]
    except Exception:
        workers = []

    # ── Beat 스케줄 ──────────────────────────
    TASK_LABELS = {
        'apps.nas.tasks.sync_nas_filesystem': 'NAS 파일 동기화',
        'apps.nas.tasks.bulk_ocr_extract':    'OCR 일괄 추출',
        'apps.schools.tasks.scan_vsdx_folder':'VSDX 구성도 파싱',
        'apps.schools.tasks.sync_pms_contacts':'PMS 담당자 동기화',
        'core.tasks.backup_database':          'DB 백업',
        'apps.nas.tasks.purge_old_trash':      '휴지통 정리',
    }
    beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
    schedules = []
    for name, conf in beat_schedule.items():
        task_path = conf.get('task', '')
        sched = conf.get('schedule')
        if isinstance(sched, (int, float)):
            secs = int(sched)
            if secs >= 3600:
                interval = f'{secs // 3600}시간마다'
            elif secs >= 60:
                interval = f'{secs // 60}분마다'
            else:
                interval = f'{secs}초마다'
        elif hasattr(sched, 'run_every'):
            secs = int(sched.run_every.total_seconds())
            if secs >= 3600:
                interval = f'{secs // 3600}시간마다'
            elif secs >= 60:
                interval = f'{secs // 60}분마다'
            else:
                interval = f'{secs}초마다'
        elif hasattr(sched, 'minute'):
            m = ','.join(str(x) for x in sorted(sched.minute)) if sched.minute != {0} else '0'
            h = ','.join(str(x) for x in sorted(sched.hour)) if sched.hour else '*'
            interval = f'매일 {h}:{m.zfill(2)}'
        else:
            interval = str(sched)
        schedules.append({
            'name': name,
            'task': task_path,
            'label': TASK_LABELS.get(task_path, task_path.split('.')[-1]),
            'interval': interval,
        })

    # ── 태스크 실행 이력 (django-celery-results) ──
    page = max(1, int(request.GET.get('page', 1)))
    page_size = 30
    offset = (page - 1) * page_size
    task_filter = request.GET.get('task', '')
    status_filter = request.GET.get('status', '')

    task_rows = []
    task_total = 0
    task_summary = {}
    try:
        from django_celery_results.models import TaskResult
        from django.db.models import Count
        qs = TaskResult.objects.order_by('-date_done')
        if task_filter:
            qs = qs.filter(task_name__icontains=task_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)
        task_total = qs.count()

        for r in qs[offset:offset + page_size]:
            task_rows.append({
                'id':        r.id,
                'task':      TASK_LABELS.get(r.task_name, r.task_name.split('.')[-1] if r.task_name else '-'),
                'task_name': r.task_name or '-',
                'status':    r.status,
                'date_done': r.date_done.strftime('%Y-%m-%d %H:%M:%S') if r.date_done else '-',
                'runtime':   f'{r.result[:60]}' if r.result and r.status == 'FAILURE' else (
                             f'{float(r.result):.1f}초' if r.result and r.result.replace('.','',1).isdigit() else '-'),
                'worker':    r.worker or '-',
            })

        # 상태별 집계
        status_counts = dict(TaskResult.objects.values_list('status').annotate(cnt=Count('id')))
        task_summary = {
            'total':   TaskResult.objects.count(),
            'success': status_counts.get('SUCCESS', 0),
            'failure': status_counts.get('FAILURE', 0),
            'pending': status_counts.get('PENDING', 0),
            'started': status_counts.get('STARTED', 0),
        }
    except Exception:
        pass

    return JsonResponse({
        'broker': broker.split('@')[-1] if '@' in broker else broker,
        'flower_url': flower_url,
        'workers': workers,
        'worker_count': len(workers),
        'schedules': schedules,
        'tasks': {
            'rows': task_rows,
            'total': task_total,
            'page': page,
            'page_size': page_size,
            'total_pages': (task_total + page_size - 1) // page_size,
        },
        'task_summary': task_summary,
    })


@login_required
@_admin_required
def system_health(request):
    """시스템 헬스 API — CPU·메모리·디스크 현황"""
    import psutil
    try:
        cpu = psutil.cpu_percent(interval=0.5)
    except Exception:
        cpu = None
    try:
        mem = psutil.virtual_memory()
        memory = {
            'total_gb': round(mem.total / 1024**3, 1),
            'used_gb':  round(mem.used  / 1024**3, 1),
            'percent':  mem.percent,
        }
    except Exception:
        memory = {}
    try:
        disk = psutil.disk_usage('/')
        disk_info = {
            'total_gb': round(disk.total / 1024**3, 1),
            'used_gb':  round(disk.used  / 1024**3, 1),
            'percent':  disk.percent,
        }
    except Exception:
        disk_info = {}

    return JsonResponse({
        'cpu':    cpu,
        'memory': memory,
        'disk':   disk_info,
    })


@login_required
@_admin_required
def storage_usage(request):
    """NAS 스토리지 사용량"""
    import shutil
    from django.conf import settings as _settings
    nas_path = getattr(_settings, 'NAS_MEDIA_ROOT', '/mnt/lvm-cache/nas/media/npms')

    try:
        total, used, free = shutil.disk_usage(nas_path)
        return JsonResponse({
            'nas_path':  nas_path,
            'total_gb':  round(total / 1024**3, 1),
            'used_gb':   round(used  / 1024**3, 1),
            'free_gb':   round(free  / 1024**3, 1),
            'percent':   round(used / total * 100, 1) if total else 0,
            'total': f'{total / 1024**3:.1f} GB',
            'used':  f'{used  / 1024**3:.1f} GB',
        })
    except Exception as e:
        return JsonResponse({
            'nas_path': nas_path,
            'total': 'N/A', 'used': 'N/A',
            'error': str(e),
        })


# 허용된 태스크 목록 (임의 태스크 실행 방지)
_ALLOWED_TASKS = {
    'sync_nas_filesystem':   'apps.nas.tasks.sync_nas_filesystem',
    'bulk_ocr_extract':      'apps.nas.tasks.bulk_ocr_extract',
    'scan_vsdx_folder':      'apps.schools.tasks.scan_vsdx_folder',
    'sync_pms_contacts':     'apps.schools.tasks.sync_pms_contacts',
    'backup_database':       'core.tasks.backup_database',
}


@login_required
@_admin_required
def trigger_task(request):
    """배치 작업 수동 트리거 (POST)"""
    if request.method != 'POST':
        return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    task_name = body.get('task', '')
    if task_name not in _ALLOWED_TASKS:
        return JsonResponse({
            'error': f'알 수 없는 태스크: {task_name}',
            'allowed': list(_ALLOWED_TASKS.keys()),
        }, status=400)

    task_path = _ALLOWED_TASKS[task_name]
    try:
        module_path, func_name = task_path.rsplit('.', 1)
        import importlib
        module = importlib.import_module(module_path)
        task = getattr(module, func_name)
        result = task.delay()
        return JsonResponse({'ok': True, 'task': task_name, 'task_id': str(result.id)})
    except Exception as e:
        return JsonResponse({'error': f'태스크 실행 실패: {e}'}, status=500)


@login_required
@_admin_required
def backup_status(request):
    """백업 파일 목록 및 상태 조회"""
    import glob
    import os
    from django.conf import settings

    backup_dir = getattr(settings, 'DB_BACKUP_DIR', '/home/kwonyj/network_pms/backups')
    keep_days  = getattr(settings, 'DB_BACKUP_KEEP_DAYS', 30)

    pattern = os.path.join(backup_dir, 'npms_db_*.sql.gz')
    files = sorted(glob.glob(pattern), reverse=True)

    backups = []
    for f in files[:20]:
        stat = os.stat(f)
        size = stat.st_size
        size_str = (f'{size/1024:.1f} KB' if size < 1024*1024
                    else f'{size/1024/1024:.1f} MB')
        backups.append({
            'filename': os.path.basename(f),
            'size': size_str,
            'created_at': __import__('datetime').datetime.fromtimestamp(
                stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })

    return JsonResponse({
        'backup_dir': backup_dir,
        'keep_days': keep_days,
        'total': len(files),
        'backups': backups,
    })
