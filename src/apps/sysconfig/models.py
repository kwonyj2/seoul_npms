from django.db import models

# 보안관제 모델 re-export (마이그레이션에서 인식)
from apps.sysconfig.security_models import (  # noqa: F401
    SecurityEvent, BlockedIP, WhitelistedIP, BlockLog,
    SecurityConfig, SystemLogEntry, FileIntegritySnapshot,
)


class SystemExpiry(models.Model):
    """시스템 전체 만료일 설정 — superadmin만 조정 가능"""
    expiry_date = models.DateField('시스템 만료일')
    updated_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='변경자')
    updated_at  = models.DateTimeField('변경일시', auto_now=True)
    note        = models.CharField('변경사유', max_length=200, blank=True)

    class Meta:
        db_table = 'sysconfig_system_expiry'
        verbose_name = '시스템 만료일'

    def __str__(self):
        return f'시스템 만료일: {self.expiry_date}'

    @classmethod
    def get_expiry_date(cls):
        """현재 시스템 만료일 반환 (없으면 None → 무제한)"""
        obj = cls.objects.order_by('-id').first()
        return obj.expiry_date if obj else None

    @classmethod
    def is_expired(cls):
        """시스템 만료 여부"""
        from django.utils import timezone
        expiry = cls.get_expiry_date()
        if expiry is None:
            return False
        return timezone.localdate() > expiry


class ModuleConfig(models.Model):
    """모듈별 최소 역할 오버라이드 (MODULE_REGISTRY 기본값 재정의)"""
    module_key = models.CharField('모듈 키', max_length=50, unique=True)
    min_role   = models.CharField('최소 역할', max_length=20, default='worker')

    class Meta:
        db_table = 'sysconfig_module'
        verbose_name = '모듈 설정'

    def __str__(self):
        return f'{self.module_key} → {self.min_role}'


class NasRoleConfig(models.Model):
    """역할별 NAS 행위 권한 설정"""
    ACTION_CHOICES = [
        ('download',      '파일 다운로드'),
        ('upload',        '파일 업로드'),
        ('delete',        '파일 삭제'),
        ('create_folder', '폴더 생성'),
    ]
    role    = models.CharField('역할', max_length=20)
    action  = models.CharField('행위', max_length=20, choices=ACTION_CHOICES)
    allowed = models.BooleanField('허용', default=False)

    class Meta:
        db_table = 'sysconfig_nas_role'
        verbose_name = 'NAS 역할 권한'
        unique_together = [['role', 'action']]

    def __str__(self):
        return f'{self.role} {self.action} = {self.allowed}'

    @classmethod
    def can_do(cls, role, action):
        """역할이 NAS 행위를 할 수 있는지 확인 (DB 조회, 기본값 fallback)"""
        DEFAULTS = {
            ('superadmin', 'download'): True,  ('superadmin', 'upload'): True,  ('superadmin', 'delete'): True,  ('superadmin', 'create_folder'): True,
            ('admin',      'download'): True,  ('admin',      'upload'): True,  ('admin',      'delete'): True,  ('admin',      'create_folder'): True,
            ('worker',     'download'): True,  ('worker',     'upload'): True,  ('worker',     'delete'): False, ('worker',     'create_folder'): False,
            ('resident',   'download'): True,  ('resident',   'upload'): False, ('resident',   'delete'): False, ('resident',   'create_folder'): False,
            ('customer',   'download'): True,  ('customer',   'upload'): False, ('customer',   'delete'): False, ('customer',   'create_folder'): False,
        }
        try:
            obj = cls.objects.get(role=role, action=action)
            return obj.allowed
        except cls.DoesNotExist:
            return DEFAULTS.get((role, action), False)


class ModuleRolePerm(models.Model):
    """모듈별 역할 독립 접근 권한 (계층 없이 역할별 개별 제어)"""
    module_key = models.CharField('모듈 키', max_length=50)
    role       = models.CharField('역할', max_length=20)
    allowed    = models.BooleanField('허용', default=True)

    class Meta:
        db_table = 'sysconfig_module_role_perm'
        verbose_name = '모듈 역할 권한'
        unique_together = [['module_key', 'role']]

    def __str__(self):
        return f'{self.module_key} / {self.role} = {self.allowed}'
