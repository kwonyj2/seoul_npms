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
    """SSH 로그 수집 — journalctl 우선, auth.log 폴백"""
    import subprocess
    from apps.sysconfig.security_models import SystemLogEntry, SecurityConfig

    if not SecurityConfig.get_bool('ssh_monitor_enabled'):
        return 'SSH 모니터링 비활성'

    # SSH 실패 패턴
    FAIL_PATTERNS = [
        re.compile(r'Failed password for (?:invalid user )?(\S+) from (\S+) port'),
        re.compile(r'Failed publickey for (\S+) from (\S+) port'),
        re.compile(r'Invalid user (\S+) from (\S+)'),
    ]
    SUCCESS_PATTERN = re.compile(r'Accepted (?:password|publickey) for (\S+) from (\S+) port')
    AUTH_FAIL_PATTERNS = [
        re.compile(r'pam_unix\(\S+:auth\):\s+authentication failure.*rhost=(\S+)'),
        re.compile(r'pam_unix\(\S+:auth\):\s+authentication failure.*user=(\S+)'),
        re.compile(r'pam_unix\(\S+:auth\):\s+(?:conversation failed|auth could not identify)'),
    ]

    # 날짜 파싱
    MONTHS = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    ISO_PAT = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')
    # journalctl 형식: " 4월 16 08:58:49" or "Apr 16 08:58:49"
    JCT_PAT = re.compile(r'^\s*(\d{1,2})월\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})')

    def parse_date(line):
        # ISO 8601
        m = ISO_PAT.match(line)
        if m:
            try:
                dt = datetime.datetime.fromisoformat(m.group(1))
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            except Exception:
                pass
        # journalctl 한글 형식: " 4월 16 08:58:49"
        m = JCT_PAT.match(line)
        if m:
            try:
                mon, day, h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
                return timezone.make_aware(
                    datetime.datetime(timezone.now().year, mon, day, h, mi, s)
                )
            except Exception:
                pass
        # 전통 syslog: "Apr 16 08:58:49"
        try:
            parts = line.split()
            mon = MONTHS.get(parts[0], 0)
            if mon:
                day = int(parts[1])
                hms = parts[2].split(':')
                return timezone.make_aware(
                    datetime.datetime(timezone.now().year, mon, day, int(hms[0]), int(hms[1]), int(hms[2]))
                )
        except Exception:
            pass
        return None

    def _process_line(line, cutoff):
        """한 줄 파싱 → (log_type, username, ip, log_time) or None"""
        log_time = parse_date(line)
        if log_time and log_time <= cutoff:
            return None

        # SSH 실패
        for pat in FAIL_PATTERNS:
            m = pat.search(line)
            if m:
                groups = m.groups()
                user = groups[0] if len(groups) >= 1 else ''
                ip = groups[1] if len(groups) >= 2 else ''
                return ('ssh_fail', user, ip, log_time)

        # SSH 성공
        m = SUCCESS_PATTERN.search(line)
        if m:
            return ('ssh_success', m.group(1), m.group(2), log_time)

        # pam 인증 실패
        for apat in AUTH_FAIL_PATTERNS:
            am = apat.search(line)
            if am:
                val = am.group(1) if am.lastindex else ''
                # rhost=IP 인 경우 IP로, user=이름 인 경우 username으로
                if re.match(r'\d+\.\d+\.\d+\.\d+', val):
                    return ('auth_other', '', val, log_time)
                return ('auth_other', val, '', log_time)

        return None

    # 최근 수집 시각
    last = SystemLogEntry.objects.order_by('-created_at').first()
    cutoff = last.created_at if last else timezone.now() - datetime.timedelta(days=7)

    lines = []

    # 1) journalctl 시도 (운용서버 — systemd journal)
    #    --directory 로 호스트 journal 직접 읽기 (컨테이너 machine-id 불일치 우회)
    try:
        since_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        journal_dirs = ['/var/log/journal', '/run/log/journal']
        for jdir in journal_dirs:
            if os.path.isdir(jdir):
                result = subprocess.run(
                    ['journalctl', '--directory', jdir,
                     '-u', 'ssh', '-u', 'sshd', '--no-pager',
                     '--since', since_str, '-q'],
                    capture_output=True, text=True, timeout=30
                )
                if result.stdout.strip():
                    lines = result.stdout.strip().split('\n')
                    break
    except Exception:
        pass

    # 2) auth.log 폴백 (journalctl 결과 없으면)
    if not lines:
        log_paths = ['/var/log/auth.log', '/var/log/secure']
        for p in log_paths:
            if os.path.exists(p):
                try:
                    with open(p, 'r', errors='replace') as f:
                        lines = f.readlines()
                except PermissionError:
                    pass
                break

    if not lines:
        return 'SSH 로그 소스 없음'

    created = 0
    for line in lines:
        line = line.strip()
        if not line or 'sshd' not in line.lower() and 'pam_unix' not in line:
            continue
        parsed = _process_line(line, cutoff)
        if not parsed:
            continue
        log_type, username, ip, log_time = parsed
        raw = line[:500]
        if SystemLogEntry.objects.filter(raw_line=raw, log_type=log_type).exists():
            continue
        SystemLogEntry.objects.create(
            log_type=log_type,
            ip_address=ip or None,
            username=username,
            raw_line=raw,
            log_time=log_time,
        )
        created += 1

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
