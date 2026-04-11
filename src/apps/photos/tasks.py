from config.celery import app as celery_app
import logging
import os

logger = logging.getLogger(__name__)


def _safe(text):
    """파일명 안전 문자로 변환"""
    import re
    return re.sub(r'[\\/:*?"<>|]', '', str(text)).strip().replace(' ', '_')


@celery_app.task(bind=True, max_retries=2)
def sync_photo_to_nas(self, photo_id):
    """사진 NAS 저장 및 파일명 규칙 적용
    파일명: 지원청_학제_학교명_건물_층_교실_작업명_단계_작업일NO.ext
    저장위치: NAS_PHOTO_ROOT/지원청명/학교명/
    """
    from .models import Photo
    from django.conf import settings
    import shutil
    try:
        photo = Photo.objects.select_related(
            'school__support_center', 'school__school_type',
            'building', 'floor', 'room', 'work_type'
        ).get(id=photo_id)

        school  = photo.school
        center  = school.support_center.name  if school.support_center else '미분류'
        stype   = school.school_type.name     if school.school_type    else '미분류'

        # ── 파일명 조립 ──────────────────────────────────────────────
        # 지원청_학제_학교명_건물_층_교실_작업명_단계_날짜NO.ext
        parts = [
            _safe(center),
            _safe(stype),
            _safe(school.name),
        ]
        if photo.building:
            parts.append(_safe(photo.building.name))
        if photo.floor:
            parts.append(_safe(photo.floor.floor_name))
        if photo.room:
            parts.append(_safe(photo.room.name))

        work_label = photo.work_type.name if photo.work_type else (photo.work_type_etc or '기타')
        parts.append(_safe(work_label))
        parts.append(_safe(photo.get_photo_stage_display()))  # 작업전 / 작업후 / 기타

        date_str = photo.taken_at.strftime('%Y%m%d')

        # 같은 학교·날짜·작업명·단계의 순번
        seq = Photo.objects.filter(
            school=school,
            taken_at__date=photo.taken_at.date(),
            work_type=photo.work_type,
            photo_stage=photo.photo_stage,
            id__lte=photo.id,
        ).count()

        ext = os.path.splitext(photo.image.name)[1].lower() if photo.image else '.jpg'
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            ext = '.jpg'

        file_name = '_'.join(parts) + f'_{date_str}{seq:03d}{ext}'

        # ── 저장 경로: NAS현장사진/지원청/학교명/ ──────────────────────
        nas_photo_root = getattr(settings, 'NAS_PHOTO_ROOT', '/app/nas/media/npms/작업이미지')
        dest_dir  = os.path.join(nas_photo_root, _safe(center), _safe(school.name))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file_name)

        # 원본 파일 복사
        if photo.image:
            try:
                src = photo.image.path
                if os.path.exists(src):
                    shutil.copy2(src, dest_path)
                    photo.nas_path = dest_path
            except Exception as e:
                logger.warning(f'Photo copy error: {e}')

        photo.file_name = file_name
        photo.file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
        photo.save(update_fields=['nas_path', 'file_name', 'file_size'])
        logger.info(f'Photo {photo_id} → {dest_path}')

        # AI 분류
        classify_photo_ai.delay(photo_id)

    except Photo.DoesNotExist:
        logger.error(f'Photo {photo_id} not found')
    except Exception as exc:
        logger.error(f'Photo NAS sync error: {exc}')
        raise self.retry(exc=exc, countdown=30)


@celery_app.task
def classify_photo_ai(photo_id):
    """AI 이미지 분류"""
    from .models import Photo
    import httpx
    from django.conf import settings
    try:
        photo = Photo.objects.get(id=photo_id)
        ai_url = getattr(settings, 'AI_SERVER_URL', 'http://ai_server:8100')
        if not photo.image or not os.path.exists(photo.image.path):
            return

        with open(photo.image.path, 'rb') as f:
            resp = httpx.post(
                f'{ai_url}/api/classify/image/',
                files={'file': f},
                timeout=30
            )
        if resp.status_code == 200:
            result = resp.json()
            photo.ai_category   = result.get('category', '')
            photo.ai_confidence = result.get('confidence')
            photo.save(update_fields=['ai_category', 'ai_confidence'])
            logger.info(f'Photo {photo_id} classified: {photo.ai_category}')
    except Photo.DoesNotExist:
        logger.error(f'Photo {photo_id} not found')
    except Exception as exc:
        logger.warning(f'Photo AI classification error: {exc}')
