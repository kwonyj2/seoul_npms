"""
accounts 앱 모델
사용자, 역할, 권한, 세션 관리
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError('사용자명은 필수입니다.')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'superadmin')
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """사용자 모델"""
    ROLE_CHOICES = [
        ('superadmin', '슈퍼관리자'),
        ('admin',      '관리자'),
        ('customer',   '고객(학교담당자)'),
        ('worker',     '현장기사'),
        ('resident',   '상주인력'),
    ]

    username       = models.CharField('사용자명', max_length=50, unique=True)
    email          = models.EmailField('이메일', unique=True)
    name           = models.CharField('성명', max_length=50)
    phone          = models.CharField('연락처', max_length=20, blank=True)
    role           = models.CharField('역할', max_length=20, choices=ROLE_CHOICES, default='worker')
    support_center = models.ForeignKey(
        'schools.SupportCenter', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='소속 지원청'
    )
    home_address   = models.TextField('자택주소', blank=True)
    home_lat       = models.DecimalField('자택위도', max_digits=10, decimal_places=7, null=True, blank=True)
    home_lng       = models.DecimalField('자택경도', max_digits=10, decimal_places=7, null=True, blank=True)
    profile_image  = models.ImageField('프로필사진', upload_to='profiles/', null=True, blank=True)
    service_expiry = models.DateField(
        '서비스 만료일', null=True, blank=True,
        help_text='superadmin이 지정한 기일까지만 접속 허용'
    )
    # 2FA
    is_2fa_enabled = models.BooleanField('2FA 활성화', default=False)
    totp_secret    = models.CharField('TOTP 비밀키', max_length=64, blank=True)

    is_active      = models.BooleanField('활성', default=True)
    is_staff       = models.BooleanField('스태프', default=False)
    created_at     = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at     = models.DateTimeField('수정일시', auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'username'
    REQUIRED_FIELDS = ['email', 'name']

    class Meta:
        db_table = 'users'
        verbose_name = '사용자'
        verbose_name_plural = '사용자 목록'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_role_display()})'

    def is_service_active(self):
        """서비스 만료일 확인"""
        if self.service_expiry is None:
            return True
        return timezone.localdate() <= self.service_expiry


class UserSession(models.Model):
    """접속 세션 추적 - 현재 어느 화면에 접속 중인지"""
    user         = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='사용자', related_name='sessions')
    session_key  = models.CharField('세션키', max_length=40, unique=True)
    ip_address   = models.GenericIPAddressField('IP주소', null=True, blank=True)
    user_agent   = models.TextField('브라우저정보', blank=True)
    current_page = models.CharField('현재페이지', max_length=200, blank=True)
    login_at     = models.DateTimeField('로그인시각', auto_now_add=True)
    last_active  = models.DateTimeField('마지막활동', auto_now=True)
    is_active    = models.BooleanField('활성', default=True)

    class Meta:
        db_table = 'user_sessions'
        verbose_name = '사용자 세션'
        verbose_name_plural = '사용자 세션 목록'

    def __str__(self):
        return f'{self.user.name} - {self.login_at}'


class UserActivityLog(models.Model):
    """사용자 활동 로그"""
    ACTION_CHOICES = [
        ('login',    '로그인'),
        ('logout',   '로그아웃'),
        ('create',   '생성'),
        ('update',   '수정'),
        ('delete',   '삭제'),
        ('view',     '조회'),
        ('download', '다운로드'),
        ('upload',   '업로드'),
    ]
    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='사용자')
    action     = models.CharField('행위', max_length=20, choices=ACTION_CHOICES)
    target     = models.CharField('대상', max_length=200, blank=True)
    detail     = models.TextField('상세내용', blank=True)
    ip_address = models.GenericIPAddressField('IP주소', null=True, blank=True)
    created_at = models.DateTimeField('발생일시', auto_now_add=True)

    class Meta:
        db_table = 'user_activity_logs'
        verbose_name = '활동 로그'
        verbose_name_plural = '활동 로그 목록'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.action} - {self.created_at}'


class LoginHistory(models.Model):
    """로그인 이력"""
    user        = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='사용자',
                                    related_name='login_history', null=True, blank=True)
    attempted_username = models.CharField('시도 아이디', max_length=100, blank=True)
    ip_address  = models.GenericIPAddressField('IP주소', null=True, blank=True)
    user_agent  = models.TextField('브라우저정보', blank=True)
    success     = models.BooleanField('성공여부', default=True)
    fail_reason = models.CharField('실패사유', max_length=200, blank=True)
    created_at  = models.DateTimeField('시도일시', auto_now_add=True)

    class Meta:
        db_table = 'login_history'
        verbose_name = '로그인 이력'
        verbose_name_plural = '로그인 이력 목록'
        ordering = ['-created_at']


class PasswordResetToken(models.Model):
    """비밀번호 재설정 토큰"""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='사용자')
    token      = models.CharField('토큰', max_length=100, unique=True)
    is_used    = models.BooleanField('사용여부', default=False)
    expires_at = models.DateTimeField('만료일시')
    created_at = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table = 'password_reset_tokens'
        verbose_name = '비밀번호 재설정 토큰'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
