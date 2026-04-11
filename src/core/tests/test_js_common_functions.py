"""
Phase 3-6: JS 공통 함수 정리 테스트
JavaScript Common Function Organization Tests

검증 항목:
  1. npms.js 에 필수 공통 함수 전부 존재
  2. npms.js 정적 파일 서빙 (200 OK)
  3. 일반 템플릿이 npms.js 의 함수를 중복 정의하지 않음
  4. mobile/utils.js 존재 및 모바일 공통 함수 포함
  5. mobile/base.html 이 mobile/utils.js 를 로드
  6. 모바일 템플릿이 showToastLocal 을 중복 정의하지 않음
"""
import os
import re
from django.test import TestCase, Client
from django.conf import settings


# ─────────────────────────────────────────
# 파일 경로 헬퍼
# ─────────────────────────────────────────

BASE_DIR    = settings.BASE_DIR  # /app 또는 /home/kwonyj/network_pms/src
STATIC_DIR  = os.path.join(BASE_DIR, 'static')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

NPMS_JS         = os.path.join(STATIC_DIR, 'js', 'npms.js')
MOBILE_UTILS_JS = os.path.join(STATIC_DIR, 'mobile', 'js', 'utils.js')
MOBILE_BASE_HTML = os.path.join(TEMPLATE_DIR, 'mobile', 'base.html')


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _has_func(source, func_name):
    """source 에 'function func_name' 선언이 포함되어 있는지 확인."""
    pattern = rf'\bfunction\s+{re.escape(func_name)}\s*\('
    return bool(re.search(pattern, source))


def _has_class(source, class_name):
    pattern = rf'\bclass\s+{re.escape(class_name)}\b'
    return bool(re.search(pattern, source))


# ─────────────────────────────────────────
# 1. npms.js 필수 함수 존재 검증
# ─────────────────────────────────────────

class NpmsJsRequiredFunctionsTest(TestCase):
    """npms.js 에 모든 공통 유틸 함수가 정의되어 있어야 한다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = _read(NPMS_JS)

    def test_getCsrfToken_defined(self):
        self.assertTrue(_has_func(self.source, 'getCsrfToken'),
                        'getCsrfToken 함수가 npms.js 에 없습니다')

    def test_apiGet_defined(self):
        self.assertTrue(_has_func(self.source, 'apiGet'))

    def test_apiPost_defined(self):
        self.assertTrue(_has_func(self.source, 'apiPost'))

    def test_apiPatch_defined(self):
        self.assertTrue(_has_func(self.source, 'apiPatch'))

    def test_apiDelete_defined(self):
        self.assertTrue(_has_func(self.source, 'apiDelete'))

    def test_showToast_defined(self):
        self.assertTrue(_has_func(self.source, 'showToast'))

    def test_formatDate_defined(self):
        self.assertTrue(_has_func(self.source, 'formatDate'))

    def test_formatDateTime_defined(self):
        self.assertTrue(_has_func(self.source, 'formatDateTime'))

    def test_timeAgo_defined(self):
        self.assertTrue(_has_func(self.source, 'timeAgo'))

    def test_numFmt_defined(self):
        self.assertTrue(_has_func(self.source, 'numFmt'))

    def test_confirmAction_defined(self):
        self.assertTrue(_has_func(self.source, 'confirmAction'))

    def test_debounce_defined(self):
        """debounce 는 공통 유틸이므로 npms.js 에 있어야 한다."""
        self.assertTrue(_has_func(self.source, 'debounce'),
                        'debounce 함수가 npms.js 에 없습니다')

    def test_SignaturePad_class_defined(self):
        self.assertTrue(_has_class(self.source, 'SignaturePad'))

    def test_startGpsTracking_defined(self):
        self.assertTrue(_has_func(self.source, 'startGpsTracking'))

    def test_stopGpsTracking_defined(self):
        self.assertTrue(_has_func(self.source, 'stopGpsTracking'))


# ─────────────────────────────────────────
# 2. npms.js 정적 파일 서빙 테스트
# ─────────────────────────────────────────

class NpmsJsStaticServingTest(TestCase):
    """npms.js 가 정적 파일로 서빙되는지 확인."""

    def setUp(self):
        self.client = Client()
        from apps.accounts.models import User
        self.user = User.objects.create_user(
            username='jstest_user', email='jstest@test.com',
            password='testpass1234', role='admin',
        )
        self.client.force_login(self.user)

    def test_npms_js_file_exists_on_disk(self):
        self.assertTrue(os.path.exists(NPMS_JS),
                        f'npms.js 파일이 없습니다: {NPMS_JS}')

    def test_npms_js_not_empty(self):
        self.assertGreater(os.path.getsize(NPMS_JS), 1000,
                           'npms.js 파일이 너무 작습니다 (1KB 미만)')

    def test_npms_js_served_200(self):
        """DEBUG=True 환경에서 /static/js/npms.js 200 반환."""
        if not settings.DEBUG:
            self.skipTest('DEBUG=False 환경에서는 정적 파일 서빙 생략')
        resp = self.client.get('/static/js/npms.js')
        self.assertEqual(resp.status_code, 200)

    def test_npms_js_content_type_javascript(self):
        if not settings.DEBUG:
            self.skipTest('DEBUG=False 환경에서는 정적 파일 서빙 생략')
        resp = self.client.get('/static/js/npms.js')
        self.assertIn('javascript', resp.get('Content-Type', ''))


# ─────────────────────────────────────────
# 3. 일반 템플릿 중복 함수 제거 검증
# ─────────────────────────────────────────

class TemplateDuplicateFunctionTest(TestCase):
    """
    base.html 을 상속하는 일반 템플릿은 npms.js 가 자동 로드되므로
    공통 함수를 중복 정의해선 안 된다.
    """

    def _assert_no_func(self, template_rel_path, func_name):
        path = os.path.join(TEMPLATE_DIR, template_rel_path)
        source = _read(path)
        has = _has_func(source, func_name)
        self.assertFalse(has,
            f'{template_rel_path} 에 {func_name}() 중복 정의가 남아 있습니다. '
            f'npms.js 의 전역 함수를 사용하세요.')

    # ── incidents/sla.html ─────────────────────────────────────
    def test_sla_no_duplicate_showToast(self):
        self._assert_no_func('incidents/sla.html', 'showToast')

    def test_sla_no_duplicate_getCsrfToken(self):
        self._assert_no_func('incidents/sla.html', 'getCsrfToken')

    # ── workforce/attendance.html ──────────────────────────────
    def test_attendance_no_duplicate_showToast(self):
        self._assert_no_func('workforce/attendance.html', 'showToast')

    # ── workforce/workers.html ─────────────────────────────────
    def test_workers_no_duplicate_showToast(self):
        self._assert_no_func('workforce/workers.html', 'showToast')

    # ── nas/index.html ────────────────────────────────────────
    def test_nas_no_duplicate_getCsrfToken(self):
        self._assert_no_func('nas/index.html', 'getCsrfToken')

    # ── materials/index.html ──────────────────────────────────
    def test_materials_no_duplicate_numFmt(self):
        self._assert_no_func('materials/index.html', 'numFmt')

    def test_materials_no_duplicate_formatDate(self):
        self._assert_no_func('materials/index.html', 'formatDate')


# ─────────────────────────────────────────
# 4. mobile/utils.js 존재 및 모바일 공통 함수
# ─────────────────────────────────────────

class MobileUtilsJsTest(TestCase):
    """mobile/utils.js 가 모바일 공통 함수를 포함해야 한다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.path = MOBILE_UTILS_JS
        cls.exists = os.path.exists(cls.path)
        cls.source = _read(cls.path) if cls.exists else ''

    def test_mobile_utils_js_file_exists(self):
        self.assertTrue(self.exists,
                        f'mobile/utils.js 파일이 없습니다: {self.path}')

    def test_mobile_utils_has_showToastLocal(self):
        """모바일 전용 토스트: 화면 하단 중앙 표시."""
        self.assertTrue(_has_func(self.source, 'showToastLocal'),
                        'showToastLocal 함수가 mobile/utils.js 에 없습니다')

    def test_showToastLocal_bottom_center_style(self):
        """showToastLocal 은 bottom-center(left:50%) 스타일이어야 한다."""
        self.assertIn('50%', self.source,
                      'showToastLocal 이 bottom-center 스타일을 사용하지 않습니다')

    def test_mobile_utils_not_empty(self):
        self.assertGreater(len(self.source), 100,
                           'mobile/utils.js 파일이 너무 작습니다')


# ─────────────────────────────────────────
# 5. mobile/base.html 에서 utils.js 로드
# ─────────────────────────────────────────

class MobileBaseHtmlLoadsUtilsTest(TestCase):
    """mobile/base.html 이 mobile/utils.js 를 script 태그로 포함해야 한다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = _read(MOBILE_BASE_HTML)

    def test_mobile_base_loads_utils_js(self):
        self.assertIn('mobile/js/utils.js', self.source,
                      'mobile/base.html 이 mobile/js/utils.js 를 로드하지 않습니다')

    def test_mobile_base_script_tag_format(self):
        """script src 태그로 포함되어야 한다."""
        has_script = bool(re.search(r'<script[^>]+mobile/js/utils\.js', self.source))
        self.assertTrue(has_script,
                        'mobile/base.html 에 <script src="...mobile/js/utils.js"> 가 없습니다')


# ─────────────────────────────────────────
# 6. 모바일 템플릿 showToastLocal 중복 제거
# ─────────────────────────────────────────

class MobileTemplateDuplicateFunctionTest(TestCase):
    """
    mobile/utils.js 가 로드된 후에는 모바일 템플릿에서
    showToastLocal 을 중복 정의할 필요가 없다.
    """

    def _assert_no_func(self, template_rel_path, func_name):
        path = os.path.join(TEMPLATE_DIR, template_rel_path)
        source = _read(path)
        self.assertFalse(_has_func(source, func_name),
            f'{template_rel_path} 에 {func_name}() 중복 정의가 남아 있습니다. '
            f'mobile/utils.js 의 공통 함수를 사용하세요.')

    def test_mobile_incident_detail_no_showToastLocal(self):
        self._assert_no_func('mobile/incident_detail.html', 'showToastLocal')

    def test_mobile_report_cable_no_showToastLocal(self):
        self._assert_no_func('mobile/report_cable.html', 'showToastLocal')

    def test_mobile_report_switch_no_showToastLocal(self):
        self._assert_no_func('mobile/report_switch.html', 'showToastLocal')


# ─────────────────────────────────────────
# 7. npms.js 함수 시그니처 정합성 검증
# ─────────────────────────────────────────

class NpmsJsFunctionSignatureTest(TestCase):
    """npms.js 함수 파라미터 시그니처가 올바른지 검증."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = _read(NPMS_JS)

    def test_showToast_has_type_param(self):
        """showToast(message, type) 형태여야 한다."""
        m = re.search(r'function showToast\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m, 'showToast 함수 시그니처를 찾을 수 없습니다')
        params = m.group(1)
        self.assertGreaterEqual(params.count(','), 1,
                                'showToast 는 message, type 두 인자가 필요합니다')

    def test_apiGet_has_params(self):
        """apiGet(url, params) 형태여야 한다."""
        m = re.search(r'async function apiGet\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m)
        self.assertIn('url', m.group(1))

    def test_apiPost_has_data_param(self):
        m = re.search(r'async function apiPost\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m)
        self.assertIn('data', m.group(1))

    def test_debounce_has_fn_and_delay(self):
        """debounce(fn, delay) 형태여야 한다."""
        m = re.search(r'function debounce\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m, 'debounce 함수 시그니처를 찾을 수 없습니다')
        params = m.group(1)
        self.assertGreaterEqual(params.count(','), 1,
                                'debounce 는 fn, delay 두 인자가 필요합니다')

    def test_numFmt_single_param(self):
        m = re.search(r'function numFmt\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m)
        # 인자가 1개 이상
        self.assertTrue(len(m.group(1).strip()) > 0)

    def test_formatDate_single_param(self):
        m = re.search(r'function formatDate\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m)

    def test_confirmAction_has_callback(self):
        m = re.search(r'function confirmAction\s*\(([^)]+)\)', self.source)
        self.assertIsNotNone(m)
        params = m.group(1)
        self.assertIn('callback', params)
