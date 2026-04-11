"""
NAS 파일시스템 → DB 동기화 관리 명령

NAS_MEDIA_ROOT 하위 물리 파일/폴더를 스캔하여
Folder / File DB 레코드를 일괄 생성합니다.
이미 DB에 있는 항목은 건너뜁니다 (중복 없음).

사용법:
    python manage.py sync_nas_files             # 실제 실행
    python manage.py sync_nas_files --dry-run   # 통계만 출력
"""
import os
import mimetypes
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.nas.models import Folder, File


# 폴더 경로 키워드 → 카테고리
FOLDER_CATEGORY = {
    '장애처리보고서': 'incident',
    '장애': 'incident',
    '정기점검': 'regular',
    '케이블': 'cable',
    '스위치설치': 'switch',
    '산출물': 'report',
    '작업이미지': 'photo',
    '이미지': 'photo',
}

# 확장자 → 카테고리
EXT_CATEGORY = {
    '.pdf':  'report',
    '.pptx': 'report', '.ppt': 'report',
    '.xlsx': 'report', '.xlsm': 'report', '.xls': 'report',
    '.docx': 'other',  '.doc': 'other',
    '.jpg':  'photo',  '.jpeg': 'photo',
    '.png':  'photo',  '.gif': 'photo', '.bmp': 'photo',
}

SKIP_EXTENSIONS = {':zone.identifier', '.tmp', '.ds_store'}


def guess_category(folder_full_path: str, filename: str) -> str:
    for kw, cat in FOLDER_CATEGORY.items():
        if kw in folder_full_path:
            return cat
    ext = os.path.splitext(filename)[1].lower()
    return EXT_CATEGORY.get(ext, 'other')


class Command(BaseCommand):
    help = 'NAS_MEDIA_ROOT 물리 파일시스템을 스캔해 Folder/File DB 레코드를 생성합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='DB 변경 없이 생성 대상 건수만 출력합니다.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        nas_root = getattr(settings, 'NAS_MEDIA_ROOT', str(settings.MEDIA_ROOT))

        self.stdout.write(f'[sync_nas_files] 스캔 경로: {nas_root}')
        if dry_run:
            self.stdout.write(self.style.WARNING('  ※ DRY-RUN 모드 — DB 변경 없음\n'))

        folder_map: dict[str, object] = {}  # full_path → Folder instance (or namespace)
        f_created = f_skip = 0
        p_created = p_skip = p_err = 0

        # ── 1단계: Folder 레코드 (topdown → 부모 먼저 생성됨) ────────
        for dirpath, dirnames, _ in os.walk(nas_root, topdown=True):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))

            rel = os.path.relpath(dirpath, nas_root)
            if rel == '.':
                continue  # 루트 자체는 폴더로 등록하지 않음

            full_path = '/' + rel.replace(os.sep, '/')
            folder_name = os.path.basename(full_path)
            parent_path = os.path.dirname(full_path)
            parent = folder_map.get(parent_path)  # None이면 최상위

            # DB에서 기존 레코드 확인
            existing = Folder.objects.filter(full_path=full_path).first()
            if existing:
                folder_map[full_path] = existing
                f_skip += 1
                continue

            # 신규 생성
            if dry_run:
                folder = SimpleNamespace(id=None, full_path=full_path)
                self.stdout.write(f'  [폴더+] {full_path}')
            else:
                folder = Folder.objects.create(
                    name=folder_name,
                    parent=parent if isinstance(parent, Folder) else None,
                    full_path=full_path,
                    is_system=True,
                    access_level='admin',
                )
                self.stdout.write(f'  [폴더+] {full_path}')

            folder_map[full_path] = folder
            f_created += 1

        # ── 2단계: File 레코드 ────────────────────────────────────────
        for dirpath, dirnames, filenames in os.walk(nas_root, topdown=True):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))

            rel = os.path.relpath(dirpath, nas_root)
            if rel == '.':
                continue

            full_path = '/' + rel.replace(os.sep, '/')
            folder = folder_map.get(full_path)
            if folder is None:
                continue

            for fname in sorted(filenames):
                # 숨김/임시 파일 건너뜀
                fname_lower = fname.lower()
                if fname.startswith('.'):
                    continue
                if any(fname_lower.endswith(skip) for skip in SKIP_EXTENSIONS):
                    continue

                fpath = os.path.join(dirpath, fname)

                # 이미 DB에 있으면 스킵
                if File.objects.filter(file_path=fpath).exists():
                    p_skip += 1
                    continue

                try:
                    size = os.path.getsize(fpath)
                    mime = mimetypes.guess_type(fname)[0] or 'application/octet-stream'
                    cat = guess_category(full_path, fname)

                    if not dry_run and isinstance(folder, Folder):
                        File.objects.create(
                            folder=folder,
                            name=fname,
                            original_name=fname,
                            file_path=fpath,
                            file_size=size,
                            mime_type=mime,
                            category=cat,
                        )
                    p_created += 1

                    if p_created % 500 == 0:
                        self.stdout.write(f'    파일 등록 진행 중 ... {p_created}건')

                except Exception as exc:
                    p_err += 1
                    self.stderr.write(f'  [오류] {fpath}: {exc}')

        # ── 결과 요약 ─────────────────────────────────────────────────
        mode = '(DRY-RUN) ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{mode}완료 ─ '
            f'폴더: 생성={f_created} / 기존={f_skip}  |  '
            f'파일: 등록={p_created} / 기존={p_skip} / 오류={p_err}'
        ))
