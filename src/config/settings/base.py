"""
NPMS 공통 설정 (base)
서울시교육청 학교 네트워크 장애관리 시스템
"""
import os
from pathlib import Path
import environ
from celery.schedules import crontab

# ─────────────────────────────────────────
# 기본 경로
# ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR.parent.parent, '.env'))

# ─────────────────────────────────────────
# 보안
# ─────────────────────────────────────────
SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-key')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# ─────────────────────────────────────────
# 앱 정의
# ─────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'channels',
    'django_celery_beat',
    'django_celery_results',
    'drf_spectacular',
]

LOCAL_APPS = [
    'core',
    'apps.accounts',
    'apps.schools',
    'apps.incidents',
    'apps.workforce',
    'apps.gps',
    'apps.materials',
    'apps.assets',
    'apps.network',
    'apps.reports',
    'apps.nas',
    'apps.photos',
    'apps.ai_engine',
    'apps.statistics',
    'apps.dashboard',
    'apps.bulletin',
    'apps.progress',
    'apps.audit',
    'apps.wbs',
    'apps.sysconfig',
    'apps.education',
    'apps.mobile',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─────────────────────────────────────────
# 미들웨어
# ─────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.ip_block.IPBlockMiddleware',
    'core.middleware.audit.AuditLogMiddleware',
    'core.middleware.session_tracking.SessionTrackingMiddleware',
    'core.middleware.security_headers.SecurityHeadersMiddleware',
    'core.middleware.system_expiry.SystemExpiryMiddleware',
]

ROOT_URLCONF = 'config.urls'

# ─────────────────────────────────────────
# 템플릿
# ─────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_settings',
                'core.context_processors.user_access',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ─────────────────────────────────────────
# 데이터베이스 (PostgreSQL)
# ─────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='npms_db'),
        'USER': env('DB_USER', default='django'),
        'PASSWORD': env('DB_PASSWORD', default='django_password'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# ─────────────────────────────────────────
# 캐시 (Redis)
# ─────────────────────────────────────────
REDIS_PASSWORD = env('REDIS_PASSWORD', default='npmsRedis2026Secure')
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default=f'redis://:{REDIS_PASSWORD}@localhost:6379/0'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 8 * 60 * 60   # 8시간 (기본 2주 → 단축)
SESSION_SAVE_EVERY_REQUEST = True   # 활동 시마다 만료 연장

# ─────────────────────────────────────────
# Celery
# ─────────────────────────────────────────
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default=f'redis://:{REDIS_PASSWORD}@localhost:6379/1')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_RESULT_EXTENDED = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Flower 모니터링 URL (nginx 프록시 경유)
FLOWER_URL = env('FLOWER_URL', default='/npms/flower/')
CELERY_BEAT_SCHEDULE = {
    # NAS 파일시스템 → DB 자동 동기화 (1분마다)
    # schools·materials·reports 등 모든 앱에서 생성된 파일을 NAS DB에 자동 등록 + 삭제된 파일 정리
    'sync-nas-filesystem': {
        'task': 'apps.nas.tasks.sync_nas_filesystem',
        'schedule': 60,  # 1분
    },
    # 미OCR 파일 일괄 처리 (1시간마다)
    'bulk-ocr-extract': {
        'task': 'apps.nas.tasks.bulk_ocr_extract',
        'schedule': 3600,
    },
    # 건물정보_비지오 폴더 스캔 → 새 VSDX 자동 파싱 (5분마다)
    'scan-vsdx-folder': {
        'task': 'apps.schools.tasks.scan_vsdx_folder',
        'schedule': 300,
    },
    # 운영 PMS 담당자 정보 동기화 (매일 새벽 2시)
    'sync-pms-contacts': {
        'task': 'apps.schools.tasks.sync_pms_contacts',
        'schedule': crontab(hour=2, minute=0),
    },
    # PostgreSQL 자동 백업 (매일 새벽 3시)
    'db-backup': {
        'task': 'core.tasks.backup_database',
        'schedule': crontab(hour=3, minute=0),
    },
    # NAS 휴지통 30일 이상 파일 자동 영구 삭제 (매일 새벽 4시)
    'purge-old-trash': {
        'task': 'apps.nas.tasks.purge_old_trash',
        'schedule': crontab(hour=4, minute=0),
    },
    # WBS 진척 스냅샷 (매주 월요일 새벽 1시)
    'wbs-progress-snapshot': {
        'task': 'apps.wbs.tasks.snapshot_wbs_progress',
        'schedule': crontab(hour=1, minute=0, day_of_week=1),
    },
    # SLA 월간 지표 자동 산출 (매일 새벽 5시 — 전월+당월 재계산)
    'auto-calculate-sla': {
        'task': 'apps.incidents.tasks.auto_calculate_sla',
        'schedule': crontab(hour=5, minute=0),
    },
    # ── 보안관제 ────────────────────────
    # SSH 로그 수집 (5분마다)
    'collect-system-logs': {
        'task': 'sysconfig.collect_system_logs',
        'schedule': 300,
    },
    # 파일 무결성 점검 (1시간마다)
    'check-file-integrity': {
        'task': 'sysconfig.check_file_integrity',
        'schedule': 3600,
    },
    # 만료 IP 차단 해제 (5분마다)
    'cleanup-expired-blocks': {
        'task': 'sysconfig.cleanup_expired_blocks',
        'schedule': 300,
    },
    # 보안 이벤트 자동 생성 (5분마다)
    'generate-security-events': {
        'task': 'sysconfig.generate_security_events',
        'schedule': 300,
    },
    # SSH 공격 IP 자동 차단 (5분마다)
    'auto-block-ssh-attackers': {
        'task': 'sysconfig.auto_block_ssh_attackers',
        'schedule': 300,
    },
    # ── 공휴일 자동 생성 ────────────────────────
    # 매년 1/1 새벽 0시 30분: 올해+내년 음력 공휴일 + 대체공휴일 자동 등록
    'generate-yearly-holidays': {
        'task': 'apps.progress.tasks.generate_yearly_holidays',
        'schedule': crontab(month_of_year=1, day_of_month=1, hour=0, minute=30),
    },
}

# ─────────────────────────────────────────
# DB 자동 백업
# ─────────────────────────────────────────
DB_BACKUP_DIR         = env('DB_BACKUP_DIR',         default='/app/nas/backups')
DB_BACKUP_KEEP_DAYS   = env.int('DB_BACKUP_KEEP_DAYS', default=30)
DB_BACKUP_ENCRYPT_KEY = env('DB_BACKUP_ENCRYPT_KEY', default='')

# ─────────────────────────────────────────
# 운영 PMS 연동
# ─────────────────────────────────────────
PMS_API_URL  = env('PMS_API_URL',  default='http://112.187.158.4/pms')
PMS_API_KEY  = env('PMS_API_KEY',  default='npms-pms-sync-2026')

# ─────────────────────────────────────────
# Django Channels (WebSocket)
# ─────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [f'redis://:{REDIS_PASSWORD}@{env("REDIS_HOST", default="localhost")}:{env("REDIS_PORT", default="6379")}/0'],
        },
    },
}

# ─────────────────────────────────────────
# 인증
# ─────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'core.validators.PasswordComplexityValidator'},
]

LOGIN_URL = '/npms/accounts/login/'
LOGIN_REDIRECT_URL = '/npms/'
LOGOUT_REDIRECT_URL = '/npms/accounts/login/'

# ─────────────────────────────────────────
# REST Framework
# ─────────────────────────────────────────
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    # ── Rate Limiting ──────────────────────────────────────
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/min',   # 비인증: 분당 30회
        'user': '200/min',  # 인증:   분당 200회
    },
}

# ─────────────────────────────────────────
# 국제화 (한국어/한국시간)
# ─────────────────────────────────────────
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────
# 정적 파일 / 미디어
# ─────────────────────────────────────────
STATIC_URL = '/npms/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'core.storage.MinifyManifestStaticFilesStorage'

MEDIA_URL = '/npms/media/'
# MEDIA_ROOT는 NAS_ROOT 아래로 통합 — NAS_ROOT 정의 후 아래에서 최종 설정
# (NAS 경로 섹션 이후에 override됨)

# ─────────────────────────────────────────
# Nginx Proxy (PMS 충돌 방지)
# ─────────────────────────────────────────
FORCE_SCRIPT_NAME = '/npms'
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ─────────────────────────────────────────
# 파일 업로드
# ─────────────────────────────────────────
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024  # 100MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024

# ─────────────────────────────────────────
# 기본 PK
# ─────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────
# 느린 쿼리 로그 임계값 (ms)
# ─────────────────────────────────────────
SLOW_QUERY_LOG_MS = 100

# 파일 업로드 최대 크기 (20MB)
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# Debug Toolbar (개발 환경에서 사용)
INTERNAL_IPS = ['127.0.0.1']

# ─────────────────────────────────────────
# 외부 API 키
# ─────────────────────────────────────────
VWORLD_API_KEY     = env('VWORLD_API_KEY', default='')
AI_SERVER_URL      = env('AI_SERVER_URL', default='http://npms_ai:8001')
ANTHROPIC_API_KEY  = env('ANTHROPIC_API_KEY', default='')
SITE_URL         = env('SITE_URL', default='http://112.187.158.4/npms')

# SMS (SOLAPI / 알리고 호환)
SMS_PROVIDER       = env('SMS_PROVIDER', default='solapi')   # solapi | aligo | console
SMS_API_KEY        = env('SMS_API_KEY', default='')
SMS_API_SECRET     = env('SMS_API_SECRET', default='')
SMS_SENDER_NUMBER  = env('SMS_SENDER_NUMBER', default='')
SMS_ENABLED        = env.bool('SMS_ENABLED', default=False)

# ─────────────────────────────────────────
# NAS 경로
# ─────────────────────────────────────────
NAS_ROOT = env('NAS_ROOT', default='/mnt/lvm-cache/nas')
NAS_MEDIA_ROOT = f"{NAS_ROOT}/media/npms"
NAS_OUTPUT_ROOT = f"{NAS_ROOT}/media/npms/산출물"
NAS_PHOTO_ROOT  = f"{NAS_ROOT}/media/npms/작업이미지"

# 모든 파일 저장소를 NAS 단일 경로로 통합
MEDIA_ROOT = NAS_MEDIA_ROOT

# ─────────────────────────────────────────
# SLA 기본값
# ─────────────────────────────────────────
SLA_ARRIVAL_HOURS = 2    # 도착 기준: 2시간
SLA_RESOLVE_HOURS = 8    # 처리 기준: 8시간

# ─────────────────────────────────────────
# JWT (simplejwt)
# ─────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─────────────────────────────────────────
# 동시 로그인 제한
# ─────────────────────────────────────────
MAX_CONCURRENT_SESSIONS = 3

# ─────────────────────────────────────────
# 레이트 리미팅
# ─────────────────────────────────────────
RATELIMIT_LOGIN_RATE  = '10/min'    # IP당 분당 10회
RATELIMIT_UPLOAD_RATE = '100/hour'  # 사용자당 시간당 100회
RATELIMIT_PDF_RATE    = '5/min'     # 사용자당 분당 5회


# ─────────────────────────────────────────
# drf-spectacular (OpenAPI 문서)
# ─────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'NPMS API',
    'DESCRIPTION': '서울시교육청 학교 네트워크 장애관리 시스템 REST API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY': [{'jwtAuth': []}],
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
        'displayRequestDuration': True,
    },
}
