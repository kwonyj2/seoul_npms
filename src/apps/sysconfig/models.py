from django.db import models


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
