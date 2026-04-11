from config.celery import app as celery_app
import logging
import os
import base64
import copy

logger = logging.getLogger(__name__)


def _photo_to_b64(photo):
    """Photo 객체 → base64 data URI 문자열. 실패시 빈 문자열 반환."""
    from django.conf import settings
    try:
        path = photo.nas_path if photo.nas_path else os.path.join(settings.MEDIA_ROOT, photo.image.name)
        if not os.path.exists(path):
            path = os.path.join(settings.MEDIA_ROOT, photo.image.name)
        if not os.path.exists(path):
            return ''
        ext = os.path.splitext(path)[1].lower().lstrip('.')
        mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}.get(ext, 'jpeg')
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f'data:image/{mime};base64,{b64}'
    except Exception as exc:
        logger.warning(f'사진 base64 변환 실패 (id={photo.id}): {exc}')
        return ''


def _inject_photos(devices):
    """devices 리스트 내 photo_*_id 를 base64 data URI 로 교체 (병렬 처리)."""
    import concurrent.futures
    from apps.photos.models import Photo

    id_set = set()
    for d in devices:
        for key in ('photo_before_id', 'photo_after_id', 'photo_serial_id'):
            if d.get(key):
                id_set.add(int(d[key]))

    if not id_set:
        return

    photos = {p.id: p for p in Photo.objects.filter(id__in=id_set)}

    # 병렬 base64 변환
    tasks = []
    for d in devices:
        for id_key, b64_key in (
            ('photo_before_id', 'photo_before_b64'),
            ('photo_after_id',  'photo_after_b64'),
            ('photo_serial_id', 'photo_serial_b64'),
        ):
            pid = d.get(id_key)
            if pid and int(pid) in photos:
                tasks.append((d, b64_key, photos[int(pid)]))
            else:
                d[b64_key] = ''

    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_photo_to_b64, p): (d, key) for d, key, p in tasks}
            for future in concurrent.futures.as_completed(futures):
                d, key = futures[future]
                d[key] = future.result()


def _inject_cable_photos(cables):
    """cables 리스트 내 photo_*_id 를 base64 data URI 로 교체 (병렬 처리)."""
    import concurrent.futures
    from apps.photos.models import Photo

    id_set = set()
    for c in cables:
        for key in ('photo_sp_before_id', 'photo_sp_after_id', 'photo_ep_before_id', 'photo_ep_after_id'):
            if c.get(key):
                id_set.add(int(c[key]))

    if not id_set:
        return

    photos = {p.id: p for p in Photo.objects.filter(id__in=id_set)}

    # 병렬 base64 변환
    tasks = []
    for c in cables:
        for id_key, b64_key in (
            ('photo_sp_before_id', 'photo_sp_before_b64'),
            ('photo_sp_after_id',  'photo_sp_after_b64'),
            ('photo_ep_before_id', 'photo_ep_before_b64'),
            ('photo_ep_after_id',  'photo_ep_after_b64'),
        ):
            pid = c.get(id_key)
            if pid and int(pid) in photos:
                tasks.append((c, b64_key, photos[int(pid)]))
            else:
                c[b64_key] = ''

    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_photo_to_b64, p): (c, key) for c, key, p in tasks}
            for future in concurrent.futures.as_completed(futures):
                c, key = futures[future]
                c[key] = future.result()


@celery_app.task(bind=True, max_retries=3, time_limit=300, soft_time_limit=270)
def generate_report_pdf_task(self, report_id):
    """보고서 PDF 생성"""
    from .models import Report
    from django.conf import settings
    from django.template.loader import render_to_string
    import weasyprint

    try:
        report = Report.objects.select_related('school', 'template', 'created_by').get(id=report_id)

        data = copy.deepcopy(report.data) if report.data else {}
        report_type = report.template.report_type
        school_name = report.school.name.replace('/', '_').replace('\\', '_')

        if report_type == 'cable':
            if data.get('cables'):
                _inject_cable_photos(data['cables'])
            html_content = render_to_string('reports/pdf_cable_install.html', {
                'report': report,
                'data':   data,
            })
            base_name = f'소규모 네트워크 포설 확인서_{school_name}'
        else:
            if data.get('devices'):
                _inject_photos(data['devices'])
            html_content = render_to_string('reports/pdf_switch_install.html', {
                'report': report,
                'data':   data,
            })
            doc_type = data.get('doc_type', 'switch')
            if doc_type == 'ap':
                base_name = f'AP 설치 확인서_{school_name}'
            else:
                base_name = f'스위치 설치 확인서_{school_name}'

        # PDF 출력 경로
        pdf_dir = os.path.join(
            getattr(settings, 'NAS_OUTPUT_ROOT', '/media/reports'),
            str(report.school.id)
        )
        os.makedirs(pdf_dir, exist_ok=True)

        pdf_path = os.path.join(pdf_dir, f'{base_name}.pdf')
        weasyprint.HTML(string=html_content).write_pdf(pdf_path)

        report.pdf_path = pdf_path
        report.save(update_fields=['pdf_path'])
        logger.info(f'Report PDF generated: {pdf_path}')

    except Report.DoesNotExist:
        logger.error(f'Report {report_id} not found')
    except Exception as exc:
        logger.error(f'Report PDF generation error: {exc}')
        raise self.retry(exc=exc, countdown=60)
