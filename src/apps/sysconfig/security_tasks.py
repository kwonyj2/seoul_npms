"""
보안관제 Celery 태스크
1. collect_system_logs   — /var/log/auth.log SSH 로그 수집 (5분마다)
2. check_file_integrity  — 핵심 설정파일 SHA256 점검 (1시간마다)
3. cleanup_expired_blocks — 만료된 IP 차단 자동 해제 (5분마다)
4. generate_security_events — LoginHistory 기반 보안 이벤트 생성 (5분마다)
"""
import datetime
import hashlib
import logging
import os
import re

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('security')


@shared_task(name='sysconfig.collect_system_logs')
def collect_system_logs():
    """SSH 로그 수집 — /var/log/auth.log 파싱"""
    from apps.sysconfig.security_models import SystemLogEntry, SecurityConfig, SecurityEvent

    if not SecurityConfig.get_bool('ssh_monitor_enabled'):
        return 'SSH 모니터링 비활성'

    log_paths = ['/var/log/auth.log', '/var/log/secure']
    log_file = None
    for p in log_paths:
        if os.path.exists(p):
            log_file = p
            break
    if not log_file:
        return 'auth.log 파일 없음'

    # 최근 수집 시각 이후만 처리 (최초 실행 시 7일 전부터)
    last = SystemLogEntry.objects.order_by('-created_at').first()
    cutoff = last.created_at if last else timezone.now() - datetime.timedelta(days=7)

    # SSH 실패 패턴
    FAIL_PATTERNS = [
        re.compile(r'Failed password for (?:invalid user )?(\S+) from (\S+) port'),
        re.compile(r'Failed publickey for (\S+) from (\S+) port'),
        re.compile(r'authentication failure.*rhost=(\S+).*user=(\S+)'),
        re.compile(r'Invalid user (\S+) from (\S+)'),
        re.compile(r'Connection closed by (?:invalid user )?(\S+)?\s*(\S+) port'),
    ]
    SUCCESS_PATTERN = re.compile(r'Accepted (?:password|publickey) for (\S+) from (\S+) port')
    # sudo/pam 패턴 (authentication failure, conversation failed, could not identify)
    AUTH_FAIL_PATTERNS = [
        re.compile(r'pam_unix\(\S+:auth\):\s+authentication failure.*user=(\S+)'),
        re.compile(r'pam_unix\(\S+:auth\):\s+(?:conversation failed|auth could not identify)'),
        re.compile(r'sudo:\s+(\S+)\s*:.*authentication failure'),
    ]

    # 날짜 파싱 — ISO 8601 (2026-04-12T05:17:01.780+09:00) + syslog (Apr 12 05:17:01)
    MONTHS = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    ISO_PAT = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')

    def parse_syslog_date(line):
        # ISO 8601 형식
        m = ISO_PAT.match(line)
        if m:
            try:
                dt = datetime.datetime.fromisoformat(m.group(1))
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except Exception:
                pass
        # 전통 syslog 형식
        try:
            parts = line.split()
            mon = MONTHS.get(parts[0], 0)
            if mon:
                day = int(parts[1])
                hms = parts[2].split(':')
                year = timezone.now().year
                return timezone.make_aware(
                    datetime.datetime(year, mon, day, int(hms[0]), int(hms[1]), int(hms[2]))
                )
        except Exception:
            pass
        return None

    created = 0
    try:
        with open(log_file, 'r', errors='replace') as f:
            for line in f:
                log_time = parse_syslog_date(line)
                if log_time and log_time <= cutoff:
                    continue

                # SSH 실패
                for pat in FAIL_PATTERNS:
                    m = pat.search(line)
                    if m:
                        groups = m.groups()
                        if len(groups) >= 2:
                            user, ip = groups[0], groups[1]
                        else:
                            user, ip = groups[0] if groups else '', ''
                        if not SystemLogEntry.objects.filter(
                            raw_line=line.strip()[:500],
                            log_type='ssh_fail'
                        ).exists():
                            SystemLogEntry.objects.create(
                                log_type='ssh_fail',
                                ip_address=ip or None,
                                username=user,
                                raw_line=line.strip()[:500],
                                log_time=log_time,
                            )
                            created += 1
                        break

                # SSH 성공
                m = SUCCESS_PATTERN.search(line)
                if m:
                    user, ip = m.group(1), m.group(2)
                    if not SystemLogEntry.objects.filter(
                        raw_line=line.strip()[:500],
                        log_type='ssh_success'
                    ).exists():
                        SystemLogEntry.objects.create(
                            log_type='ssh_success',
                            ip_address=ip or None,
                            username=user,
                            raw_line=line.strip()[:500],
                            log_time=log_time,
                        )
                        created += 1

                # sudo/pam 인증 실패
                for apat in AUTH_FAIL_PATTERNS:
                    am = apat.search(line)
                    if am:
                        user = am.group(1) if am.lastindex else ''
                        raw = line.strip()[:500]
                        if not SystemLogEntry.objects.filter(raw_line=raw, log_type='auth_other').exists():
                            SystemLogEntry.objects.create(
                                log_type='auth_other',
                                username=user,
                                raw_line=raw,
                                log_time=log_time,
                            )
                            created += 1
                        break
    except PermissionError:
        return 'auth.log 읽기 권한 없음'
    except Exception as e:
        return f'오류: {e}'

    return f'{created}건 수집'


@shared_task(name='sysconfig.check_file_integrity')
def check_file_integrity():
    """핵심 설정파일 SHA256 해시 비교"""
    from apps.sysconfig.security_models import FileIntegritySnapshot, SecurityConfig, SecurityEvent

    if not SecurityConfig.get_bool('file_integrity_enabled'):
        return '파일 무결성 점검 비활성'

    # 점검 대상 파일
    TARGET_FILES = [
        '/app/config/settings/base.py',
        '/app/config/settings/production.py',
        '/app/config/urls.py',
        '/app/docker-compose.yml',
        '/etc/nginx/conf.d/default.conf',
        '/app/manage.py',
    ]
    # 호스트 개발환경 대비 대체 경로
    ALT_BASE = '/home/kwonyj/network_pms/src'
    ALT_FILES = [
        f'{ALT_BASE}/config/settings/base.py',
        f'{ALT_BASE}/config/settings/production.py',
        f'{ALT_BASE}/config/urls.py',
    ]

    all_files = TARGET_FILES + ALT_FILES
    changed = 0

    for fpath in all_files:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'rb') as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()
            fsize = os.path.getsize(fpath)

            snap, created = FileIntegritySnapshot.objects.get_or_create(
                file_path=fpath,
                defaults={'sha256_hash': current_hash, 'file_size': fsize}
            )
            if not created:
                if snap.sha256_hash != current_hash:
                    snap.prev_hash = snap.sha256_hash
                    snap.sha256_hash = current_hash
                    snap.file_size = fsize
                    snap.is_changed = True
                    snap.save()
                    changed += 1
                    SecurityEvent.objects.create(
                        event_type='file_integrity',
                        severity='high',
                        description=f'파일 변경 감지: {fpath}',
                        detail={'path': fpath, 'old': snap.prev_hash[:16], 'new': current_hash[:16]},
                    )
                else:
                    if snap.is_changed:
                        snap.is_changed = False
                        snap.save()
        except Exception as e:
            logger.debug(f'파일 무결성 점검 오류: {fpath} — {e}')

    return f'{changed}건 변경 감지'


@shared_task(name='sysconfig.cleanup_expired_blocks')
def cleanup_expired_blocks():
    """만료된 IP 차단 자동 해제"""
    from apps.sysconfig.security_models import BlockedIP, BlockLog, SecurityEvent

    now = timezone.now()
    expired = BlockedIP.objects.filter(
        is_permanent=False,
        expires_at__isnull=False,
        expires_at__lte=now,
    )
    count = 0
    for b in expired:
        BlockLog.objects.create(
            ip_address=b.ip_address,
            action='unblock',
            reason=f'자동 해제 (만료: {b.expires_at.strftime("%Y-%m-%d %H:%M")})',
        )
        SecurityEvent.objects.create(
            event_type='ip_unblocked', severity='info',
            ip_address=b.ip_address,
            description=f'차단 만료 자동 해제',
        )
        b.delete()
        count += 1

    return f'{count}건 해제'


@shared_task(name='sysconfig.generate_security_events')
def generate_security_events():
    """LoginHistory 기반 보안 이벤트 자동 생성 (5분마다)"""
    from apps.sysconfig.security_models import SecurityEvent
    from apps.accounts.models import LoginHistory
    from django.db.models import Count

    now = timezone.now()
    window = now - datetime.timedelta(minutes=5)

    # 최근 5분 실패 기록에서 IP별 집계
    ip_fails = (
        LoginHistory.objects.filter(success=False, created_at__gte=window)
        .values('ip_address')
        .annotate(cnt=Count('id'))
        .filter(cnt__gte=3)
    )

    created = 0
    for row in ip_fails:
        ip = row['ip_address']
        cnt = row['cnt']

        # 이미 같은 시간대 이벤트 있으면 스킵
        if SecurityEvent.objects.filter(
            ip_address=ip, event_type='brute_force', created_at__gte=window
        ).exists():
            continue

        if cnt >= 20:
            sev = 'critical'
        elif cnt >= 10:
            sev = 'high'
        else:
            sev = 'medium'

        # 시도한 계정명 목록
        usernames = sorted(set(
            LoginHistory.objects.filter(
                ip_address=ip, success=False, created_at__gte=window
            ).exclude(attempted_username='')
            .values_list('attempted_username', flat=True)
        ))[:5]

        SecurityEvent.objects.create(
            event_type='brute_force',
            severity=sev,
            ip_address=ip,
            description=f'5분 내 {cnt}회 로그인 실패 (계정: {", ".join(usernames) or "N/A"})',
            detail={'fail_count': cnt, 'usernames': usernames},
        )
        created += 1

    # 미등록 계정 시도
    unknown_fails = (
        LoginHistory.objects.filter(
            success=False, user__isnull=True, created_at__gte=window
        ).values('attempted_username')
        .annotate(cnt=Count('id'))
        .filter(cnt__gte=2)
    )
    for row in unknown_fails:
        uname = row['attempted_username']
        if not uname:
            continue
        if SecurityEvent.objects.filter(
            event_type='unknown_user', username=uname, created_at__gte=window
        ).exists():
            continue
        SecurityEvent.objects.create(
            event_type='unknown_user',
            severity='medium',
            username=uname,
            description=f'미등록 계정 "{uname}" {row["cnt"]}회 로그인 시도',
        )
        created += 1

    return f'{created}건 이벤트 생성'
