# accounts 비즈니스 로직
from django.conf import settings


def enforce_concurrent_session_limit(user):
    """MAX_CONCURRENT_SESSIONS 초과 시 가장 오래된 세션을 비활성화한다."""
    from .models import UserSession
    limit = getattr(settings, 'MAX_CONCURRENT_SESSIONS', 3)
    active_sessions = UserSession.objects.filter(
        user=user, is_active=True
    ).order_by('login_at')  # 오래된 순

    count = active_sessions.count()
    if count > limit:
        # 초과분만큼 오래된 것부터 비활성화
        to_deactivate = active_sessions[:count - limit]
        ids = list(to_deactivate.values_list('id', flat=True))
        UserSession.objects.filter(id__in=ids).update(is_active=False)
