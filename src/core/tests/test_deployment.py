"""
Phase 8-3: 배포 자동화 테스트

테스트 범위:
  1. GitHub Actions 워크플로우 파일 존재 (src/infra/workflows/deploy.yml)
  2. 배포 스크립트 존재 및 마이그레이션 포함 (src/infra/deploy.sh)
  3. 롤백 스크립트 존재 (src/infra/rollback.sh)
  4. 배포 완료 SMS 알림 태스크 존재
"""
import os
from django.test import TestCase
from django.conf import settings


def _infra(path=''):
    """src/infra/ 경로"""
    return os.path.join(str(settings.BASE_DIR), 'infra', path)


# ─────────────────────────────────────────────────────────────
# 1. GitHub Actions 워크플로우
# ─────────────────────────────────────────────────────────────
class GitHubActionsWorkflowTest(TestCase):

    def test_workflows_directory_exists(self):
        """infra/workflows/ 디렉터리가 있어야 한다"""
        path = _infra('workflows')
        self.assertTrue(os.path.isdir(path),
            f'infra/workflows/ 디렉터리가 없습니다: {path}')

    def test_deploy_workflow_exists(self):
        """infra/workflows/deploy.yml 파일이 있어야 한다"""
        path = _infra('workflows/deploy.yml')
        self.assertTrue(os.path.isfile(path),
            f'infra/workflows/deploy.yml이 없습니다: {path}')

    def test_deploy_workflow_has_test_step(self):
        """배포 워크플로우에 테스트 실행 단계가 있어야 한다"""
        with open(_infra('workflows/deploy.yml')) as f:
            content = f.read()
        self.assertIn('manage.py test', content,
            'deploy.yml에 테스트 실행 단계가 없습니다.')

    def test_deploy_workflow_has_migrate_step(self):
        """배포 워크플로우에 마이그레이션 단계가 있어야 한다"""
        with open(_infra('workflows/deploy.yml')) as f:
            content = f.read()
        self.assertIn('migrate', content,
            'deploy.yml에 migrate 단계가 없습니다.')

    def test_deploy_workflow_triggers_on_push(self):
        """배포 워크플로우가 push 이벤트에 트리거되어야 한다"""
        with open(_infra('workflows/deploy.yml')) as f:
            content = f.read()
        self.assertIn('push', content,
            'deploy.yml에 push 트리거가 없습니다.')


# ─────────────────────────────────────────────────────────────
# 2. 배포 스크립트
# ─────────────────────────────────────────────────────────────
class DeployScriptTest(TestCase):

    def test_deploy_script_exists(self):
        """infra/deploy.sh 배포 스크립트가 있어야 한다"""
        path = _infra('deploy.sh')
        self.assertTrue(os.path.isfile(path),
            f'infra/deploy.sh가 없습니다: {path}')

    def test_deploy_script_has_collectstatic(self):
        with open(_infra('deploy.sh')) as f:
            content = f.read()
        self.assertIn('collectstatic', content)

    def test_deploy_script_has_migrate(self):
        with open(_infra('deploy.sh')) as f:
            content = f.read()
        self.assertIn('migrate', content)


# ─────────────────────────────────────────────────────────────
# 3. 롤백 스크립트
# ─────────────────────────────────────────────────────────────
class RollbackScriptTest(TestCase):

    def test_rollback_script_exists(self):
        """infra/rollback.sh 롤백 스크립트가 있어야 한다"""
        path = _infra('rollback.sh')
        self.assertTrue(os.path.isfile(path),
            f'infra/rollback.sh가 없습니다: {path}')

    def test_rollback_script_has_rollback_command(self):
        with open(_infra('rollback.sh')) as f:
            content = f.read()
        has_rollback = any(cmd in content for cmd in
            ['git checkout', 'docker pull', 'git reset', 'git tag'])
        self.assertTrue(has_rollback, 'rollback.sh에 롤백 명령이 없습니다.')


# ─────────────────────────────────────────────────────────────
# 4. 배포 완료 알림 태스크
# ─────────────────────────────────────────────────────────────
class DeployNotificationTest(TestCase):

    def test_deploy_notify_task_importable(self):
        """core.tasks.notify_deploy_complete 태스크가 있어야 한다"""
        try:
            from core.tasks import notify_deploy_complete
        except ImportError:
            self.fail('core.tasks.notify_deploy_complete가 없습니다.')

    def test_deploy_notify_task_is_celery_task(self):
        from core.tasks import notify_deploy_complete
        self.assertTrue(
            hasattr(notify_deploy_complete, 'delay'),
            'notify_deploy_complete가 Celery 태스크가 아닙니다.'
        )
