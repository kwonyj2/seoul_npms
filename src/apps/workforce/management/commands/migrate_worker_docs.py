"""
인력 서류·증명사진 파일을 구 구조에서 신 구조로 마이그레이션.

구 구조:
  data/인력관리/{worker_id}/증명사진/{지원청}_{이름}.{ext}
  data/인력관리/{worker_id}/{카테고리키}/파일.{ext}

신 구조:
  data/인력관리/증명사진/{지원청}_{이름[순번]}_증명사진.{ext}
  data/인력관리/{카테고리키}/{지원청}_{이름[순번]}_{카테고리라벨}.{ext}

사용법:
  python manage.py migrate_worker_docs          # dry-run (실제 이동 없음)
  python manage.py migrate_worker_docs --apply  # 실제 마이그레이션 실행
"""

import os
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.workforce.views import (
    WORKER_DOC_ALLOWED_EXTS,
    WORKER_DOC_CATEGORIES,
    _unique_doc_path,
    _worker_name_stem,
)

NAS_ROOT = os.path.join(settings.MEDIA_ROOT, 'data', '인력관리')


class Command(BaseCommand):
    help = '인력 서류·증명사진 파일을 신규 폴더 구조로 마이그레이션합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='실제로 파일을 이동합니다. 없으면 dry-run.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        mode  = '★ 실제 실행' if apply else '◆ DRY-RUN (--apply 없으면 파일 미이동)'
        self.stdout.write(self.style.WARNING(f'\n{mode}\n'))

        if not os.path.isdir(NAS_ROOT):
            self.stdout.write(self.style.ERROR(f'NAS 루트 없음: {NAS_ROOT}'))
            return

        workers = User.objects.filter(role='worker').select_related('support_center')
        moved_total = 0
        error_total = 0

        for worker in workers:
            # 구 구조 기준 디렉터리
            old_base = os.path.join(NAS_ROOT, str(worker.id))
            if not os.path.isdir(old_base):
                continue

            stem = _worker_name_stem(worker)
            self.stdout.write(f'\n[{worker.id}] {stem}')

            # ── 증명사진 ───────────────────────────────────────────────
            old_photo_dir = os.path.join(old_base, '증명사진')
            new_photo_dir = os.path.join(NAS_ROOT, '증명사진')
            if os.path.isdir(old_photo_dir):
                for fname in os.listdir(old_photo_dir):
                    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
                    if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                        continue
                    src      = os.path.join(old_photo_dir, fname)
                    new_name = f"{stem}_증명사진.{ext}"
                    dst      = os.path.join(new_photo_dir, new_name)
                    # 중복 방지
                    if os.path.exists(dst):
                        n = 2
                        while os.path.exists(dst):
                            new_name = f"{stem}_증명사진_{n}.{ext}"
                            dst = os.path.join(new_photo_dir, new_name)
                            n += 1
                    self.stdout.write(f'  [사진] {src} → {dst}')
                    if apply:
                        os.makedirs(new_photo_dir, exist_ok=True)
                        shutil.move(src, dst)
                        # profile_image 갱신
                        rel = os.path.join('data', '인력관리', '증명사진', new_name)
                        worker.profile_image = rel
                        worker.save(update_fields=['profile_image'])
                    moved_total += 1

            # ── 서류 카테고리 ──────────────────────────────────────────
            for cat in WORKER_DOC_CATEGORIES:
                old_cat_dir = os.path.join(old_base, cat['key'])
                new_cat_dir = os.path.join(NAS_ROOT, cat['key'])
                if not os.path.isdir(old_cat_dir):
                    continue
                for fname in sorted(os.listdir(old_cat_dir)):
                    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
                    if ext not in WORKER_DOC_ALLOWED_EXTS:
                        continue
                    src      = os.path.join(old_cat_dir, fname)
                    new_name = _unique_doc_path(new_cat_dir, stem, cat['label'], ext)
                    dst      = os.path.join(new_cat_dir, new_name)
                    self.stdout.write(f'  [{cat["key"]}] {src} → {dst}')
                    if apply:
                        os.makedirs(new_cat_dir, exist_ok=True)
                        shutil.move(src, dst)
                    moved_total += 1

            # 구 폴더 정리 (비어있으면 삭제)
            if apply:
                try:
                    # 빈 하위 디렉터리 제거
                    for sub in os.listdir(old_base):
                        sub_path = os.path.join(old_base, sub)
                        if os.path.isdir(sub_path) and not os.listdir(sub_path):
                            os.rmdir(sub_path)
                    if not os.listdir(old_base):
                        os.rmdir(old_base)
                        self.stdout.write(f'  → 구 폴더 삭제: {old_base}')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  구 폴더 정리 실패: {e}'))

        summary = f'\n총 {moved_total}개 파일 {"이동 완료" if apply else "이동 예정"}, 오류 {error_total}건'
        self.stdout.write(self.style.SUCCESS(summary))
        if not apply:
            self.stdout.write(self.style.WARNING('실제 이동하려면 --apply 옵션을 추가하세요.\n'))
