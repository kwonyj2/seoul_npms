"""
Phase 5-3: API 문서화 테스트

테스트 범위:
  1. GET /api/schema/        — OpenAPI 3.0 스키마 YAML 반환
  2. GET /api/schema/?format=json — JSON 형식 스키마 반환
  3. GET /api/docs/          — Swagger UI HTML 반환
  4. GET /api/redoc/         — ReDoc UI HTML 반환
  5. 스키마에 핵심 API 경로 포함 여부 확인
  6. 스키마에 인증 스킴 정의 여부 (JWT/Session)
  7. SPECTACULAR_SETTINGS 설정 확인
  8. 비인증 접근 허용 (공개 문서)
  9. 스키마 content-type 확인
 10. API 버전 정보 포함 확인
"""
import json

from django.test import TestCase, Client, override_settings
from django.urls import reverse, NoReverseMatch

# API 문서 테스트 중 Rate Limiting 방지
NO_THROTTLE = {
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class SchemaEndpointTest(TestCase):
    """GET /api/schema/ — OpenAPI 스키마 엔드포인트"""

    def setUp(self):
        self.client = Client()

    def test_schema_returns_200(self):
        resp = self.client.get('/api/schema/')
        self.assertEqual(resp.status_code, 200)

    def test_schema_yaml_content_type(self):
        resp = self.client.get('/api/schema/')
        # drf-spectacular은 OpenAPI MIME 타입 사용
        ct = resp['Content-Type']
        self.assertTrue(
            'yaml' in ct or 'openapi' in ct,
            f'예상치 못한 Content-Type: {ct}'
        )

    def test_schema_json_format(self):
        resp = self.client.get('/api/schema/?format=json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('json', resp['Content-Type'])

    def test_schema_json_is_valid(self):
        resp = self.client.get('/api/schema/?format=json')
        try:
            data = json.loads(resp.content)
        except json.JSONDecodeError:
            self.fail('스키마 JSON 파싱 실패')
        self.assertIn('openapi', data)

    def test_schema_is_openapi_3(self):
        resp = self.client.get('/api/schema/?format=json')
        data = json.loads(resp.content)
        self.assertTrue(data['openapi'].startswith('3.'))

    def test_schema_no_auth_required(self):
        """스키마 엔드포인트는 인증 없이 접근 가능해야 한다"""
        c = Client()  # 비인증
        resp = c.get('/api/schema/')
        self.assertEqual(resp.status_code, 200)


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class SwaggerUITest(TestCase):
    """GET /api/docs/ — Swagger UI"""

    def setUp(self):
        self.client = Client()

    def test_swagger_returns_200(self):
        resp = self.client.get('/api/docs/')
        self.assertEqual(resp.status_code, 200)

    def test_swagger_content_type_html(self):
        resp = self.client.get('/api/docs/')
        self.assertIn('text/html', resp['Content-Type'])

    def test_swagger_no_auth_required(self):
        c = Client()
        resp = c.get('/api/docs/')
        self.assertEqual(resp.status_code, 200)


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class ReDocUITest(TestCase):
    """GET /api/redoc/ — ReDoc UI"""

    def setUp(self):
        self.client = Client()

    def test_redoc_returns_200(self):
        resp = self.client.get('/api/redoc/')
        self.assertEqual(resp.status_code, 200)

    def test_redoc_content_type_html(self):
        resp = self.client.get('/api/redoc/')
        self.assertIn('text/html', resp['Content-Type'])

    def test_redoc_no_auth_required(self):
        c = Client()
        resp = c.get('/api/redoc/')
        self.assertEqual(resp.status_code, 200)


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class SchemaContentTest(TestCase):
    """스키마 내용 검증 — 핵심 API 경로 포함 여부"""

    def _get_schema(self):
        resp = self.client.get('/api/schema/?format=json')
        return json.loads(resp.content)

    def setUp(self):
        self.client = Client()
        self.schema = self._get_schema()

    def test_paths_key_exists(self):
        self.assertIn('paths', self.schema)

    def test_incidents_api_documented(self):
        paths = self.schema.get('paths', {})
        incident_paths = [p for p in paths if 'incidents' in p]
        self.assertGreater(len(incident_paths), 0, '장애 API가 스키마에 없습니다')

    def test_accounts_api_documented(self):
        paths = self.schema.get('paths', {})
        account_paths = [p for p in paths if 'accounts' in p]
        self.assertGreater(len(account_paths), 0, '계정 API가 스키마에 없습니다')

    def test_statistics_api_documented(self):
        paths = self.schema.get('paths', {})
        stat_paths = [p for p in paths if 'statistics' in p]
        self.assertGreater(len(stat_paths), 0, '통계 API가 스키마에 없습니다')

    def test_wbs_api_documented(self):
        paths = self.schema.get('paths', {})
        wbs_paths = [p for p in paths if 'wbs' in p]
        self.assertGreater(len(wbs_paths), 0, 'WBS API가 스키마에 없습니다')

    def test_info_block_has_title(self):
        info = self.schema.get('info', {})
        self.assertIn('title', info)
        self.assertTrue(len(info['title']) > 0)

    def test_info_block_has_version(self):
        info = self.schema.get('info', {})
        self.assertIn('version', info)


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class SchemaAuthTest(TestCase):
    """스키마에 인증 스킴 정의 여부"""

    def _get_schema(self):
        resp = self.client.get('/api/schema/?format=json')
        return json.loads(resp.content)

    def setUp(self):
        self.client = Client()
        self.schema = self._get_schema()

    def test_security_schemes_exist(self):
        components = self.schema.get('components', {})
        self.assertIn('securitySchemes', components,
                      'securitySchemes가 스키마에 없습니다')

    def test_jwt_scheme_defined(self):
        components = self.schema.get('components', {})
        schemes = components.get('securitySchemes', {})
        # JWT 관련 스킴 존재 여부 (키 이름은 설정에 따라 다름)
        jwt_keys = [k for k in schemes if 'jwt' in k.lower() or 'bearer' in k.lower()]
        self.assertGreater(len(jwt_keys), 0, 'JWT 인증 스킴이 스키마에 없습니다')


@override_settings(REST_FRAMEWORK=NO_THROTTLE)
class SpectacularSettingsTest(TestCase):
    """SPECTACULAR_SETTINGS 설정 검증"""

    def test_spectacular_installed(self):
        from django.conf import settings
        self.assertIn('drf_spectacular', settings.INSTALLED_APPS)

    def test_spectacular_settings_exist(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'SPECTACULAR_SETTINGS'))

    def test_title_configured(self):
        from django.conf import settings
        settings_dict = getattr(settings, 'SPECTACULAR_SETTINGS', {})
        self.assertIn('TITLE', settings_dict)
        self.assertIn('NPMS', settings_dict['TITLE'])

    def test_version_configured(self):
        from django.conf import settings
        settings_dict = getattr(settings, 'SPECTACULAR_SETTINGS', {})
        self.assertIn('VERSION', settings_dict)
