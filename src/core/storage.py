"""
정적 파일 최적화 스토리지

MinifyManifestStaticFilesStorage:
  - JS/CSS 파일 자동 minify (rcssmin/rjsmin)
  - WhiteNoise CompressedManifestStaticFilesStorage 상속
    → gzip 압축 + 파일명 해시(캐시 무효화) 자동 처리
"""
import logging
from django.core.files.base import ContentFile
from whitenoise.storage import CompressedManifestStaticFilesStorage

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
