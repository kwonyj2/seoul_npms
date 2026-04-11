"""core Celery 태스크"""
import os
import glob
import subprocess
import logging
from datetime import datetime
from celery import shared_task
from django.conf import settings

logger = logging.getLogger('celery.core')


# ─────────────────────────────────────────
# 내부 헬퍼 함수 (테스트에서 직접 mock 가능)
# ─────────────────────────────────────────

def _run_pg_dump(backup_dir: str) -> dict:
    """
    pg_dump 실행 → .sql.gz 저장.
    반환: {'status': 'ok'|'error'|'timeout', 'file': str, 'size': str, 'msg': str}
    """
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'npms_db_{timestamp}.sql.gz')

    db = settings.DATABASES['default']
    db_name = db.get('NAME', 'npms_db')
    db_user = db.get('USER', 'django')
    db_pass = db.get('PASSWORD', '')
    db_host = db.get('HOST', 'db')
    db_port = str(db.get('PORT', '5432'))

    env = os.environ.copy()
    env['PGPASSWORD'] = db_pass

    cmd = ['pg_dump', '-h', db_host, '-p', db_port,
           '-U', db_user, '-d', db_name, '--no-password', '-F', 'p']

    try:
        dump = subprocess.run(cmd, capture_output=True, timeout=300, env=env)
        if dump.returncode != 0:
            return {
                'status': 'error',
                'msg': dump.stderr.decode('utf-8', errors='replace')[:500],
            }

        with subprocess.Popen(
            ['gzip'], stdin=subprocess.PIPE,
            stdout=open(backup_file, 'wb')
        ) as gz:
            gz.communicate(input=dump.stdout)

        size_bytes = os.path.getsize(backup_file)
        size_str = (f'{size_bytes / 1024:.1f} KB' if size_bytes < 1024 * 1024
                    else f'{size_bytes / 1024 / 1024:.1f} MB')
        return {'status': 'ok', 'file': backup_file, 'size': size_str}

    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'msg': 'pg_dump 타임아웃 (5분 초과)'}
    except Exception as e:
        return {'status': 'error', 'msg': str(e)}


def _cleanup_old_backups(backup_dir: str, keep_days: int) -> int:
    """보존 기간 초과 백업 파일 삭제. 삭제 파일 수 반환."""
    import time
    cutoff = time.time() - keep_days * 86400
    pattern = os.path.join(backup_dir, 'npms_db_*.sql.gz')
    deleted = 0
    for f in glob.glob(pattern):
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
                deleted += 1
            except OSError:
                pass
    return deleted


# ─────────────────────────────────────────
# Celery 태스크
# ─────────────────────────────────────────

@shared_task(name='core.tasks.backup_database', bind=True, max_retries=2)
def backup_database(self):
    """매일 새벽 3시 PostgreSQL 자동 백업"""
    backup_dir = getattr(settings, 'DB_BACKUP_DIR',
                         '/home/kwonyj/network_pms/backups')
    keep_days  = getattr(settings, 'DB_BACKUP_KEEP_DAYS', 30)

    logger.info('DB 백업 시작: %s', backup_dir)
    result = _run_pg_dump(backup_dir)

    if result['status'] == 'ok':
        deleted = _cleanup_old_backups(backup_dir, keep_days)
        logger.info('DB 백업 완료: %s (%s), 구 백업 %d개 삭제',
                    result['file'], result['size'], deleted)
        result['deleted'] = deleted
    elif result['status'] == 'timeout':
        logger.error('DB 백업 타임아웃')
    else:
        logger.error('DB 백업 실패: %s', result.get('msg', ''))
        try:
            raise self.retry(countdown=600)
        except Exception:
            pass

    return result


@shared_task(name='core.tasks.notify_deploy_complete', bind=False)
def notify_deploy_complete(version: str = '', deployer: str = 'CI/CD'):
    """배포 완료 SMS 알림"""
    from django.conf import settings as _settings
    msg = f'[NPMS] 배포 완료 | {version or "최신"} | {deployer}'
    logger.info('배포 알림: %s', msg)

    sms_enabled = getattr(_settings, 'SMS_ENABLED', False)
    if not sms_enabled:
        logger.info('SMS_ENABLED=False — 알림 건너뜀')
        return {'status': 'skipped', 'message': msg}

    try:
        from apps.incidents.sms import send_sms
        from apps.accounts.models import User
        # superadmin에게 알림
        admins = User.objects.filter(
            role='superadmin', is_active=True
        ).exclude(phone='').values_list('phone', flat=True)
        for phone in admins:
            send_sms(phone, msg)
        return {'status': 'ok', 'recipients': len(admins)}
    except Exception as e:
        logger.error('배포 알림 SMS 실패: %s', e)
        return {'status': 'error', 'error': str(e)}
