"""
NAS Celery 태스크
- OCR 텍스트 추출 (Tesseract + pdfplumber)
"""
import logging
import os
from config.celery import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def extract_ocr_text(self, file_id: int):
    """
    NAS 파일 OCR 텍스트 추출
    - PDF: pdfplumber 텍스트 추출 + Tesseract OCR (이미지 페이지)
    - 이미지(JPG/PNG): Tesseract OCR
    - 기타: 건너뜀
    """
    from .models import File
    try:
        f = File.objects.get(pk=file_id)
    except File.DoesNotExist:
        return

    if f.ocr_text:
        return  # 이미 추출됨

    file_path = f.file_path
    if not os.path.exists(file_path):
        return

    mime = (f.mime_type or '').lower()
    text = ''

    try:
        if 'pdf' in mime or file_path.lower().endswith('.pdf'):
            text = _extract_pdf(file_path)
        elif any(ext in (mime + file_path.lower()) for ext in ['image', 'jpg', 'jpeg', 'png', 'tiff', 'bmp']):
            text = _extract_image(file_path)
    except Exception as exc:
        logger.warning(f'OCR 실패 (file_id={file_id}): {exc}')
        raise self.retry(exc=exc, countdown=30)

    if text:
        f.ocr_text = text[:65000]  # DB 제한
        f.save(update_fields=['ocr_text'])
        logger.info(f'OCR 완료 (file_id={file_id}): {len(text)}자')


def _extract_pdf(file_path: str) -> str:
    """PDF → 텍스트 (pdfplumber 우선, 이미지 페이지는 Tesseract)"""
    parts = []
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ''
                if page_text.strip():
                    parts.append(page_text)
                else:
                    # 이미지 기반 페이지 → OCR
                    try:
                        img = page.to_image(resolution=150).original
                        parts.append(_ocr_pil(img))
                    except Exception:
                        pass
    except ImportError:
        # pdfplumber 없으면 Tesseract만
        parts.append(_extract_pdf_tesseract(file_path))
    return '\n'.join(parts)


def _extract_pdf_tesseract(file_path: str) -> str:
    """pdf2image + tesseract fallback"""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(file_path, dpi=150, first_page=1, last_page=5)
        return '\n'.join(_ocr_pil(img) for img in images)
    except Exception:
        return ''


def _extract_image(file_path: str) -> str:
    """이미지 파일 OCR"""
    try:
        from PIL import Image
        img = Image.open(file_path)
        return _ocr_pil(img)
    except Exception:
        return ''


def _ocr_pil(image) -> str:
    """PIL Image → Tesseract OCR (한국어+영어)"""
    try:
        import pytesseract
        return pytesseract.image_to_string(image, lang='kor+eng')
    except Exception:
        return ''


@celery_app.task
def classify_nas_file(file_id: int):
    """NAS 파일 AI 자동 분류 (카테고리 자동 설정)"""
    from .models import File
    import httpx
    from django.conf import settings

    try:
        f = File.objects.get(pk=file_id)
    except File.DoesNotExist:
        return

    ai_url = getattr(settings, 'AI_SERVER_URL', 'http://npms_ai:8001')
    try:
        resp = httpx.post(
            f'{ai_url}/api/classify/document/',
            json={'filename': f.name, 'text': f.ocr_text or ''},
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            category = result.get('category', 'other')
            # File.CATEGORY_CHOICES에 없으면 'other'로 fallback
            valid = [c[0] for c in File.CATEGORY_CHOICES]
            if category not in valid:
                category = 'other'
            if f.category == 'other':  # 이미 분류된 것은 덮어쓰지 않음
                f.category = category
                f.save(update_fields=['category'])
    except Exception as exc:
        logger.debug(f'NAS classify error (file_id={file_id}): {exc}')


@celery_app.task
def bulk_ocr_extract(limit: int = 100):
    """미추출 파일 일괄 OCR (정기 태스크)"""
    from .models import File
    pending = File.objects.filter(
        ocr_text='',
        mime_type__in=['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'],
    )[:limit]
    for f in pending:
        extract_ocr_text.delay(f.id)
    return f'{len(pending)}개 OCR 태스크 등록'


@celery_app.task
def sync_nas_filesystem():
    """
    NAS_MEDIA_ROOT 물리 파일시스템 → DB 자동 동기화 (주기 태스크)

    학교앱·자재·보고서 등 어느 경로에서 생성된 파일이든
    NAS 폴더에 저장되는 즉시 DB 레코드를 자동으로 생성합니다.
    """
    import mimetypes
    from django.conf import settings
    from .models import Folder, File

    SKIP_EXTENSIONS = {':zone.identifier', '.tmp', '.ds_store'}
    FOLDER_CATEGORY = {
        '장애처리보고서': 'incident', '장애': 'incident',
        '정기점검': 'regular', '케이블': 'cable', '스위치설치': 'switch',
        '산출물': 'report', '작업이미지': 'photo', '이미지': 'photo',
    }
    EXT_CATEGORY = {
        '.pdf': 'report', '.pptx': 'report', '.ppt': 'report',
        '.xlsx': 'report', '.xlsm': 'report', '.xls': 'report',
        '.jpg': 'photo', '.jpeg': 'photo', '.png': 'photo', '.gif': 'photo',
    }

    def guess_category(folder_path, fname):
        for kw, cat in FOLDER_CATEGORY.items():
            if kw in folder_path:
                return cat
        return EXT_CATEGORY.get(os.path.splitext(fname)[1].lower(), 'other')

    nas_root = getattr(settings, 'NAS_MEDIA_ROOT', str(settings.MEDIA_ROOT))
    folder_map = {}
    f_created = p_created = 0

    # 1단계: Folder 레코드
    for dirpath, dirnames, _ in os.walk(nas_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        rel = os.path.relpath(dirpath, nas_root)
        if rel == '.':
            continue
        full_path = '/' + rel.replace(os.sep, '/')
        parent_path = os.path.dirname(full_path)
        parent = folder_map.get(parent_path)

        folder = Folder.objects.filter(full_path=full_path).first()
        if not folder:
            folder = Folder.objects.create(
                name=os.path.basename(full_path),
                parent=parent if isinstance(parent, Folder) else None,
                full_path=full_path,
                is_system=True,
                access_level='admin',
            )
            f_created += 1
        folder_map[full_path] = folder

    # 2단계: File 레코드
    for dirpath, dirnames, filenames in os.walk(nas_root, topdown=True):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        rel = os.path.relpath(dirpath, nas_root)
        if rel == '.':
            continue
        full_path = '/' + rel.replace(os.sep, '/')
        folder = folder_map.get(full_path)
        if not isinstance(folder, Folder):
            continue

        for fname in filenames:
            if fname.startswith('.'):
                continue
            if any(fname.lower().endswith(s) for s in SKIP_EXTENSIONS):
                continue
            fpath = os.path.join(dirpath, fname)
            if File.objects.filter(file_path=fpath).exists():
                continue
            try:
                File.objects.create(
                    folder=folder,
                    name=fname,
                    original_name=fname,
                    file_path=fpath,
                    file_size=os.path.getsize(fpath),
                    mime_type=mimetypes.guess_type(fname)[0] or 'application/octet-stream',
                    category=guess_category(full_path, fname),
                )
                p_created += 1
            except Exception as exc:
                logger.warning(f'NAS sync 파일 등록 실패: {fpath}: {exc}')

    logger.info(f'NAS sync 완료 — 폴더 {f_created}개, 파일 {p_created}개 신규 등록')
    return f'폴더+{f_created} 파일+{p_created}'
