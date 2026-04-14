"""
파일 스토리지

NasMediaStorage:
  - 한글 파일명·공백 보존 (Django 기본 동작: 공백→_ 변환 방지)
  - NAS 미디어 저장용

MinifyManifestStaticFilesStorage:
  - JS/CSS 파일 자동 minify (rcssmin/rjsmin)
  - WhiteNoise CompressedManifestStaticFilesStorage 상속
    → gzip 압축 + 파일명 해시(캐시 무효화) 자동 처리
"""
import logging
import re
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage


class NasMediaStorage(FileSystemStorage):
    """한글 파일명·공백을 보존하는 NAS 전용 스토리지"""

    def get_valid_name(self, name):
        s = str(name).strip()
        s = re.sub(r'[\x00-\x1f\\:*?"<>|]', '', s)
        return s

logger = logging.getLogger(__name__)

_SKIP_DIRS = ('vendor', 'fonts', 'img')


class MinifyManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """collectstatic 시 CSS/JS 파일 minify → 압축 → 해시 파일명 적용"""

    def _should_minify(self, path: str) -> bool:
        """minify 대상 여부 판단 (이미 minified 파일 및 외부 라이브러리 제외)"""
        if '.min.' in path:
            return False
        if any(skip in path for skip in _SKIP_DIRS):
            return False
        return path.endswith('.css') or path.endswith('.js')

    def post_process(self, paths, dry_run=False, **options):
        """부모 post_process 전에 CSS/JS minify 수행"""
        if not dry_run:
            for path in list(paths.keys()):
                if self._should_minify(path):
                    self._minify_file(path)
        yield from super().post_process(paths, dry_run, **options)

    def _minify_file(self, path: str):
        try:
            with self.open(path) as f:
                content = f.read().decode('utf-8', errors='replace')

            if path.endswith('.css'):
                import rcssmin
                minified = rcssmin.cssmin(content)
            else:
                import rjsmin
                minified = rjsmin.jsmin(content)

            self._save(path, ContentFile(minified.encode('utf-8')))
            logger.debug(f'Minified: {path} ({len(content)} → {len(minified)} chars)')
        except Exception as e:
            logger.warning(f'Minify failed for {path}: {e}')
