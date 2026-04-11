from config.celery import app as celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_sessions():
    """비활성 세션 정리 (30분 이상 미접속)"""
    from django.utils import timezone
    from datetime import timedelta
    from .models import UserSession
    cutoff = timezone.now() - timedelta(minutes=30)
    count = UserSession.objects.filter(is_active=True, last_active__lt=cutoff).update(is_active=False)
    if count:
        logger.info(f'세션 정리: {count}개 비활성 처리')
    return count
