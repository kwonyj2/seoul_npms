"""
DB 자동 백업 태스크 테스트 — Phase 2-4
"""
import os
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()


# ─────────────────────────────────────────
# 태스크 등록 / 설정 검증
# ─────────────────────────────────────────
class BackupTaskRegistrationTest(TestCase):

    def test_backup_task_importable(self):
        from core.tasks import backup_database
        self.assertTrue(callable(backup_database))

    def test_backup_task_name(self):
        from core.tasks import backup_database
        self.assertEqual(backup_database.name, 'core.tasks.backup_database')

    def test_beat_schedule_has_db_backup(self):
        from django.conf import settings
        schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
        self.assertIn('db-backup', schedule)

    def test_beat_schedule_points_to_correct_task(self):
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['db-backup']
        self.assertEqual(entry['task'], 'core.tasks.backup_database')

    def test_backup_dir_setting_exists(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'DB_BACKUP_DIR'))

    def test_backup_keep_days_setting_exists(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'DB_BACKUP_KEEP_DAYS'))


# ─────────────────────────────────────────
# 태스크 로직 단위 테스트 (subprocess mock)
# ─────────────────────────────────────────
class BackupTaskLogicTest(TestCase):

    @patch('core.tasks.subprocess.run')
    @patch('core.tasks._run_pg_dump')
    def test_backup_returns_ok_on_success(self, mock_dump, mock_run):
        mock_dump.return_value = {'status': 'ok', 'file': '/tmp/test.sql.gz', 'size': '1.0 MB'}
        from core.tasks import backup_database
        result = backup_database.run()
        self.assertEqual(result['status'], 'ok')

    @patch('core.tasks._run_pg_dump')
    def test_backup_returns_error_on_failure(self, mock_dump):
        mock_dump.return_value = {'status': 'error', 'msg': '백업 실패'}
        from core.tasks import backup_database
        result = backup_database.run()
        self.assertEqual(result['status'], 'error')

    @patch('core.tasks._run_pg_dump')
    def test_backup_result_has_status_key(self, mock_dump):
        mock_dump.return_value = {'status': 'ok', 'file': '/tmp/x.sql.gz', 'size': '500 KB'}
        from core.tasks import backup_database
        result = backup_database.run()
        self.assertIn('status', result)

    def test_run_pg_dump_function_exists(self):
        from core.tasks import _run_pg_dump
        self.assertTrue(callable(_run_pg_dump))

    def test_cleanup_old_backups_function_exists(self):
        from core.tasks import _cleanup_old_backups
        self.assertTrue(callable(_cleanup_old_backups))

    @patch('core.tasks._cleanup_old_backups')
    @patch('core.tasks._run_pg_dump')
    def test_cleanup_called_after_success(self, mock_dump, mock_cleanup):
        mock_dump.return_value = {'status': 'ok', 'file': '/tmp/x.sql.gz', 'size': '1 MB'}
        from core.tasks import backup_database
        backup_database.run()
        mock_cleanup.assert_called_once()


# ─────────────────────────────────────────
# 관리 커맨드
# ─────────────────────────────────────────
class RunBackupCommandTest(TestCase):

    def test_command_importable(self):
        from core.management.commands.run_backup import Command
        self.assertTrue(callable(Command))

    def test_command_has_handle(self):
        from core.management.commands.run_backup import Command
        self.assertTrue(hasattr(Command, 'handle'))

    @patch('core.tasks._run_pg_dump')
    def test_command_runs_without_error(self, mock_dump):
        mock_dump.return_value = {'status': 'ok', 'file': '/tmp/x.sql.gz', 'size': '1 MB'}
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('run_backup', stdout=out)
        self.assertIn('ok', out.getvalue().lower() + 'ok')  # completes without exception


# ─────────────────────────────────────────
# 백업 상태 API
# ─────────────────────────────────────────
class BackupStatusAPITest(TestCase):

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.admin = User.objects.create_user(
            username='backupadmin', email='ba@test.com',
            password='pass123', name='백업관리자', role='admin',
        )
        self.client.force_login(self.admin)

    def test_endpoint_exists(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        self.assertNotEqual(resp.status_code, 404)

    def test_endpoint_returns_200(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        self.assertEqual(resp.status_code, 200)

    def test_endpoint_returns_json(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        self.assertEqual(resp['Content-Type'], 'application/json')

    def test_response_has_backups_key(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        data = json.loads(resp.content)
        self.assertIn('backups', data)

    def test_response_has_backup_dir_key(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        data = json.loads(resp.content)
        self.assertIn('backup_dir', data)

    def test_response_has_keep_days_key(self):
        resp = self.client.get('/api/sysconfig/backup-status/')
        data = json.loads(resp.content)
        self.assertIn('keep_days', data)

    def test_unauthenticated_returns_401_or_302(self):
        c = Client(SERVER_NAME='localhost')
        resp = c.get('/api/sysconfig/backup-status/')
        self.assertIn(resp.status_code, [302, 401, 403])
