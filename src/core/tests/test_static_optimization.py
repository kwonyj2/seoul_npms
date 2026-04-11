"""
Phase 6-3: 정적 파일 최적화 테스트

테스트 범위:
  1. JS/CSS minify — rcssmin/rjsmin + MinifyManifestStaticFilesStorage
  2. nginx gzip 설정 — nginx.conf 검증
  3. 브라우저 캐시 헤더 — nginx 1년 캐시
  4. 폰트 preload 태그 — base.html
"""
import os
from django.test import TestCase


# ─────────────────────────────────────────────────────────────
# 1. Minify 패키지 + Storage
# ─────────────────────────────────────────────────────────────
class MinifyPackageTest(TestCase):
    """rcssmin/rjsmin 패키지가 설치되어야 한다"""

    def test_rcssmin_importable(self):
        try:
            import rcssmin
        except ImportError:
            self.fail('rcssmin 패키지가 설치되지 않았습니다.')

    def test_rjsmin_importable(self):
        try:
            import rjsmin
        except ImportError:
            self.fail('rjsmin 패키지가 설치되지 않았습니다.')

    def test_rcssmin_minifies_css(self):
        """rcssmin이 실제로 CSS를 최소화해야 한다"""
        import rcssmin
        css = '  body   {   color:  red;  /* comment */ }  '
        result = rcssmin.cssmin(css)
        self.assertLess(len(result), len(css))
        self.assertNotIn('/* comment */', result)

    def test_rjsmin_minifies_js(self):
        """rjsmin이 실제로 JS를 최소화해야 한다"""
        import rjsmin
        js = '  var x   =  1;   // comment\n  var y = 2;  '
        result = rjsmin.jsmin(js)
        self.assertLess(len(result), len(js))


class MinifyStorageTest(TestCase):
    """MinifyManifestStaticFilesStorage 클래스"""

    def test_storage_class_importable(self):
        try:
            from core.storage import MinifyManifestStaticFilesStorage
        except ImportError:
            self.fail('core.storage.MinifyManifestStaticFilesStorage 가 없습니다.')

    def test_storage_inherits_whitenoise(self):
        """WhiteNoise CompressedManifestStaticFilesStorage 상속"""
        from core.storage import MinifyManifestStaticFilesStorage
        from whitenoise.storage import CompressedManifestStaticFilesStorage
        self.assertTrue(
            issubclass(MinifyManifestStaticFilesStorage, CompressedManifestStaticFilesStorage)
        )

    def test_staticfiles_storage_setting(self):
        """settings.STATICFILES_STORAGE 가 MinifyManifestStaticFilesStorage 이어야 한다"""
        from django.conf import settings
        self.assertIn(
            'MinifyManifestStaticFilesStorage',
            settings.STATICFILES_STORAGE,
            'STATICFILES_STORAGE가 MinifyManifestStaticFilesStorage 이 아닙니다.'
        )


# ─────────────────────────────────────────────────────────────
# 2. nginx gzip 설정
# ─────────────────────────────────────────────────────────────
class NginxGzipTest(TestCase):
    """nginx.conf gzip / 캐시 설정"""

    def _get_nginx_conf(self):
        from django.conf import settings
        conf_path = os.path.join(str(settings.BASE_DIR), 'infra', 'nginx.conf')
        with open(conf_path) as f:
            return f.read()

    def test_nginx_conf_has_gzip_on(self):
        """nginx.conf에 gzip on 설정이 있어야 한다"""
        conf = self._get_nginx_conf()
        self.assertIn('gzip on', conf, 'nginx.conf에 gzip on이 없습니다.')

    def test_nginx_conf_has_gzip_types(self):
        """gzip_types에 CSS/JS가 포함되어야 한다"""
        conf = self._get_nginx_conf()
        self.assertIn('gzip_types', conf)
        self.assertIn('text/css', conf)

    def test_nginx_static_expires_1y(self):
        """정적 파일 캐시가 1년(max 또는 365d/1y) 이어야 한다"""
        conf = self._get_nginx_conf()
        # expires max 또는 1y 또는 365d
        has_long_cache = any(
            marker in conf
            for marker in ('expires max', 'expires 1y', 'expires 365d')
        )
        self.assertTrue(has_long_cache, 'nginx 정적 파일 캐시가 1년이 아닙니다.')

    def test_nginx_gzip_comp_level(self):
        """gzip_comp_level 이 설정되어야 한다"""
        conf = self._get_nginx_conf()
        self.assertIn('gzip_comp_level', conf)

    def test_nginx_cache_control_immutable(self):
        """정적 파일에 Cache-Control: immutable 헤더가 설정되어야 한다"""
        conf = self._get_nginx_conf()
        self.assertIn('immutable', conf, 'nginx에 Cache-Control immutable이 없습니다.')


# ─────────────────────────────────────────────────────────────
# 3. 폰트 preload 태그 (base.html)
# ─────────────────────────────────────────────────────────────
class FontPreloadTest(TestCase):
    """base.html에 font preload 태그가 있어야 한다"""

    def _get_base_html(self):
        from django.conf import settings
        base_path = os.path.join(str(settings.BASE_DIR), 'templates', 'base.html')
        with open(base_path) as f:
            return f.read()

    def test_base_has_font_preload_link(self):
        """<link rel="preload" as="font"> 태그가 있어야 한다"""
        html = self._get_base_html()
        self.assertIn('rel="preload"', html, 'base.html에 preload 태그가 없습니다.')
        self.assertIn('as="font"', html, 'base.html에 font preload가 없습니다.')

    def test_base_has_css_preload(self):
        """CSS 파일도 preload되어야 한다 (rel=preload as=style 또는 dns-prefetch)"""
        html = self._get_base_html()
        has_preload = 'rel="preload"' in html or 'rel="dns-prefetch"' in html
        self.assertTrue(has_preload, 'base.html에 resource preload 힌트가 없습니다.')

    def test_font_preload_has_crossorigin(self):
        """font preload는 crossorigin 속성이 필요하다"""
        html = self._get_base_html()
        self.assertIn('crossorigin', html, 'font preload에 crossorigin이 없습니다.')

    def test_npms_css_has_font_face(self):
        """npms.css에 @font-face 가 정의되어야 한다"""
        from django.conf import settings
        css_path = os.path.join(str(settings.BASE_DIR), 'static', 'css', 'npms.css')
        with open(css_path) as f:
            content = f.read()
        self.assertIn('@font-face', content, 'npms.css에 @font-face가 없습니다.')
