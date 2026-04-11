"""
schools Celery 태스크
- scan_vsdx_folder: NAS/건물정보_비지오 폴더 감시 → 자동 파싱 → DB 저장
- import_vsdx_file: 단일 VSDX 파일 파싱 후 DB 저장
"""
import os
import logging
import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

VSDX_FOLDER = os.path.join(
    getattr(settings, 'NAS_MEDIA_ROOT', '/app/nas/media/npms'),
    'data', '건물정보_비지오'
)


@shared_task(bind=True, max_retries=2)
def import_vsdx_file(self, file_path: str, school_name_override: str = None):
    """단일 VSDX 파일 파싱 → Building/Floor/Room DB 저장"""
    from .vsdx_parser import parse_vsdx
    from .models import School, SchoolBuilding, SchoolFloor, SchoolRoom, VsdxImportLog

    file_name = os.path.basename(file_path)
    school_name = school_name_override or os.path.splitext(file_name)[0]

    logger.info(f'[VSDX] 파싱 시작: {file_name} (학교명: {school_name})')

    # 학교명 매칭 (정확 → 부분)
    school = School.objects.filter(name=school_name, is_active=True).first()
    if not school:
        school = School.objects.filter(name__contains=school_name, is_active=True).first()
    if not school:
        msg = f'학교 미매칭: {school_name}'
        logger.warning(f'[VSDX] {msg}')
        VsdxImportLog.objects.create(
            file_name=file_name, file_path=file_path,
            status='fail', error_msg=msg
        )
        return {'status': 'fail', 'error': msg}

    # VSDX 파싱
    result = parse_vsdx(file_path)
    if result.error:
        logger.error(f'[VSDX] 파싱 오류: {result.error}')
        VsdxImportLog.objects.create(
            school=school, file_name=file_name, file_path=file_path,
            status='fail', error_msg=result.error
        )
        return {'status': 'fail', 'error': result.error}

    # DB 저장 (트랜잭션)
    room_count = 0
    try:
        with transaction.atomic():
            for bld_data in result.buildings:
                above = [f.floor_num for f in bld_data.floors if f.floor_num > 0]
                below = [f.floor_num for f in bld_data.floors if f.floor_num < 0]
                building, _ = SchoolBuilding.objects.get_or_create(
                    school=school,
                    name=bld_data.name,
                    defaults={
                        'floors':   max(above) if above else 1,
                        'basement': abs(min(below)) if below else 0,
                    }
                )
                if above:
                    building.floors = max(above)
                if below:
                    building.basement = abs(min(below))
                building.save(update_fields=['floors', 'basement'])

                for fl_data in bld_data.floors:
                    floor, _ = SchoolFloor.objects.get_or_create(
                        building=building,
                        floor_num=fl_data.floor_num,
                        defaults={'floor_name': fl_data.floor_name}
                    )
                    # 기존 파싱 데이터 교체
                    floor.rooms.filter(vsdx_source=file_name).delete()

                    for rm in fl_data.rooms:
                        SchoolRoom.objects.create(
                            floor=floor,
                            name=rm.name,
                            room_number=rm.room_number,
                            room_type=rm.room_type,
                            area_m2=rm.area_m2,
                            pos_x=rm.pos_x,
                            pos_y=rm.pos_y,
                            pos_w=rm.pos_w,
                            pos_h=rm.pos_h,
                            vsdx_source=file_name,
                        )
                        room_count += 1

    except Exception as e:
        logger.exception(f'[VSDX] DB 저장 실패: {e}')
        VsdxImportLog.objects.create(
            school=school, file_name=file_name, file_path=file_path,
            status='fail', room_count=room_count, error_msg=str(e)
        )
        raise self.retry(exc=e, countdown=60)

    VsdxImportLog.objects.create(
        school=school, file_name=file_name, file_path=file_path,
        status='success', room_count=room_count
    )
    logger.info(f'[VSDX] 완료: {school_name} — {room_count}개 호실')
    return {'status': 'success', 'school': school_name, 'rooms': room_count}


@shared_task
def scan_vsdx_folder():
    """NAS/건물정보_비지오 폴더 스캔 → 새 .vsdx 파일 자동 파싱"""
    from .models import VsdxImportLog

    if not os.path.isdir(VSDX_FOLDER):
        logger.info(f'[VSDX] 폴더 없음: {VSDX_FOLDER}')
        return {'scanned': 0}

    processed = set(
        VsdxImportLog.objects.filter(status='success')
        .values_list('file_name', flat=True)
    )

    queued = 0
    for fname in os.listdir(VSDX_FOLDER):
        if not fname.lower().endswith('.vsdx') or fname.endswith(':Zone.Identifier'):
            continue
        if fname in processed:
            continue
        import_vsdx_file.delay(os.path.join(VSDX_FOLDER, fname))
        queued += 1
        logger.info(f'[VSDX] 큐 등록: {fname}')

    return {'scanned': queued}


@shared_task(bind=True, max_retries=1)
def sync_pms_contacts(self):
    """운영 PMS에서 학교 담당자(확인자/점검자) 전체 동기화"""
    from apps.schools.models import School, SchoolContact

    api_url = getattr(settings, 'PMS_API_URL', '').rstrip('/')
    api_key = getattr(settings, 'PMS_API_KEY', '')

    if not api_url:
        logger.warning('[PMS 동기화] PMS_API_URL 미설정')
        return {'synced': 0, 'error': 'PMS_API_URL not set'}

    try:
        resp = requests.get(
            f'{api_url}/api/contacts/export/',
            headers={'X-Api-Key': api_key},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.error(f'[PMS 동기화] API 호출 실패: {exc}')
        raise self.retry(exc=exc, countdown=300)

    if not payload.get('success'):
        logger.error(f'[PMS 동기화] API 오류: {payload.get("error")}')
        return {'synced': 0}

    synced = 0
    skipped = 0
    for item in payload.get('data', []):
        school_name = item.get('school_name', '').strip()
        school_code = item.get('school_code', '').strip()

        # 학교 매칭: 코드 우선, 없으면 이름
        school = None
        if school_code:
            school = School.objects.filter(code=school_code).first()
        if not school:
            school = School.objects.filter(name=school_name).first()
        if not school:
            skipped += 1
            logger.debug(f'[PMS 동기화] 학교 미매칭: {school_name}')
            continue

        contacts_to_upsert = []
        if item.get('confirmer_name'):
            contacts_to_upsert.append({
                'name':     item['confirmer_name'],
                'phone':    item.get('confirmer_contact', ''),
                'position': '확인자',
            })
        if item.get('inspector_name'):
            contacts_to_upsert.append({
                'name':     item['inspector_name'],
                'phone':    item.get('inspector_contact', ''),
                'position': '점검자',
            })

        with transaction.atomic():
            for c in contacts_to_upsert:
                obj, created = SchoolContact.objects.update_or_create(
                    school=school,
                    position=c['position'],
                    defaults={
                        'name':       c['name'],
                        'phone':      c['phone'],
                        'is_primary': (c['position'] == '확인자'),
                    },
                )
                if created or obj.name != c['name']:
                    synced += 1

    logger.info(f'[PMS 동기화] 완료 — 동기화: {synced}건 / 미매칭: {skipped}개 학교')
    return {'synced': synced, 'skipped': skipped}
