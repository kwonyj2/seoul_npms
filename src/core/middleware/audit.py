import logging
from django.utils import timezone
from core.utils.network import get_client_ip

logger = logging.getLogger('audit')

# HTTP 메서드 → UserActivityLog.action 매핑
_METHOD_ACTION = {
    'POST':   'create',
    'PUT':    'update',
    'PATCH':  'update',
    'DELETE': 'delete',
}


def _extract_target(path: str) -> str:
    """URL 경로에서 API prefix 를 제거해 대상 리소스명 반환"""
    for prefix in ('/npms/api/', '/api/'):
        if path.startswith(prefix):
            return path[len(prefix):].rstrip('/')
    return path.rstrip('/')


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated and request.method in _METHOD_ACTION:
            action = _METHOD_ACTION[request.method]
            target = _extract_target(request.path)

            # ── 파일 로그 ────────────────────────���────────
            logger.info(
                f"[AUDIT] user={request.user} method={request.method} "
                f"path={request.path} status={response.status_code} "
                f"time={timezone.now()}"
            )

            # ── DB 감사 로그 ───────────────────────────────
            try:
                from apps.accounts.models import UserActivityLog
                UserActivityLog.objects.create(
                    user=request.user,
                    action=action,
                    target=target[:200],
                    detail=f'status={response.status_code}',
                    ip_address=get_client_ip(request),
                )
            except Exception as e:
                logger.debug('UserActivityLog DB 저장 실패: %s', e)

        return response
