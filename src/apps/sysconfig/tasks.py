# sysconfig Celery 태스크 — autodiscover 용 진입점
# security_tasks.py 의 태스크를 여기서 import 해야 Celery가 발견함

from apps.sysconfig.security_tasks import (  # noqa: F401
    collect_system_logs,
    check_file_integrity,
    cleanup_expired_blocks,
    generate_security_events,
    auto_block_ssh_attackers,
)
