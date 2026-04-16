"""
보안관제 모듈 모델
- SecurityEvent: 통합 보안 이벤트
- BlockedIP: IP 차단 관리
- WhitelistedIP: IP 화이트리스트
- SecurityConfig: 보안 정책 설정
- SystemLogEntry: 시스템(OS) 로그 수집
- FileIntegritySnapshot: 파일 무결성 스냅샷
"""
from django.db import models
from django.utils import timezone


class SecurityEvent(models.Model):
    """통합 보안 이벤트 (모든 보안 관련 이벤트를 한곳에 저장)"""
    SEVERITY_CHOICES = [
        ('critical', '심각'),
        ('high',     '높음'),
        ('medium',   '보통'),
        ('low',      '낮음'),
        ('info',     '정보'),
    ]
    EVENT_TYPE_CHOICES = [
        ('brute_force',      '브루트포스'),
        ('login_fail',       '로그인 실패'),
        ('login_success',    '로그인 성공'),
        ('account_locked',   '계정 잠금'),
        ('unknown_user',     '미등록 계정 시도'),
        ('ip_blocked',       'IP 차단'),
        ('ip_unblocked',     'IP 차단 해제'),
        ('ssh_fail',         'SSH 실패'),
        ('ssh_success',      'SSH 성공'),
        ('port_scan',        '포트 스캔'),
        ('abnormal_access',  '비정상 접근'),
        ('file_integrity',   '파일 무결성 변경'),
        ('resource_anomaly', '리소스 이상'),
        ('container_error',  '컨테이너 오류'),
        ('config_change',    '보안 설정 변경'),
        ('manual',           '수동 등록'),
    ]

    event_type  = models.CharField('이벤트 유형', max_length=30, choices=EVENT_TYPE_CHOICES)
    severity    = models.CharField('위험도', max_length=10, choices=SEVERITY_CHOICES, default='info')
    ip_address  = models.GenericIPAddressField('IP 주소', null=True, blank=True, db_index=True)
    username    = models.CharField('사용자명', max_length=100, blank=True)
    description = models.TextField('설명')
    detail      = models.JSONField('상세 데이터', default=dict, blank=True)
    resolved    = models.BooleanField('해결 여부', default=False)
    created_at  = models.DateTimeField('발생일시', default=timezone.now, db_index=True)

    class Meta:
        db_table = 'security_events'
        verbose_name = '보안 이벤트'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['ip_address', '-created_at']),
        ]

    def __str__(self):
        return f'[{self.severity}] {self.get_event_type_display()} - {self.ip_address or "N/A"}'


class BlockedIP(models.Model):
    """IP 차단 관리"""
    REASON_CHOICES = [
        ('brute_force',  '브루트포스'),
        ('port_scan',    '포트 스캔'),
        ('ssh_attack',   'SSH 공격'),
        ('manual',       '수동 차단'),
        ('abnormal',     '비정상 접근'),
    ]

    ip_address   = models.GenericIPAddressField('IP 주소', unique=True, db_index=True)
    reason       = models.CharField('차단 사유', max_length=30, choices=REASON_CHOICES)
    description  = models.CharField('상세 사유', max_length=300, blank=True)
    is_permanent = models.BooleanField('영구 차단', default=False)
    auto_blocked = models.BooleanField('자동 차단', default=True)
    fail_count   = models.IntegerField('실패 횟수', default=0)
    blocked_at   = models.DateTimeField('차단 시각', default=timezone.now)
    expires_at   = models.DateTimeField('해제 예정', null=True, blank=True)
    blocked_by   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='차단자'
    )

    class Meta:
        db_table = 'blocked_ips'
        verbose_name = '차단 IP'
        ordering = ['-blocked_at']

    def __str__(self):
        return f'{self.ip_address} ({self.get_reason_display()})'

    @property
    def is_active(self):
        if self.is_permanent:
            return True
        if self.expires_at and timezone.now() >= self.expires_at:
            return False
        return True


class WhitelistedIP(models.Model):
    """화이트리스트 (차단 제외 IP)"""
    ip_address  = models.GenericIPAddressField('IP 주소', unique=True)
    description = models.CharField('설명', max_length=200)
    created_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='등록자'
    )
    created_at  = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        db_table = 'whitelisted_ips'
        verbose_name = '화이트리스트 IP'
        ordering = ['ip_address']

    def __str__(self):
        return f'{self.ip_address} - {self.description}'


class BlockLog(models.Model):
    """IP 차단/해제 이력"""
    ACTION_CHOICES = [
        ('block',   '차단'),
        ('unblock', '해제'),
    ]
    ip_address = models.GenericIPAddressField('IP 주소', db_index=True)
    action     = models.CharField('행위', max_length=10, choices=ACTION_CHOICES)
    reason     = models.CharField('사유', max_length=300, blank=True)
    actor      = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='처리자'
    )
    created_at = models.DateTimeField('처리일시', auto_now_add=True)

    class Meta:
        db_table = 'block_logs'
        verbose_name = '차단 이력'
        ordering = ['-created_at']


class SecurityConfig(models.Model):
    """보안 정책 설정 (키-값 저장)"""
    key         = models.CharField('설정키', max_length=100, unique=True)
    value       = models.TextField('설정값')
    description = models.CharField('설명', max_length=300, blank=True)
    updated_at  = models.DateTimeField('수정일시', auto_now=True)
    updated_by  = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='수정자'
    )

    class Meta:
        db_table = 'security_configs'
        verbose_name = '보안 설정'

    # 기본값
    DEFAULTS = {
        'auto_block_enabled':    'true',
        'block_threshold':       '10',      # N회 실패 시 차단
        'block_duration_min':    '60',      # 차단 시간(분)
        'block_window_min':      '30',      # 실패 감시 윈도우(분)
        'permanent_threshold':   '50',      # 영구 차단 임계값
        'ssh_monitor_enabled':   'true',
        'file_integrity_enabled':'true',
        'resource_monitor_enabled':'true',
        'alert_enabled':         'true',
        'report_auto_enabled':   'true',
    }

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return cls.DEFAULTS.get(key, default or '')

    @classmethod
    def get_bool(cls, key):
        return cls.get(key, 'false').lower() in ('true', '1', 'yes')

    @classmethod
    def get_int(cls, key, default=0):
        try:
            return int(cls.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def __str__(self):
        return f'{self.key} = {self.value}'


class SystemLogEntry(models.Model):
    """시스템(OS) 로그 수집 결과"""
    LOG_TYPE_CHOICES = [
        ('ssh_fail',    'SSH 실패'),
        ('ssh_success', 'SSH 성공'),
        ('port_scan',   '포트 스캔'),
        ('auth_other',  '기타 인증'),
    ]

    log_type   = models.CharField('로그유형', max_length=20, choices=LOG_TYPE_CHOICES)
    ip_address = models.GenericIPAddressField('IP 주소', null=True, blank=True)
    username   = models.CharField('사용자명', max_length=100, blank=True)
    raw_line   = models.TextField('원본 로그')
    log_time   = models.DateTimeField('로그 시각', null=True, blank=True)
    created_at = models.DateTimeField('수집일시', auto_now_add=True)

    class Meta:
        db_table = 'system_log_entries'
        verbose_name = '시스템 로그'
        ordering = ['-log_time']
        indexes = [
            models.Index(fields=['log_type', '-log_time']),
        ]


class FileIntegritySnapshot(models.Model):
    """파일 무결성 스냅샷"""
    file_path    = models.CharField('파일경로', max_length=500)
    sha256_hash  = models.CharField('SHA256', max_length=64)
    file_size    = models.BigIntegerField('파일크기', default=0)
    checked_at   = models.DateTimeField('점검일시', auto_now=True)
    is_changed   = models.BooleanField('변경 감지', default=False)
    prev_hash    = models.CharField('이전 해시', max_length=64, blank=True)

    class Meta:
        db_table = 'file_integrity_snapshots'
        verbose_name = '파일 무결성'
        unique_together = [['file_path']]

    def __str__(self):
        status = '⚠ 변경됨' if self.is_changed else '✓ 정상'
        return f'{self.file_path} [{status}]'
