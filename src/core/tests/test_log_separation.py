"""
로그 파일 분리 테스트 — Phase 2-3
"""
import logging
from django.test import TestCase
from django.conf import settings


class LogHandlerSeparationTest(TestCase):
    """핸들러 분리 구성 검증"""

    def _handlers(self):
        return settings.LOGGING.get('handlers', {})

    def _loggers(self):
        return settings.LOGGING.get('loggers', {})

    def test_app_file_handler_exists(self):
        self.assertIn('app_file', self._handlers())

    def test_error_file_handler_exists(self):
        self.assertIn('error_file', self._handlers())

    def test_security_file_handler_exists(self):
        self.assertIn('security_file', self._handlers())

    def test_celery_file_handler_exists(self):
        self.assertIn('celery_file', self._handlers())

    def test_access_file_handler_exists(self):
        self.assertIn('access_file', self._handlers())

    def test_apps_error_file_handler_exists(self):
        self.assertIn('apps_error_file', self._handlers())

    def test_celery_file_handler_has_correct_filename(self):
        h = self._handlers().get('celery_file', {})
        filename = h.get('filename', '')
        self.assertIn('celery', filename)

    def test_access_file_handler_has_correct_filename(self):
        h = self._handlers().get('access_file', {})
        filename = h.get('filename', '')
        self.assertIn('access', filename)

    def test_apps_error_file_handler_has_correct_filename(self):
        h = self._handlers().get('apps_error_file', {})
        filename = h.get('filename', '')
        self.assertIn('error', filename)


class LoggerRoutingTest(TestCase):
    """로거 → 핸들러 라우팅 검증"""

    def _loggers(self):
        return settings.LOGGING.get('loggers', {})

    def test_celery_logger_uses_celery_file(self):
        celery_cfg = self._loggers().get('celery', {})
        self.assertIn('celery_file', celery_cfg.get('handlers', []))

    def test_django_request_logger_uses_access_file(self):
        req_cfg = self._loggers().get('django.request', {})
        self.assertIn('access_file', req_cfg.get('handlers', []))

    def test_apps_errors_logger_uses_apps_error_file(self):
        err_cfg = self._loggers().get('apps.errors', {})
        self.assertIn('apps_error_file', err_cfg.get('handlers', []))

    def test_apps_errors_logger_configured(self):
        self.assertIn('apps.errors', self._loggers())

    def test_celery_logger_propagate_false(self):
        celery_cfg = self._loggers().get('celery', {})
        self.assertFalse(celery_cfg.get('propagate', True))


class LogRotationTest(TestCase):
    """로그 로테이션 설정 검증"""

    def _handler(self, name):
        return settings.LOGGING.get('handlers', {}).get(name, {})

    def test_app_file_has_max_bytes(self):
        self.assertIn('maxBytes', self._handler('app_file'))

    def test_error_file_has_max_bytes(self):
        self.assertIn('maxBytes', self._handler('error_file'))

    def test_celery_file_has_max_bytes(self):
        self.assertIn('maxBytes', self._handler('celery_file'))

    def test_access_file_has_max_bytes(self):
        self.assertIn('maxBytes', self._handler('access_file'))

    def test_celery_file_has_backup_count(self):
        self.assertIn('backupCount', self._handler('celery_file'))

    def test_access_file_has_backup_count(self):
        self.assertIn('backupCount', self._handler('access_file'))


class LoggingFunctionalTest(TestCase):
    """로거 실제 동작 검증"""

    def test_celery_logger_captures_info(self):
        with self.assertLogs('celery', level='INFO') as cm:
            logging.getLogger('celery').info('Celery 로거 테스트')
        self.assertTrue(any('Celery 로거 테스트' in line for line in cm.output))

    def test_apps_errors_logger_captures_error(self):
        with self.assertLogs('apps.errors', level='ERROR') as cm:
            logging.getLogger('apps.errors').error('에러 로거 테스트')
        self.assertTrue(any('에러 로거 테스트' in line for line in cm.output))

    def test_apps_mobile_logger_captures_info(self):
        with self.assertLogs('apps.mobile', level='INFO') as cm:
            logging.getLogger('apps.mobile').info('모바일 로거 테스트')
        self.assertTrue(len(cm.output) > 0)


class ShowLogsCommandTest(TestCase):
    """show_logs 관리 커맨드 테스트"""

    def test_command_importable(self):
        from core.management.commands.show_logs import Command
        self.assertTrue(callable(Command))

    def test_command_has_handle_method(self):
        from core.management.commands.show_logs import Command
        self.assertTrue(hasattr(Command, 'handle'))

    def test_command_add_arguments(self):
        from core.management.commands.show_logs import Command
        self.assertTrue(hasattr(Command, 'add_arguments'))
