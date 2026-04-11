"""
에러 로깅 설정 테스트 — Phase 2-1
"""
import logging
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model

User = get_user_model()


class LoggingConfigTest(TestCase):
    """Django LOGGING 설정 구조 검증"""

    def test_logging_setting_exists(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'LOGGING'))

    def test_logging_has_formatters(self):
        from django.conf import settings
        logging_cfg = settings.LOGGING
        self.assertIn('formatters', logging_cfg)

    def test_logging_has_verbose_formatter(self):
        from django.conf import settings
        formatters = settings.LOGGING.get('formatters', {})
        self.assertIn('verbose', formatters)

    def test_verbose_formatter_includes_level(self):
        from django.conf import settings
        fmt = settings.LOGGING['formatters']['verbose'].get('format', '')
        self.assertIn('levelname', fmt)

    def test_verbose_formatter_includes_timestamp(self):
        from django.conf import settings
        fmt = settings.LOGGING['formatters']['verbose'].get('format', '')
        self.assertIn('asctime', fmt)

    def test_apps_logger_configured(self):
        from django.conf import settings
        loggers = settings.LOGGING.get('loggers', {})
        self.assertIn('apps', loggers)

    def test_django_request_logger_configured(self):
        from django.conf import settings
        loggers = settings.LOGGING.get('loggers', {})
        self.assertIn('django.request', loggers)

    def test_apps_logger_callable(self):
        with self.assertLogs('apps', level='INFO') as cm:
            logging.getLogger('apps').info('로깅 테스트 메시지')
        self.assertTrue(any('로깅 테스트 메시지' in line for line in cm.output))

    def test_error_logger_captures_errors(self):
        with self.assertLogs('apps', level='ERROR') as cm:
            logging.getLogger('apps.test').error('테스트 에러 발생')
        self.assertTrue(any('ERROR' in line for line in cm.output))


class Custom404HandlerTest(TestCase):
    """커스텀 404 핸들러 테스트"""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    def test_404_handler_importable(self):
        from core.error_views import custom_404
        self.assertTrue(callable(custom_404))

    def test_404_returns_404_status(self):
        from django.http import Http404
        from django.test import RequestFactory
        from core.error_views import custom_404
        rf = RequestFactory()
        request = rf.get('/nonexistent/')
        response = custom_404(request, Http404())
        self.assertEqual(response.status_code, 404)

    def test_404_api_request_returns_json(self):
        from django.http import Http404
        from django.test import RequestFactory
        from core.error_views import custom_404
        rf = RequestFactory()
        request = rf.get('/api/nonexistent/', HTTP_ACCEPT='application/json')
        response = custom_404(request, Http404())
        self.assertEqual(response.status_code, 404)
        self.assertIn('application/json', response['Content-Type'])

    def test_404_logs_warning(self):
        from django.http import Http404
        from django.test import RequestFactory
        from core.error_views import custom_404
        rf = RequestFactory()
        request = rf.get('/nonexistent-page/')
        with self.assertLogs('apps.errors', level='WARNING') as cm:
            custom_404(request, Http404())
        self.assertTrue(any('404' in line or 'Not Found' in line for line in cm.output))


class Custom500HandlerTest(TestCase):
    """커스텀 500 핸들러 테스트"""

    def test_500_handler_importable(self):
        from core.error_views import custom_500
        self.assertTrue(callable(custom_500))

    def test_500_returns_500_status(self):
        from django.test import RequestFactory
        from core.error_views import custom_500
        rf = RequestFactory()
        request = rf.get('/broken/')
        response = custom_500(request)
        self.assertEqual(response.status_code, 500)

    def test_500_api_request_returns_json(self):
        from django.test import RequestFactory
        from core.error_views import custom_500
        rf = RequestFactory()
        request = rf.get('/api/broken/', HTTP_ACCEPT='application/json')
        response = custom_500(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn('application/json', response['Content-Type'])

    def test_500_logs_critical(self):
        from django.test import RequestFactory
        from core.error_views import custom_500
        rf = RequestFactory()
        request = rf.get('/broken/')
        with self.assertLogs('apps.errors', level='ERROR') as cm:
            custom_500(request)
        self.assertTrue(any('500' in line or 'Internal' in line or 'Error' in line
                            for line in cm.output))


class AppLoggerIntegrationTest(TestCase):
    """앱별 logger 통합 테스트"""

    def test_incidents_logger_usable(self):
        with self.assertLogs('apps.incidents', level='INFO') as cm:
            logging.getLogger('apps.incidents').info('장애 로거 테스트')
        self.assertTrue(len(cm.output) > 0)

    def test_reports_logger_usable(self):
        with self.assertLogs('apps.reports', level='INFO') as cm:
            logging.getLogger('apps.reports').info('보고서 로거 테스트')
        self.assertTrue(len(cm.output) > 0)

    def test_mobile_logger_usable(self):
        with self.assertLogs('apps.mobile', level='INFO') as cm:
            logging.getLogger('apps.mobile').info('모바일 로거 테스트')
        self.assertTrue(len(cm.output) > 0)
