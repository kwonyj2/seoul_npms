import os
import logging
from config.celery import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name='apps.workforce.tasks.convert_career_pptx')
def convert_career_pptx():
    """경력프로필 폴더의 PPTX 파일을 JPG로 일괄 변환.
    이미 변환된 파일(mtime 비교)은 건너뜀.
    """
    from django.conf import settings
    import subprocess
    import tempfile
    import shutil

    career_dir = os.path.join(settings.MEDIA_ROOT, '인력관리', '경력프로필')
    if not os.path.isdir(career_dir):
        return 'career dir not found'

    converted = 0
    skipped = 0
    errors = []

    for fname in os.listdir(career_dir):
        if not fname.lower().endswith('.pptx'):
            continue

        pptx_path = os.path.join(career_dir, fname)
        jpg_path = os.path.splitext(pptx_path)[0] + '.jpg'

        # 이미 변환된 jpg가 최신이면 스킵
        if os.path.isfile(jpg_path):
            if os.path.getmtime(jpg_path) >= os.path.getmtime(pptx_path):
                skipped += 1
                continue

        base_name = os.path.splitext(fname)[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # PPTX → PDF
                result = subprocess.run([
                    'libreoffice', '--headless', '--convert-to', 'pdf',
                    '--outdir', tmpdir, pptx_path
                ], timeout=60, capture_output=True)
                pdf_path = os.path.join(tmpdir, base_name + '.pdf')
                if not os.path.isfile(pdf_path):
                    errors.append(f'{fname}: PDF 변환 실패')
                    continue

                # PDF → JPG (첫 페이지만)
                subprocess.run([
                    'pdftoppm', '-jpeg', '-r', '200', '-f', '1', '-l', '1',
                    '-singlefile', pdf_path, os.path.join(tmpdir, 'out')
                ], timeout=30, capture_output=True)
                tmp_jpg = os.path.join(tmpdir, 'out.jpg')
                if os.path.isfile(tmp_jpg):
                    shutil.move(tmp_jpg, jpg_path)
                    converted += 1
                else:
                    errors.append(f'{fname}: JPG 변환 실패')
            except Exception as e:
                errors.append(f'{fname}: {str(e)}')

    msg = f'converted={converted}, skipped={skipped}, errors={len(errors)}'
    if errors:
        logger.warning(f'convert_career_pptx: {msg} — {errors}')
    else:
        logger.info(f'convert_career_pptx: {msg}')
    return msg
