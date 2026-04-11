"""
Phase 3-7: 에러 핸들링 정비 테스트

테스트 범위:
  1. _is_api() 탐지 로직
  2. custom_404 / custom_500 응답 포맷 & 로깅
  3. DRF 커스텀 exception_handler 설정 및 표준 포맷
  4. AuditLogMiddleware 로깅 범위 (변경 메서드만)
  5. SessionTrackingMiddleware DB 오류 무시
"""
import json
import logging
from unittest.mock import MagicMock, patch, call

from django.conf import settings
from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import (
    ValidationError,
    NotFound,
    PermissionDenied,
    AuthenticationFailed,
)

from core.error_views import _is_api, custom_404, custom_500


# ─────────────────────────────────────────────────────────────
# 1. _is_api() 탐지 로직
# ─────────────────────────────────────────────────────────────
class IsApiDetectionTest(TestCase):
    """_is_api(request) — 경로·Accept 헤더 기반 API 판별"""

    def _make_request(self, path, accept='text/html'):
        req = RequestFactory().get(path, HTTP_ACCEPT=accept)
        return req

    def test_api_prefix_returns_true(self):
        req = self._make_request('/api/incidents/')
        self.assertTrue(_is_api(req))

    def test_npms_api_prefix_returns_true(self):
        # FORCE_SCRIPT_NAME='/npms' 이므로 factory path를 직접 조작
        req = self._make_request('/anything/')
        req.path = '/npms/api/incidents/'   # SCRIPT_NAME 포함 경로 직접 지정
        self.assertTrue(_is_api(req))

    def test_accept_json_returns_true(self):
        req = self._make_request('/some/page/', accept='application/json')
        self.assertTrue(_is_api(req))

    def test_accept_json_mixed_returns_true(self):
        req = self._make_request('/some/page/', accept='text/html,application/json,*/*')
        self.assertTrue(_is_api(req))

    def test_regular_path_returns_false(self):
        req = self._make_request('/npms/incidents/')
        self.assertFalse(_is_api(req))

    def test_empty_path_returns_false(self):
        req = self._make_request('/')
        self.assertFalse(_is_api(req))

    def test_api_path_no_json_accept_still_true(self):
        # 경로 기준만으로도 True
        req = self._make_request('/api/reports/reports/', accept='text/html')
        self.assertTrue(_is_api(req))


# ─────────────────────────────────────────────────────────────
# 2. custom_404 뷰
# ─────────────────────────────────────────────────────────────
class Custom404ViewTest(TestCase):
    """custom_404() — 응답 포맷 및 로깅"""

    def setUp(self):
        self.factory = RequestFactory()

    # API → JSON 응답
    def test_api_request_returns_json(self):
        req = self.factory.get('/api/unknown/')
        resp = custom_404(req)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp['Content-Type'], 'application/json')

    def test_api_json_contains_error_key(self):
        req = self.factory.get('/api/unknown/')
        data = json.loads(custom_404(req).content)
        self.assertIn('error', data)

    def test_api_json_contains_path_key(self):
        # FORCE_SCRIPT_NAME='/npms' → factory.get('/api/x/') 시 request.path = '/npms/api/x/'
        req = self.factory.get('/api/unknown/')
        data = json.loads(custom_404(req).content)
        self.assertIn('/api/unknown/', data['path'])   # 실제 path 값이 포함되어야 함

    def test_api_json_error_value(self):
        req = self.factory.get('/api/unknown/')
        data = json.loads(custom_404(req).content)
        self.assertEqual(data['error'], 'Not Found')

    # 브라우저 → HTML 응답
    def test_browser_request_returns_html(self):
        req = self.factory.get('/npms/missing/')
        resp = custom_404(req)
        self.assertEqual(resp.status_code, 404)
        self.assertIn('text/html', resp['Content-Type'])

    def test_browser_response_contains_html_tag(self):
        req = self.factory.get('/npms/missing/')
        content = custom_404(req).content.decode()
        # 템플릿 렌더 성공 시 HTML, 폴백 시 h1 태그 — 어느 쪽이든 HTML 포함
        self.assertTrue('<' in content)

    # 로깅
    def test_warning_logged_for_api(self):
        req = self.factory.get('/api/unknown/')
        with self.assertLogs('apps.errors', level='WARNING') as cm:
            custom_404(req)
        self.assertTrue(any('404' in line for line in cm.output))

    def test_warning_logged_for_browser(self):
        req = self.factory.get('/npms/missing/')
        with self.assertLogs('apps.errors', level='WARNING') as cm:
            custom_404(req)
        self.assertTrue(any('404' in line for line in cm.output))

    def test_warning_includes_method_and_path(self):
        req = self.factory.get('/api/missing/')
        with self.assertLogs('apps.errors', level='WARNING') as cm:
            custom_404(req)
        log_line = cm.output[0]
        self.assertIn('GET', log_line)
        self.assertIn('/api/missing/', log_line)

    # 템플릿 폴백
    def test_template_fallback_on_render_failure(self):
        req = self.factory.get('/npms/missing/')
        with patch('core.error_views.render_to_string', side_effect=Exception('fail')):
            resp = custom_404(req)
        self.assertEqual(resp.status_code, 404)
        content = resp.content.decode()
        self.assertIn('404', content)


# ─────────────────────────────────────────────────────────────
# 3. custom_500 뷰
# ─────────────────────────────────────────────────────────────
class Custom500ViewTest(TestCase):
    """custom_500() — 응답 포맷 및 로깅"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_api_request_returns_json_500(self):
        req = self.factory.get('/api/crash/')
        resp = custom_500(req)
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp['Content-Type'], 'application/json')

    def test_api_json_contains_error_key(self):
        req = self.factory.get('/api/crash/')
        data = json.loads(custom_500(req).content)
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Internal Server Error')

    def test_api_json_no_path_key(self):
        # 500에는 path 노출 없음 (정보 유출 방지)
        req = self.factory.get('/api/crash/')
        data = json.loads(custom_500(req).content)
        self.assertNotIn('path', data)

    def test_browser_request_returns_html_500(self):
        req = self.factory.get('/npms/crash/')
        resp = custom_500(req)
        self.assertEqual(resp.status_code, 500)
        self.assertIn('text/html', resp['Content-Type'])

    def test_error_logged_for_api(self):
        req = self.factory.get('/api/crash/')
        with self.assertLogs('apps.errors', level='ERROR') as cm:
            custom_500(req)
        self.assertTrue(any('500' in line for line in cm.output))

    def test_error_logged_for_browser(self):
        req = self.factory.get('/npms/crash/')
        with self.assertLogs('apps.errors', level='ERROR') as cm:
            custom_500(req)
        self.assertTrue(any('500' in line for line in cm.output))

    def test_error_log_includes_method_and_path(self):
        req = self.factory.get('/api/crash/')
        with self.assertLogs('apps.errors', level='ERROR') as cm:
            custom_500(req)
        log_line = cm.output[0]
        self.assertIn('GET', log_line)
        self.assertIn('/api/crash/', log_line)

    def test_template_fallback_on_render_failure(self):
        req = self.factory.get('/npms/crash/')
        with patch('core.error_views.render_to_string', side_effect=Exception('fail')):
            resp = custom_500(req)
        self.assertEqual(resp.status_code, 500)
        content = resp.content.decode()
        self.assertIn('500', content)


# ─────────────────────────────────────────────────────────────
# 4. DRF 커스텀 exception_handler 설정 및 포맷
# ─────────────────────────────────────────────────────────────
class DRFExceptionHandlerConfigTest(TestCase):
    """REST_FRAMEWORK에 EXCEPTION_HANDLER 설정 확인"""

    def test_exception_handler_configured_in_settings(self):
        """REST_FRAMEWORK에 커스텀 EXCEPTION_HANDLER가 등록되어야 한다"""
        rf = getattr(settings, 'REST_FRAMEWORK', {})
        self.assertIn(
            'EXCEPTION_HANDLER', rf,
            'REST_FRAMEWORK에 EXCEPTION_HANDLER 키가 없습니다. '
            'core/exceptions.py 작성 후 settings에 등록하세요.'
        )

    def test_exception_handler_points_to_core(self):
        """EXCEPTION_HANDLER가 core.exceptions 모듈을 가리켜야 한다"""
        rf = getattr(settings, 'REST_FRAMEWORK', {})
        handler = rf.get('EXCEPTION_HANDLER', '')
        self.assertTrue(
            handler.startswith('core.exceptions'),
            f'EXCEPTION_HANDLER={handler!r} — core.exceptions 모듈이어야 합니다.'
        )


class DRFExceptionHandlerFormatTest(TestCase):
    """custom_exception_handler() — 표준 에러 응답 포맷"""

    def _call_handler(self, exc, ctx=None):
        from core.exceptions import custom_exception_handler
        return custom_exception_handler(exc, ctx or {})

    def test_validation_error_has_error_key(self):
        resp = self._call_handler(ValidationError({'field': ['required']}))
        self.assertIsNotNone(resp)
        data = resp.data
        self.assertIn('error', data)

    def test_not_found_has_error_key(self):
        resp = self._call_handler(NotFound())
        self.assertIsNotNone(resp)
        self.assertIn('error', resp.data)

    def test_permission_denied_has_error_key(self):
        resp = self._call_handler(PermissionDenied())
        self.assertIsNotNone(resp)
        self.assertIn('error', resp.data)

    def test_authentication_failed_has_error_key(self):
        resp = self._call_handler(AuthenticationFailed())
        self.assertIsNotNone(resp)
        self.assertIn('error', resp.data)

    def test_validation_error_has_detail_key(self):
        resp = self._call_handler(ValidationError({'field': ['required']}))
        self.assertIn('detail', resp.data)

    def test_non_api_exception_returns_none(self):
        # DRF가 처리하지 않는 예외 → None 반환 (Django 기본 처리 위임)
        resp = self._call_handler(ValueError('unknown'))
        self.assertIsNone(resp)

    def test_validation_error_status_400(self):
        resp = self._call_handler(ValidationError('invalid'))
        self.assertEqual(resp.status_code, 400)

    def test_not_found_status_404(self):
        resp = self._call_handler(NotFound())
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_status_403(self):
        resp = self._call_handler(PermissionDenied())
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────────────────────────
# 5. AuditLogMiddleware
# ─────────────────────────────────────────────────────────────
class AuditLogMiddlewareTest(TestCase):
    """AuditLogMiddleware — 변경 메서드만 로깅"""

    def _make_middleware(self, response_status=200):
        from core.middleware.audit import AuditLogMiddleware
        mock_response = MagicMock()
        mock_response.status_code = response_status
        get_response = MagicMock(return_value=mock_response)
        return AuditLogMiddleware(get_response)

    def _make_request(self, method, path='/api/incidents/1/'):
        from django.test import RequestFactory
        factory = RequestFactory()
        from apps.accounts.models import User
        user = MagicMock(spec=User)
        user.is_authenticated = True
        user.__str__ = lambda s: 'testuser'

        req = getattr(factory, method.lower())(path)
        req.user = user
        return req

    def test_post_request_is_logged(self):
        mw = self._make_middleware()
        req = self._make_request('POST')
        with self.assertLogs('audit', level='INFO') as cm:
            mw(req)
        self.assertTrue(any('POST' in line for line in cm.output))

    def test_put_request_is_logged(self):
        mw = self._make_middleware()
        req = self._make_request('PUT')
        with self.assertLogs('audit', level='INFO') as cm:
            mw(req)
        self.assertTrue(any('PUT' in line for line in cm.output))

    def test_patch_request_is_logged(self):
        mw = self._make_middleware()
        req = self._make_request('PATCH')
        with self.assertLogs('audit', level='INFO') as cm:
            mw(req)
        self.assertTrue(any('PATCH' in line for line in cm.output))

    def test_delete_request_is_logged(self):
        mw = self._make_middleware()
        req = self._make_request('DELETE')
        with self.assertLogs('audit', level='INFO') as cm:
            mw(req)
        self.assertTrue(any('DELETE' in line for line in cm.output))

    def test_get_request_not_logged(self):
        mw = self._make_middleware()
        req = self._make_request('GET')
        import logging as _logging
        with self.assertRaises(AssertionError):
            # GET은 로그 없음 → assertLogs는 AssertionError 발생
            with self.assertLogs('audit', level='INFO'):
                mw(req)

    def test_unauthenticated_request_not_logged(self):
        from core.middleware.audit import AuditLogMiddleware
        mock_response = MagicMock()
        mock_response.status_code = 200
        get_response = MagicMock(return_value=mock_response)
        mw = AuditLogMiddleware(get_response)

        factory = RequestFactory()
        req = factory.post('/api/incidents/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()

        with self.assertRaises(AssertionError):
            with self.assertLogs('audit', level='INFO'):
                mw(req)

    def test_log_contains_user_method_path_status(self):
        mw = self._make_middleware(response_status=201)
        req = self._make_request('POST', '/api/incidents/')
        with self.assertLogs('audit', level='INFO') as cm:
            mw(req)
        log_line = cm.output[0]
        self.assertIn('testuser', log_line)
        self.assertIn('POST', log_line)
        self.assertIn('/api/incidents/', log_line)
        self.assertIn('201', log_line)


# ─────────────────────────────────────────────────────────────
# 6. SessionTrackingMiddleware
# ─────────────────────────────────────────────────────────────
class SessionTrackingMiddlewareTest(TestCase):
    """SessionTrackingMiddleware — DB 오류 무시, 경로 필터"""

    def _make_middleware(self):
        from core.middleware.session_tracking import SessionTrackingMiddleware
        mock_response = MagicMock()
        mock_response.status_code = 200
        get_response = MagicMock(return_value=mock_response)
        return SessionTrackingMiddleware(get_response)

    def _make_auth_request(self, path='/npms/incidents/'):
        factory = RequestFactory()
        req = factory.get(path)
        user = MagicMock()
        user.is_authenticated = True
        req.user = user
        req.session = MagicMock()
        req.session.session_key = 'test-session-key'
        return req

    def test_db_error_does_not_propagate(self):
        """DB 오류가 발생해도 응답이 정상 반환되어야 한다"""
        mw = self._make_middleware()
        req = self._make_auth_request('/npms/incidents/')

        with patch(
            'apps.accounts.models.UserSession.objects.filter',
            side_effect=Exception('DB connection lost'),
        ):
            # 예외 없이 응답 반환
            resp = mw(req)
        self.assertIsNotNone(resp)

    def test_non_npms_path_skips_tracking(self):
        """비-/npms/ 경로는 세션 추적하지 않음
        FORCE_SCRIPT_NAME='/npms' 로 인해 factory 경로에 /npms/ 가 자동 추가되므로
        request.path 를 직접 설정해 미들웨어 조건을 테스트한다.
        """
        from core.middleware.session_tracking import SessionTrackingMiddleware
        mock_response = MagicMock()
        mock_response.status_code = 200
        get_response = MagicMock(return_value=mock_response)
        mw = SessionTrackingMiddleware(get_response)

        req = self._make_auth_request('/admin/')
        req.path = '/admin/'   # FORCE_SCRIPT_NAME 우회: 순수 비-/npms/ 경로

        with patch('apps.accounts.models.UserSession') as mock_model:
            mw(req)
            mock_model.objects.filter.assert_not_called()
            mock_model.objects.update_or_create.assert_not_called()

    def test_unauthenticated_request_skips_tracking(self):
        """비인증 요청은 세션 추적하지 않음"""
        mw = self._make_middleware()
        factory = RequestFactory()
        req = factory.get('/npms/incidents/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        req.session = MagicMock()
        req.session.session_key = 'anon-session'

        with patch('apps.accounts.models.UserSession') as mock_model:
            mw(req)
            mock_model.objects.filter.assert_not_called()

    def test_response_returned_even_on_db_error(self):
        """DB 오류 시에도 미들웨어는 응답 객체를 반환해야 한다"""
        from core.middleware.session_tracking import SessionTrackingMiddleware
        expected_response = HttpResponse('ok', status=200)
        mw = SessionTrackingMiddleware(lambda r: expected_response)
        req = self._make_auth_request('/npms/incidents/')

        with patch(
            'apps.accounts.models.UserSession.objects.filter',
            side_effect=RuntimeError('DB down'),
        ):
            resp = mw(req)
        self.assertEqual(resp.status_code, 200)
