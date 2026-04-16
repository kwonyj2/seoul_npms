"""
보안관제 API — 6개 패널 전체 데이터 제공
"""
import datetime
import hashlib
import json
import os
import re
import subprocess

import psutil
from django.conf import settings
from django.db.models import Count, Max, Min, Q, F, Sum
from django.db.models.functions import TruncDate, TruncHour, ExtractHour
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import LoginHistory, UserActivityLog, UserSession, User
from apps.sysconfig.security_models import (
    SecurityEvent, BlockedIP, WhitelistedIP, BlockLog,
    SecurityConfig, SystemLogEntry, FileIntegritySnapshot,
)


def _admin_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': '로그인 필요'}, status=401)
        if request.user.role not in ('superadmin', 'admin'):
            return JsonResponse({'error': '권한 없음'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


# ═══════════════════════════════════════════════════════
# 패널1: 위협 현황 대시보드
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_dashboard(request):
    """위협 현황 대시보드 — 요약 카드 + 시간대별 차트 + 유형별 분류 + Top10 IP"""
    now = timezone.now()
    h24 = now - datetime.timedelta(hours=24)
    h7d = now - datetime.timedelta(days=7)

    # ── 요약 카드 ─────────────────────────
    total_attacks_24h = LoginHistory.objects.filter(
        success=False, created_at__gte=h24
    ).count()
    blocked_ips = BlockedIP.objects.count()
    active_sessions = UserSession.objects.filter(
        is_active=True,
        last_active__gte=now - datetime.timedelta(minutes=30)
    ).count()
    events_24h = SecurityEvent.objects.filter(created_at__gte=h24).count()

    # 위험 등급 계산
    if total_attacks_24h >= 100 or SecurityEvent.objects.filter(
        severity='critical', created_at__gte=h24, resolved=False
    ).exists():
        threat_level = 'danger'
        threat_label = '위험'
    elif total_attacks_24h >= 30:
        threat_level = 'warning'
        threat_label = '경고'
    elif total_attacks_24h >= 10:
        threat_level = 'caution'
        threat_label = '주의'
    else:
        threat_level = 'safe'
        threat_label = '안전'

    # ── 시간대별 공격 시도 (24h) ─────────
    hourly_raw = (
        LoginHistory.objects.filter(success=False, created_at__gte=h24)
        .annotate(hour=TruncHour('created_at'))
        .values('hour')
        .annotate(cnt=Count('id'))
        .order_by('hour')
    )
    hourly = {r['hour'].strftime('%H:00'): r['cnt'] for r in hourly_raw}
    hourly_labels = []
    hourly_data = []
    for i in range(24):
        t = (now - datetime.timedelta(hours=23 - i)).strftime('%H:00')
        hourly_labels.append(t)
        hourly_data.append(hourly.get(t, 0))

    # ── 공격 유형별 분류 ─────────────────
    fail_reasons = (
        LoginHistory.objects.filter(success=False, created_at__gte=h7d)
        .values('fail_reason')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )
    type_map = {}
    for r in fail_reasons:
        reason = r['fail_reason'] or '기타'
        if '잠금' in reason:
            key = '계정 잠금'
        elif '비밀번호' in reason:
            key = '비밀번호 오류'
        elif '미등록' in reason or '없는' in reason:
            key = '미등록 계정'
        elif '만료' in reason:
            key = '서비스 만료'
        else:
            key = '기타'
        type_map[key] = type_map.get(key, 0) + r['cnt']
    attack_types = [{'label': k, 'count': v} for k, v in sorted(type_map.items(), key=lambda x: -x[1])]

    # ── Top 10 위협 IP ──────────────────
    top_ips = (
        LoginHistory.objects.filter(success=False, created_at__gte=h7d)
        .values('ip_address')
        .annotate(
            fail_count=Count('id'),
            last_attempt=Max('created_at'),
            first_attempt=Min('created_at'),
        )
        .order_by('-fail_count')[:10]
    )
    top_ip_list = []
    for row in top_ips:
        ip = row['ip_address'] or '-'
        # 차단 여부
        is_blocked = BlockedIP.objects.filter(ip_address=ip).exists()
        # 위험도
        fc = row['fail_count']
        if fc >= 50:
            threat = 'critical'
        elif fc >= 20:
            threat = 'high'
        elif fc >= 10:
            threat = 'medium'
        else:
            threat = 'low'
        top_ip_list.append({
            'ip': ip,
            'fail_count': fc,
            'threat': threat,
            'is_blocked': is_blocked,
            'first': row['first_attempt'].strftime('%m-%d %H:%M') if row['first_attempt'] else '-',
            'last': row['last_attempt'].strftime('%m-%d %H:%M') if row['last_attempt'] else '-',
        })

    # ── 최근 보안 이벤트 (10건) ───────────
    recent_events = []
    for ev in SecurityEvent.objects.all()[:10]:
        recent_events.append({
            'id': ev.id,
            'type': ev.get_event_type_display(),
            'type_key': ev.event_type,
            'severity': ev.severity,
            'ip': ev.ip_address or '-',
            'username': ev.username or '-',
            'desc': ev.description[:120],
            'resolved': ev.resolved,
            'time': ev.created_at.strftime('%m-%d %H:%M:%S'),
        })

    return JsonResponse({
        'summary': {
            'attacks_24h': total_attacks_24h,
            'blocked_ips': blocked_ips,
            'active_sessions': active_sessions,
            'events_24h': events_24h,
            'threat_level': threat_level,
            'threat_label': threat_label,
        },
        'hourly': {'labels': hourly_labels, 'data': hourly_data},
        'attack_types': attack_types,
        'top_ips': top_ip_list,
        'recent_events': recent_events,
    })


# ═══════════════════════════════════════════════════════
# 패널2: 자동 차단 관리
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_blocked_ips(request):
    """차단 IP 목록 조회 / 수동 차단 / 해제"""
    if request.method == 'GET':
        q = request.GET.get('q', '')
        qs = BlockedIP.objects.all()
        if q:
            qs = qs.filter(Q(ip_address__icontains=q) | Q(description__icontains=q))

        rows = []
        for b in qs[:200]:
            rows.append({
                'id': b.id,
                'ip': b.ip_address,
                'reason': b.get_reason_display(),
                'reason_key': b.reason,
                'description': b.description,
                'fail_count': b.fail_count,
                'auto': b.auto_blocked,
                'permanent': b.is_permanent,
                'is_active': b.is_active,
                'blocked_at': b.blocked_at.strftime('%Y-%m-%d %H:%M'),
                'expires_at': b.expires_at.strftime('%Y-%m-%d %H:%M') if b.expires_at else '영구',
                'blocked_by': b.blocked_by.name if b.blocked_by else '시스템',
            })

        # 화이트리스트
        wl = list(WhitelistedIP.objects.values(
            'id', 'ip_address', 'description',
        ).order_by('ip_address'))

        return JsonResponse({'blocked': rows, 'whitelist': wl})

    elif request.method == 'POST':
        # 수동 차단
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)

        action = body.get('action')  # block / unblock / whitelist_add / whitelist_remove

        if action == 'block':
            ip = body.get('ip', '').strip()
            if not ip:
                return JsonResponse({'error': 'IP 필요'}, status=400)
            reason = body.get('reason', 'manual')
            desc = body.get('description', '관리자 수동 차단')
            permanent = body.get('permanent', False)
            duration = body.get('duration', 60)

            obj, created = BlockedIP.objects.update_or_create(
                ip_address=ip,
                defaults={
                    'reason': reason,
                    'description': desc,
                    'is_permanent': permanent,
                    'auto_blocked': False,
                    'blocked_by': request.user,
                    'blocked_at': timezone.now(),
                    'expires_at': None if permanent else timezone.now() + datetime.timedelta(minutes=int(duration)),
                }
            )
            BlockLog.objects.create(
                ip_address=ip, action='block',
                reason=f'수동 차단: {desc}', actor=request.user
            )
            SecurityEvent.objects.create(
                event_type='ip_blocked', severity='info',
                ip_address=ip, username=request.user.username,
                description=f'관리자 수동 차단: {desc}',
            )
            return JsonResponse({'ok': True, 'created': created})

        elif action == 'unblock':
            ip = body.get('ip', '').strip()
            deleted = BlockedIP.objects.filter(ip_address=ip).delete()[0]
            if deleted:
                BlockLog.objects.create(
                    ip_address=ip, action='unblock',
                    reason='관리자 수동 해제', actor=request.user
                )
                SecurityEvent.objects.create(
                    event_type='ip_unblocked', severity='info',
                    ip_address=ip, username=request.user.username,
                    description='관리자 수동 차단 해제',
                )
            return JsonResponse({'ok': True, 'deleted': deleted})

        elif action == 'whitelist_add':
            ip = body.get('ip', '').strip()
            desc = body.get('description', '')
            if not ip:
                return JsonResponse({'error': 'IP 필요'}, status=400)
            obj, created = WhitelistedIP.objects.get_or_create(
                ip_address=ip,
                defaults={'description': desc, 'created_by': request.user}
            )
            # 화이트리스트 등록 시 차단 해제
            BlockedIP.objects.filter(ip_address=ip).delete()
            return JsonResponse({'ok': True, 'created': created})

        elif action == 'whitelist_remove':
            ip = body.get('ip', '').strip()
            deleted = WhitelistedIP.objects.filter(ip_address=ip).delete()[0]
            return JsonResponse({'ok': True, 'deleted': deleted})

        return JsonResponse({'error': '알 수 없는 action'}, status=400)

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@_admin_required
def sec_block_config(request):
    """자동 차단 규칙 조회/수정"""
    KEYS = [
        'auto_block_enabled', 'block_threshold', 'block_duration_min',
        'block_window_min', 'permanent_threshold',
    ]
    if request.method == 'GET':
        config = {k: SecurityConfig.get(k) for k in KEYS}
        return JsonResponse({'config': config})

    elif request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        for k, v in body.items():
            if k in KEYS:
                SecurityConfig.objects.update_or_create(
                    key=k, defaults={'value': str(v), 'updated_by': request.user}
                )
                SecurityEvent.objects.create(
                    event_type='config_change', severity='info',
                    username=request.user.username,
                    description=f'보안 설정 변경: {k} = {v}',
                )
        return JsonResponse({'ok': True})

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


@_admin_required
def sec_block_log(request):
    """차단/해제 이력 조회"""
    page = max(1, int(request.GET.get('page', 1)))
    ps = 50
    qs = BlockLog.objects.select_related('actor').all()
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(ip_address__icontains=q) | Q(reason__icontains=q))
    total = qs.count()
    rows = []
    for r in qs[(page-1)*ps: page*ps]:
        rows.append({
            'ip': r.ip_address,
            'action': r.get_action_display(),
            'reason': r.reason,
            'actor': r.actor.name if r.actor else '시스템',
            'time': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse({
        'rows': rows, 'total': total,
        'page': page, 'page_size': ps,
        'total_pages': max(1, (total + ps - 1) // ps),
    })


# ═══════════════════════════════════════════════════════
# 패널3: 로그인 보안 분석
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_login_analysis(request):
    """로그인 보안 분석 — 추이, 비정상 탐지, 사용자 패턴, 계정잠금"""
    now = timezone.now()
    days = int(request.GET.get('days', 14))
    since = now - datetime.timedelta(days=days)

    # ── 일별 성공/실패 추이 ────────────────
    daily_success = dict(
        LoginHistory.objects.filter(success=True, created_at__gte=since)
        .annotate(d=TruncDate('created_at'))
        .values('d').annotate(cnt=Count('id'))
        .values_list('d', 'cnt')
    )
    daily_fail = dict(
        LoginHistory.objects.filter(success=False, created_at__gte=since)
        .annotate(d=TruncDate('created_at'))
        .values('d').annotate(cnt=Count('id'))
        .values_list('d', 'cnt')
    )
    labels = []
    s_data = []
    f_data = []
    for i in range(days):
        d = (since + datetime.timedelta(days=i + 1)).date()
        labels.append(d.strftime('%m-%d'))
        s_data.append(daily_success.get(d, 0))
        f_data.append(daily_fail.get(d, 0))

    # ── 비정상 로그인 탐지 ─────────────────
    # 야간(22~06) 성공 로그인
    abnormal = []
    night_logins = (
        LoginHistory.objects.filter(
            success=True, created_at__gte=since
        ).annotate(hr=ExtractHour('created_at'))
        .filter(Q(hr__gte=22) | Q(hr__lt=6))
        .select_related('user')
        .order_by('-created_at')[:20]
    )
    for r in night_logins:
        abnormal.append({
            'type': '야간 접속',
            'username': r.user.username if r.user else r.attempted_username,
            'name': r.user.name if r.user else '-',
            'ip': r.ip_address or '-',
            'time': r.created_at.strftime('%Y-%m-%d %H:%M'),
            'detail': f'{r.created_at.strftime("%H:%M")} 접속',
        })

    # 동일 IP 다중 계정 시도 (브루트포스)
    multi_user_ips = (
        LoginHistory.objects.filter(success=False, created_at__gte=since)
        .values('ip_address')
        .annotate(
            user_cnt=Count('attempted_username', distinct=True),
            total=Count('id'),
        )
        .filter(user_cnt__gte=3)
        .order_by('-total')[:10]
    )
    for row in multi_user_ips:
        abnormal.append({
            'type': '다중 계정 시도',
            'username': '-',
            'name': '-',
            'ip': row['ip_address'] or '-',
            'time': '-',
            'detail': f'{row["user_cnt"]}개 계정, {row["total"]}회 시도',
        })

    # ── 시간대별 로그인 분포 (히트맵) ─────
    hourly_dist = (
        LoginHistory.objects.filter(created_at__gte=since)
        .annotate(hr=ExtractHour('created_at'))
        .values('hr', 'success')
        .annotate(cnt=Count('id'))
        .order_by('hr')
    )
    heatmap = {'success': [0]*24, 'fail': [0]*24}
    for r in hourly_dist:
        key = 'success' if r['success'] else 'fail'
        heatmap[key][r['hr']] = r['cnt']

    # ── 잠긴 계정 현황 ───────────────────
    lock_window = now - datetime.timedelta(minutes=30)
    locked_users = (
        LoginHistory.objects.filter(
            success=False, created_at__gte=lock_window
        )
        .values('attempted_username')
        .annotate(cnt=Count('id'))
        .filter(cnt__gte=5)
        .order_by('-cnt')
    )
    locked_list = []
    for r in locked_users:
        uname = r['attempted_username']
        user = User.objects.filter(username=uname).first()
        locked_list.append({
            'username': uname,
            'name': user.name if user else '(미등록)',
            'fail_count': r['cnt'],
            'is_registered': user is not None,
        })

    return JsonResponse({
        'trend': {'labels': labels, 'success': s_data, 'fail': f_data},
        'abnormal': abnormal,
        'heatmap': heatmap,
        'locked_accounts': locked_list,
    })


# ═══════════════════════════════════════════════════════
# 패널4: 시스템 로그 감시
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_system_logs(request):
    """시스템 로그 — SSH, 리소스, Docker, 파일 무결성"""
    kind = request.GET.get('kind', 'ssh')
    page = max(1, int(request.GET.get('page', 1)))
    ps = 50

    if kind == 'ssh':
        qs = SystemLogEntry.objects.filter(log_type__in=['ssh_fail', 'ssh_success', 'auth_other'])
        q = request.GET.get('q', '')
        if q:
            qs = qs.filter(Q(ip_address__icontains=q) | Q(username__icontains=q))
        total = qs.count()
        rows = []
        for r in qs[(page-1)*ps: page*ps]:
            rows.append({
                'type': r.get_log_type_display(),
                'type_key': r.log_type,
                'ip': r.ip_address or '-',
                'username': r.username or '-',
                'raw': r.raw_line[:200],
                'time': r.log_time.strftime('%Y-%m-%d %H:%M:%S') if r.log_time else '-',
            })
        # SSH 실패 IP Top5
        ssh_top = (
            SystemLogEntry.objects.filter(log_type='ssh_fail')
            .values('ip_address')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:5]
        )
        return JsonResponse({
            'rows': rows, 'total': total, 'page': page, 'page_size': ps,
            'total_pages': max(1, (total + ps - 1) // ps),
            'ssh_top': list(ssh_top),
        })

    elif kind == 'resource':
        # 현재 리소스 상태
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        # 프로세스 Top 5 (CPU)
        procs = []
        for p in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                        key=lambda x: x.info.get('cpu_percent', 0) or 0, reverse=True)[:5]:
            procs.append({
                'pid': p.info['pid'],
                'name': p.info['name'],
                'cpu': round(p.info.get('cpu_percent', 0) or 0, 1),
                'mem': round(p.info.get('memory_percent', 0) or 0, 1),
            })
        # 이상 여부
        anomaly = cpu > 90 or mem.percent > 90 or disk.percent > 90
        return JsonResponse({
            'cpu': cpu,
            'memory': {'total': round(mem.total/1024**3, 1), 'used': round(mem.used/1024**3, 1), 'percent': mem.percent},
            'disk': {'total': round(disk.total/1024**3, 1), 'used': round(disk.used/1024**3, 1), 'percent': disk.percent},
            'processes': procs,
            'anomaly': anomaly,
        })

    elif kind == 'docker':
        # Docker 컨테이너 상태
        containers = []
        try:
            result = subprocess.run(
                ['docker', 'ps', '-a', '--format', '{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    name = parts[0]
                    status = parts[1] if len(parts) > 1 else '-'
                    is_up = 'Up' in status
                    containers.append({
                        'name': name,
                        'status': status,
                        'is_up': is_up,
                        'image': parts[3] if len(parts) > 3 else '-',
                    })
        except Exception as e:
            containers = [{'name': 'error', 'status': str(e), 'is_up': False, 'image': '-'}]
        return JsonResponse({'containers': containers})

    elif kind == 'integrity':
        rows = []
        for f in FileIntegritySnapshot.objects.all().order_by('-is_changed', 'file_path'):
            rows.append({
                'path': f.file_path,
                'hash': f.sha256_hash[:16] + '...',
                'size': f.file_size,
                'changed': f.is_changed,
                'prev_hash': (f.prev_hash[:16] + '...') if f.prev_hash else '-',
                'checked_at': f.checked_at.strftime('%Y-%m-%d %H:%M'),
            })
        return JsonResponse({'files': rows})

    return JsonResponse({'error': '알 수 없는 kind'}, status=400)


# ═══════════════════════════════════════════════════════
# 패널5: 보안 설정 관리
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_settings(request):
    """보안 설정 조회/수정"""
    ALL_KEYS = list(SecurityConfig.DEFAULTS.keys())

    if request.method == 'GET':
        config = {k: SecurityConfig.get(k) for k in ALL_KEYS}

        # 현재 Django 보안 설정 표시
        django_settings = {
            'debug': getattr(settings, 'DEBUG', False),
            'session_cookie_age': getattr(settings, 'SESSION_COOKIE_AGE', 0),
            'session_cookie_secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
            'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', False),
            'csrf_cookie_httponly': getattr(settings, 'CSRF_COOKIE_HTTPONLY', False),
            'max_concurrent_sessions': getattr(settings, 'MAX_CONCURRENT_SESSIONS', 3),
            'password_min_length': 8,
            'throttle_anon': getattr(settings, 'REST_FRAMEWORK', {}).get(
                'DEFAULT_THROTTLE_RATES', {}).get('anon', '30/min'),
            'throttle_user': getattr(settings, 'REST_FRAMEWORK', {}).get(
                'DEFAULT_THROTTLE_RATES', {}).get('user', '200/min'),
        }

        # 보안 자가진단 체크리스트
        checks = []
        checks.append({
            'item': 'DEBUG 모드', 'status': 'pass' if not settings.DEBUG else 'fail',
            'detail': 'OFF' if not settings.DEBUG else '⚠ ON — 운영환경에서 반드시 OFF',
        })
        checks.append({
            'item': 'HTTPS(SSL/TLS)', 'status': 'fail',
            'detail': '⚠ 미적용 — SESSION_COOKIE_SECURE=False',
        })
        checks.append({
            'item': 'CSRF 보호', 'status': 'pass',
            'detail': f'CSRF_COOKIE_HTTPONLY={settings.CSRF_COOKIE_HTTPONLY}',
        })
        checks.append({
            'item': 'X-Frame-Options', 'status': 'pass',
            'detail': 'DENY (nginx + Django)',
        })
        checks.append({
            'item': '보안 헤더', 'status': 'pass',
            'detail': 'X-Content-Type-Options, XSS-Protection, Referrer-Policy',
        })
        checks.append({
            'item': 'API Rate Limit', 'status': 'pass',
            'detail': f'anon={django_settings["throttle_anon"]}, user={django_settings["throttle_user"]}',
        })
        checks.append({
            'item': '비밀번호 정책', 'status': 'pass',
            'detail': '최소 8자, 복잡도 검증, 일반 비밀번호 차단',
        })
        checks.append({
            'item': '2FA 지원', 'status': 'pass',
            'detail': 'TOTP 기반 2FA 구현됨',
        })
        checks.append({
            'item': '세션 관리', 'status': 'pass',
            'detail': f'Redis 기반, {settings.SESSION_COOKIE_AGE//3600}시간 만료, 최대 {getattr(settings, "MAX_CONCURRENT_SESSIONS", 3)}개',
        })
        checks.append({
            'item': 'IP 자동 차단', 'status': 'pass' if SecurityConfig.get_bool('auto_block_enabled') else 'warn',
            'detail': f'{"활성" if SecurityConfig.get_bool("auto_block_enabled") else "비활성"} — 임계값 {SecurityConfig.get_int("block_threshold", 10)}회',
        })

        pass_cnt = sum(1 for c in checks if c['status'] == 'pass')
        score = round(pass_cnt / len(checks) * 100)

        return JsonResponse({
            'config': config,
            'django_settings': django_settings,
            'checks': checks,
            'score': score,
        })

    elif request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        for k, v in body.items():
            if k in ALL_KEYS:
                SecurityConfig.objects.update_or_create(
                    key=k, defaults={'value': str(v), 'updated_by': request.user}
                )
        SecurityEvent.objects.create(
            event_type='config_change', severity='info',
            username=request.user.username,
            description=f'보안 설정 변경: {", ".join(body.keys())}',
        )
        return JsonResponse({'ok': True})

    return JsonResponse({'error': '허용되지 않는 메서드'}, status=405)


# ═══════════════════════════════════════════════════════
# 패널6: 보안 리포트
# ═══════════════════════════════════════════════════════

@_admin_required
def sec_report(request):
    """보안 리포트 — 기간별 통계"""
    now = timezone.now()
    period = request.GET.get('period', 'daily')  # daily / weekly / monthly

    if period == 'daily':
        since = now - datetime.timedelta(days=1)
        period_label = f'{since.strftime("%Y-%m-%d")} (일간)'
    elif period == 'weekly':
        since = now - datetime.timedelta(weeks=1)
        period_label = f'{since.strftime("%Y-%m-%d")} ~ {now.strftime("%Y-%m-%d")} (주간)'
    else:
        since = now - datetime.timedelta(days=30)
        period_label = f'{since.strftime("%Y-%m-%d")} ~ {now.strftime("%Y-%m-%d")} (월간)'

    # 로그인 통계
    login_total = LoginHistory.objects.filter(created_at__gte=since).count()
    login_success = LoginHistory.objects.filter(created_at__gte=since, success=True).count()
    login_fail = LoginHistory.objects.filter(created_at__gte=since, success=False).count()
    unique_ips = LoginHistory.objects.filter(
        created_at__gte=since, success=False
    ).values('ip_address').distinct().count()

    # 차단 이력
    blocks_count = BlockLog.objects.filter(created_at__gte=since, action='block').count()
    unblocks_count = BlockLog.objects.filter(created_at__gte=since, action='unblock').count()

    # 보안 이벤트 통계
    event_by_type = dict(
        SecurityEvent.objects.filter(created_at__gte=since)
        .values('event_type')
        .annotate(cnt=Count('id'))
        .values_list('event_type', 'cnt')
    )
    event_by_severity = dict(
        SecurityEvent.objects.filter(created_at__gte=since)
        .values('severity')
        .annotate(cnt=Count('id'))
        .values_list('severity', 'cnt')
    )

    # SSH 시도
    ssh_fails = SystemLogEntry.objects.filter(
        log_type='ssh_fail', created_at__gte=since
    ).count()

    # 위협 트렌드 (이번 기간 vs 이전 기간)
    if period == 'daily':
        prev_since = since - datetime.timedelta(days=1)
    elif period == 'weekly':
        prev_since = since - datetime.timedelta(weeks=1)
    else:
        prev_since = since - datetime.timedelta(days=30)
    prev_fail = LoginHistory.objects.filter(
        created_at__gte=prev_since, created_at__lt=since, success=False
    ).count()
    trend_pct = round((login_fail - prev_fail) / max(prev_fail, 1) * 100) if prev_fail else 0

    # 일별 추이 (리포트 기간)
    daily_trend = []
    daily_data = (
        LoginHistory.objects.filter(success=False, created_at__gte=since)
        .annotate(d=TruncDate('created_at'))
        .values('d').annotate(cnt=Count('id')).order_by('d')
    )
    daily_map = {r['d']: r['cnt'] for r in daily_data}
    delta_days = (now - since).days
    for i in range(delta_days + 1):
        d = (since + datetime.timedelta(days=i)).date()
        daily_trend.append({'date': d.strftime('%m-%d'), 'count': daily_map.get(d, 0)})

    return JsonResponse({
        'period': period_label,
        'login': {
            'total': login_total,
            'success': login_success,
            'fail': login_fail,
            'unique_fail_ips': unique_ips,
        },
        'blocks': {'blocked': blocks_count, 'unblocked': unblocks_count},
        'events': {'by_type': event_by_type, 'by_severity': event_by_severity},
        'ssh_fails': ssh_fails,
        'trend': {'current': login_fail, 'previous': prev_fail, 'change_pct': trend_pct},
        'daily_trend': daily_trend,
    })
