"""
Phase 3-5: 권한별 API 접근 테스트
API Permission Access Tests

테스트 대상:
  1. 권한 클래스 단위 테스트 (IsSuperAdmin / IsAdmin / IsWorker / IsCustomer)
  2. can_access() 역할 계층·모듈 레지스트리 검증
  3. ModuleRolePerm DB 오버라이드 동작
  4. module_required 데코레이터 (미인증 → 302, 권한 부족 → 403)
  5. _admin_required 데코레이터 (worker/customer → 403, admin → 200)
  6. DRF ViewSet IsAuthenticated 엔드포인트 (미인증 → 401)
  7. DRF ViewSet IsAdmin 엔드포인트 (worker/customer → 403, admin → 200)
  8. DRF ViewSet IsAdmin — WarehouseInventory / MaterialInbound / AssetModelConfig
  9. 역할별 보고서 템플릿 생성 권한
 10. 통합: 역할 계층별 전체 권한 매트릭스 검증
"""
from unittest.mock import MagicMock, patch
from django.test import TestCase, Client, RequestFactory
from rest_framework.test import APIClient
from rest_framework.request import Request as DRFRequest
from apps.accounts.models import User
from apps.schools.models import SupportCenter, School, SchoolType
from core.permissions.roles import IsSuperAdmin, IsAdmin, IsWorker, IsCustomer
from core.modules import can_access, ROLE_HIERARCHY, MODULE_REGISTRY


# ─────────────────────────────────────────
# 공용 픽스처 믹스인
# ─────────────────────────────────────────

class PermissionFixtureMixin:
    """5개 역할 사용자 + 기본 픽스처."""

    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_user(
            username='perm_superadmin', email='superadmin@test.com',
            password='testpass1234', role='superadmin',
        )
        cls.admin = User.objects.create_user(
            username='perm_admin', email='admin@test.com',
            password='testpass1234', role='admin',
        )
        cls.worker = User.objects.create_user(
            username='perm_worker', email='worker@test.com',
            password='testpass1234', role='worker',
        )
        cls.resident = User.objects.create_user(
            username='perm_resident', email='resident@test.com',
            password='testpass1234', role='resident',
        )
        cls.customer = User.objects.create_user(
            username='perm_customer', email='customer@test.com',
            password='testpass1234', role='customer',
        )

    def _mock_request(self, user):
        """DRF permission has_permission 에 사용할 mock request."""
        req = MagicMock()
        req.user = user
        return req

    def _api(self, user=None):
        """APIClient — force_authenticate 포함."""
        c = APIClient()
        if user:
            c.force_authenticate(user=user)
        return c

    def _web(self, user=None):
        """Django test Client — force_login 포함."""
        c = Client()
        if user:
            c.force_login(user)
        return c


# ─────────────────────────────────────────
# 1. 권한 클래스 단위 테스트
# ─────────────────────────────────────────

class IsSuperAdminPermissionTest(PermissionFixtureMixin, TestCase):

    def _check(self, user):
        return IsSuperAdmin().has_permission(self._mock_request(user), None)

    def test_superadmin_allowed(self):
        self.assertTrue(self._check(self.superadmin))

    def test_admin_denied(self):
        self.assertFalse(self._check(self.admin))

    def test_worker_denied(self):
        self.assertFalse(self._check(self.worker))

    def test_resident_denied(self):
        self.assertFalse(self._check(self.resident))

    def test_customer_denied(self):
        self.assertFalse(self._check(self.customer))

    def test_unauthenticated_denied(self):
        req = MagicMock()
        req.user.is_authenticated = False
        self.assertFalse(IsSuperAdmin().has_permission(req, None))


class IsAdminPermissionTest(PermissionFixtureMixin, TestCase):

    def _check(self, user):
        return IsAdmin().has_permission(self._mock_request(user), None)

    def test_superadmin_allowed(self):
        self.assertTrue(self._check(self.superadmin))

    def test_admin_allowed(self):
        self.assertTrue(self._check(self.admin))

    def test_worker_denied(self):
        self.assertFalse(self._check(self.worker))

    def test_resident_denied(self):
        self.assertFalse(self._check(self.resident))

    def test_customer_denied(self):
        self.assertFalse(self._check(self.customer))

    def test_unauthenticated_denied(self):
        req = MagicMock()
        req.user.is_authenticated = False
        self.assertFalse(IsAdmin().has_permission(req, None))


class IsWorkerPermissionTest(PermissionFixtureMixin, TestCase):

    def _check(self, user):
        return IsWorker().has_permission(self._mock_request(user), None)

    def test_superadmin_allowed(self):
        self.assertTrue(self._check(self.superadmin))

    def test_admin_allowed(self):
        self.assertTrue(self._check(self.admin))

    def test_worker_allowed(self):
        self.assertTrue(self._check(self.worker))

    def test_resident_denied(self):
        self.assertFalse(self._check(self.resident))

    def test_customer_denied(self):
        self.assertFalse(self._check(self.customer))


class IsCustomerPermissionTest(PermissionFixtureMixin, TestCase):
    """IsCustomer = 모든 인증 사용자 허용."""

    def _check(self, user):
        return IsCustomer().has_permission(self._mock_request(user), None)

    def test_all_roles_allowed(self):
        for user in (self.superadmin, self.admin, self.worker, self.resident, self.customer):
            with self.subTest(role=user.role):
                self.assertTrue(self._check(user))

    def test_unauthenticated_denied(self):
        req = MagicMock()
        req.user.is_authenticated = False
        self.assertFalse(IsCustomer().has_permission(req, None))


# ─────────────────────────────────────────
# 2. can_access() 역할 계층 테스트
# ─────────────────────────────────────────

class CanAccessHierarchyTest(TestCase):
    """can_access() — ModuleRolePerm 없이 ROLE_HIERARCHY 기반 기본값 테스트."""

    # min_role = 'customer' 인 모듈 (incidents)
    def test_customer_can_access_incidents(self):
        self.assertTrue(can_access('customer', 'incidents'))

    def test_worker_can_access_incidents(self):
        self.assertTrue(can_access('worker', 'incidents'))

    def test_admin_can_access_incidents(self):
        self.assertTrue(can_access('admin', 'incidents'))

    # min_role = 'worker' 인 모듈 (materials)
    def test_worker_can_access_materials(self):
        self.assertTrue(can_access('worker', 'materials'))

    def test_admin_can_access_materials(self):
        self.assertTrue(can_access('admin', 'materials'))

    def test_customer_cannot_access_materials(self):
        """customer(낮은 권한)는 min_role='worker' 모듈 접근 불가."""
        self.assertFalse(can_access('customer', 'materials'))

    def test_resident_cannot_access_materials(self):
        self.assertFalse(can_access('resident', 'materials'))

    # min_role = 'admin' 인 모듈 (worker_list)
    def test_admin_can_access_worker_list(self):
        self.assertTrue(can_access('admin', 'worker_list'))

    def test_superadmin_can_access_worker_list(self):
        self.assertTrue(can_access('superadmin', 'worker_list'))

    def test_worker_cannot_access_worker_list(self):
        self.assertFalse(can_access('worker', 'worker_list'))

    def test_customer_cannot_access_worker_list(self):
        self.assertFalse(can_access('customer', 'worker_list'))

    # 존재하지 않는 모듈 → False
    def test_unknown_module_returns_false(self):
        self.assertFalse(can_access('superadmin', 'nonexistent_module_xyz'))

    # 역할 계층 순서 검증
    def test_role_hierarchy_order(self):
        """superadmin > admin > worker > resident > customer."""
        h = ROLE_HIERARCHY
        self.assertLess(h.index('superadmin'), h.index('admin'))
        self.assertLess(h.index('admin'),      h.index('worker'))
        self.assertLess(h.index('worker'),     h.index('resident'))
        self.assertLess(h.index('resident'),   h.index('customer'))

    # 모든 모듈에서 superadmin 은 항상 접근 가능
    def test_superadmin_can_access_all_registry_modules(self):
        for module_key in MODULE_REGISTRY:
            with self.subTest(module=module_key):
                self.assertTrue(can_access('superadmin', module_key))


# ─────────────────────────────────────────
# 3. ModuleRolePerm DB 오버라이드 테스트
# ─────────────────────────────────────────

class ModuleRolePermOverrideTest(PermissionFixtureMixin, TestCase):
    """ModuleRolePerm 이 registry 기본값을 오버라이드하는지 검증."""

    def test_deny_override_blocks_normally_allowed_role(self):
        """worker 가 평소 접근 가능한 모듈을 ModuleRolePerm.allowed=False 로 차단."""
        from apps.sysconfig.models import ModuleRolePerm
        # materials min_role='worker' → worker 기본 허용
        self.assertTrue(can_access('worker', 'materials'))
        # DB 오버라이드로 worker 차단
        perm = ModuleRolePerm.objects.create(
            module_key='materials', role='worker', allowed=False
        )
        try:
            self.assertFalse(can_access('worker', 'materials'))
        finally:
            perm.delete()

    def test_allow_override_grants_normally_denied_role(self):
        """customer 가 평소 접근 불가한 모듈을 ModuleRolePerm.allowed=True 로 허용."""
        from apps.sysconfig.models import ModuleRolePerm
        # worker_list min_role='admin' → customer 기본 차단
        self.assertFalse(can_access('customer', 'worker_list'))
        # DB 오버라이드로 customer 허용
        perm = ModuleRolePerm.objects.create(
            module_key='worker_list', role='customer', allowed=True
        )
        try:
            self.assertTrue(can_access('customer', 'worker_list'))
        finally:
            perm.delete()

    def test_override_is_role_specific(self):
        """특정 역할 오버라이드가 다른 역할에 영향을 주지 않는다."""
        from apps.sysconfig.models import ModuleRolePerm
        perm = ModuleRolePerm.objects.create(
            module_key='materials', role='worker', allowed=False
        )
        try:
            # worker 만 차단, admin 은 여전히 허용
            self.assertFalse(can_access('worker', 'materials'))
            self.assertTrue(can_access('admin', 'materials'))
        finally:
            perm.delete()


# ─────────────────────────────────────────
# 4. module_required 데코레이터 테스트
# ─────────────────────────────────────────

class ModuleRequiredDecoratorTest(PermissionFixtureMixin, TestCase):
    """module_required 데코레이터가 적용된 템플릿 뷰 권한 검증.
    실제 URL 은 /incidents/list/, /workforce/workers/ 등."""

    def test_unauthenticated_redirects_to_login(self):
        """미인증 접근 → /npms/accounts/login/ 으로 리다이렉트."""
        c = Client()
        resp = c.get('/incidents/list/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_customer_denied_admin_only_module(self):
        """min_role='admin' 모듈에 customer 접근 → 403."""
        c = self._web(self.customer)
        resp = c.get('/workforce/workers/')
        self.assertEqual(resp.status_code, 403)

    def test_resident_denied_admin_only_module(self):
        """min_role='admin' 모듈에 resident 접근 → 403."""
        c = self._web(self.resident)
        resp = c.get('/workforce/workers/')
        self.assertEqual(resp.status_code, 403)

    def test_worker_denied_admin_only_module(self):
        """min_role='admin' 모듈에 worker 접근 → 403."""
        c = self._web(self.worker)
        resp = c.get('/workforce/workers/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_allowed_admin_only_module(self):
        """admin 은 min_role='admin' 모듈에 접근 가능 (403 아님)."""
        c = self._web(self.admin)
        resp = c.get('/workforce/workers/')
        self.assertNotEqual(resp.status_code, 403)

    def test_superadmin_allowed_admin_only_module(self):
        """superadmin 은 모든 모듈에 접근 가능."""
        c = self._web(self.superadmin)
        resp = c.get('/workforce/workers/')
        self.assertNotEqual(resp.status_code, 403)

    def test_customer_allowed_customer_min_role_module(self):
        """min_role='customer' 인 incidents 페이지는 customer 도 접근 가능."""
        c = self._web(self.customer)
        resp = c.get('/incidents/list/')
        self.assertNotEqual(resp.status_code, 403)

    def test_worker_allowed_worker_min_role_module(self):
        """min_role='worker' 인 materials 페이지는 worker 도 접근 가능."""
        c = self._web(self.worker)
        resp = c.get('/materials/')
        self.assertNotEqual(resp.status_code, 403)

    def test_customer_denied_worker_min_role_module(self):
        """min_role='worker' 인 materials 페이지는 customer 접근 불가."""
        c = self._web(self.customer)
        resp = c.get('/materials/')
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────
# 5. sysconfig _admin_required 데코레이터
# ─────────────────────────────────────────

class SysconfigAdminRequiredTest(PermissionFixtureMixin, TestCase):
    """sysconfig API — @_admin_required: admin/superadmin 만 허용."""

    def test_unauthenticated_returns_401(self):
        c = Client()
        resp = c.get('/api/sysconfig/info/')
        # login_required → 302 redirect, OR _admin_required → 401
        self.assertIn(resp.status_code, [302, 401])

    def test_worker_returns_403(self):
        c = self._web(self.worker)
        resp = c.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 403)

    def test_resident_returns_403(self):
        c = self._web(self.resident)
        resp = c.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 403)

    def test_customer_returns_403(self):
        c = self._web(self.customer)
        resp = c.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_returns_200(self):
        c = self._web(self.admin)
        resp = c.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 200)

    def test_superadmin_returns_200(self):
        c = self._web(self.superadmin)
        resp = c.get('/api/sysconfig/info/')
        self.assertEqual(resp.status_code, 200)

    def test_user_role_update_worker_denied(self):
        """사용자 역할 변경 API: worker 접근 → 403."""
        c = self._web(self.worker)
        resp = c.post(f'/api/sysconfig/users/{self.customer.pk}/role/',
                      content_type='application/json',
                      data='{"role":"admin"}')
        self.assertEqual(resp.status_code, 403)

    def test_user_role_update_admin_allowed(self):
        """사용자 역할 변경 API: admin 접근 → 403 아님."""
        c = self._web(self.admin)
        resp = c.post(f'/api/sysconfig/users/{self.customer.pk}/role/',
                      content_type='application/json',
                      data='{"role":"worker"}')
        self.assertNotEqual(resp.status_code, 403)

    def test_module_matrix_worker_denied(self):
        """모듈 매트릭스 API: worker → 403."""
        c = self._web(self.worker)
        resp = c.get('/api/sysconfig/modules/')
        self.assertEqual(resp.status_code, 403)

    def test_module_matrix_admin_allowed(self):
        """모듈 매트릭스 API: admin → 200."""
        c = self._web(self.admin)
        resp = c.get('/api/sysconfig/modules/')
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────
# 6. DRF IsAuthenticated 엔드포인트 — 미인증 401
# ─────────────────────────────────────────

class UnauthenticatedAPIAccessTest(PermissionFixtureMixin, TestCase):
    """미인증 DRF API 접근 → 401 반환."""

    def test_unauthenticated_incidents_list_401(self):
        c = APIClient()
        resp = c.get('/api/incidents/incidents/')
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_schools_list_401(self):
        c = APIClient()
        resp = c.get('/api/schools/schools/')
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_materials_categories_401(self):
        c = APIClient()
        resp = c.get('/api/materials/categories/')
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_assets_list_401(self):
        c = APIClient()
        resp = c.get('/api/assets/api/assets/')
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_reports_templates_401(self):
        c = APIClient()
        resp = c.get('/api/reports/templates/')
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_report_list_401(self):
        c = APIClient()
        resp = c.get('/api/reports/reports/')
        self.assertEqual(resp.status_code, 401)


# ─────────────────────────────────────────
# 7. DRF IsAdmin 엔드포인트 — 역할별 접근
# ─────────────────────────────────────────

class IsAdminViewSetPermissionTest(PermissionFixtureMixin, TestCase):
    """IsAdmin permission_classes 를 가진 ViewSet 권한 테스트."""

    # ── WarehouseInventoryViewSet (permission_classes = [IsAdmin]) ──

    def test_warehouse_inventory_admin_can_read(self):
        """admin → GET /api/materials/warehouse/ : 200."""
        resp = self._api(self.admin).get('/api/materials/warehouse/')
        self.assertEqual(resp.status_code, 200)

    def test_warehouse_inventory_superadmin_can_read(self):
        resp = self._api(self.superadmin).get('/api/materials/warehouse/')
        self.assertEqual(resp.status_code, 200)

    def test_warehouse_inventory_worker_denied(self):
        """worker → GET /api/materials/warehouse/ : 403."""
        resp = self._api(self.worker).get('/api/materials/warehouse/')
        self.assertEqual(resp.status_code, 403)

    def test_warehouse_inventory_resident_denied(self):
        resp = self._api(self.resident).get('/api/materials/warehouse/')
        self.assertEqual(resp.status_code, 403)

    def test_warehouse_inventory_customer_denied(self):
        resp = self._api(self.customer).get('/api/materials/warehouse/')
        self.assertEqual(resp.status_code, 403)

    # ── MaterialInboundViewSet (permission_classes = [IsAdmin]) ──

    def test_material_inbound_admin_can_read(self):
        resp = self._api(self.admin).get('/api/materials/inbound/')
        self.assertEqual(resp.status_code, 200)

    def test_material_inbound_worker_denied(self):
        resp = self._api(self.worker).get('/api/materials/inbound/')
        self.assertEqual(resp.status_code, 403)

    def test_material_inbound_customer_denied(self):
        resp = self._api(self.customer).get('/api/materials/inbound/')
        self.assertEqual(resp.status_code, 403)

    # ── ReportTemplateViewSet (create/update/delete = IsAdmin) ──

    def test_report_template_list_worker_allowed(self):
        """GET list 는 IsAuthenticated → worker 허용."""
        resp = self._api(self.worker).get('/api/reports/templates/')
        self.assertEqual(resp.status_code, 200)

    def test_report_template_create_admin_allowed(self):
        """POST create 는 IsAdmin → admin 허용."""
        data = {
            'code': 'TEST-PERM-TPL',
            'name': '권한테스트템플릿',
            'report_type': 'other',
            'template_html': '<p>test</p>',
        }
        resp = self._api(self.admin).post('/api/reports/templates/', data, format='json')
        self.assertIn(resp.status_code, [200, 201])

    def test_report_template_create_worker_denied(self):
        """POST create 는 IsAdmin → worker 403."""
        data = {
            'code': 'TEST-PERM-TPL2',
            'name': '권한테스트템플릿2',
            'report_type': 'other',
            'template_html': '<p>test</p>',
        }
        resp = self._api(self.worker).post('/api/reports/templates/', data, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_report_template_create_customer_denied(self):
        """POST create 는 IsAdmin → customer 403."""
        data = {
            'code': 'TEST-PERM-TPL3',
            'name': '권한테스트템플릿3',
            'report_type': 'other',
            'template_html': '<p>test</p>',
        }
        resp = self._api(self.customer).post('/api/reports/templates/', data, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_report_template_create_resident_denied(self):
        data = {
            'code': 'TEST-PERM-TPL4',
            'name': '권한테스트템플릿4',
            'report_type': 'other',
            'template_html': '<p>test</p>',
        }
        resp = self._api(self.resident).post('/api/reports/templates/', data, format='json')
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────
# 8. IsAuthenticated 엔드포인트 — 모든 역할 허용
# ─────────────────────────────────────────

class IsAuthenticatedViewSetAccessTest(PermissionFixtureMixin, TestCase):
    """IsAuthenticated ViewSet 은 모든 인증 역할이 접근 가능하다."""

    def test_incidents_list_all_roles(self):
        for user in (self.superadmin, self.admin, self.worker, self.resident, self.customer):
            with self.subTest(role=user.role):
                resp = self._api(user).get('/api/incidents/incidents/')
                self.assertEqual(resp.status_code, 200,
                                 f"{user.role} should access incidents list")

    def test_schools_list_all_roles(self):
        for user in (self.superadmin, self.admin, self.worker, self.resident, self.customer):
            with self.subTest(role=user.role):
                resp = self._api(user).get('/api/schools/schools/')
                self.assertEqual(resp.status_code, 200,
                                 f"{user.role} should access schools list")

    def test_materials_categories_all_roles(self):
        for user in (self.superadmin, self.admin, self.worker, self.resident, self.customer):
            with self.subTest(role=user.role):
                resp = self._api(user).get('/api/materials/categories/')
                self.assertEqual(resp.status_code, 200,
                                 f"{user.role} should access material categories")

    def test_report_list_all_roles(self):
        for user in (self.superadmin, self.admin, self.worker, self.resident, self.customer):
            with self.subTest(role=user.role):
                resp = self._api(user).get('/api/reports/reports/')
                self.assertEqual(resp.status_code, 200,
                                 f"{user.role} should access report list")


# ─────────────────────────────────────────
# 9. 자재 관리 IsAdmin 개별 액션
# ─────────────────────────────────────────

class MaterialsIsAdminActionTest(PermissionFixtureMixin, TestCase):
    """materials 앱 내 IsAdmin 보호 개별 액션 테스트."""

    def _setup_material(self):
        from apps.materials.models import MaterialCategory, Material
        cat = MaterialCategory.objects.create(name='테스트분류', order=1)
        return Material.objects.create(
            category=cat, name='테스트자재', unit='개', is_active=True
        )

    def test_outbound_list_admin_allowed(self):
        """MaterialOutboundViewSet IsAuthenticated → admin 200."""
        resp = self._api(self.admin).get('/api/materials/outbound/')
        self.assertEqual(resp.status_code, 200)

    def test_outbound_list_worker_allowed(self):
        """MaterialOutboundViewSet IsAuthenticated → worker 200."""
        resp = self._api(self.worker).get('/api/materials/outbound/')
        self.assertEqual(resp.status_code, 200)

    def test_outbound_list_customer_allowed(self):
        """MaterialOutboundViewSet IsAuthenticated → customer 200."""
        resp = self._api(self.customer).get('/api/materials/outbound/')
        self.assertEqual(resp.status_code, 200)

    def test_center_inventory_worker_allowed(self):
        """CenterInventoryViewSet IsAuthenticated → worker 200."""
        resp = self._api(self.worker).get('/api/materials/center/')
        self.assertEqual(resp.status_code, 200)

    def test_material_usage_worker_allowed(self):
        """MaterialUsageViewSet IsAuthenticated → worker 200."""
        resp = self._api(self.worker).get('/api/materials/usage/')
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────
# 10. 통합: 역할 매트릭스 일괄 검증
# ─────────────────────────────────────────

class RolePermissionMatrixTest(PermissionFixtureMixin, TestCase):
    """
    역할별 핵심 API 엔드포인트 권한을 일괄 검증.
    형식: (url, method, role, expected_status_category)
    expected: 'ok'(2xx), 'denied'(403), 'unauth'(401)
    """

    def _call(self, user, method, url):
        c = self._api(user)
        return getattr(c, method)(url)

    def _assert(self, user, method, url, expected):
        resp = self._call(user, method, url)
        if expected == 'ok':
            self.assertIn(resp.status_code, range(200, 300),
                          f"{user.role} {method.upper()} {url} → expected 2xx, got {resp.status_code}")
        elif expected == 'denied':
            self.assertEqual(resp.status_code, 403,
                             f"{user.role} {method.upper()} {url} → expected 403, got {resp.status_code}")
        elif expected == 'unauth':
            self.assertEqual(resp.status_code, 401,
                             f"unauthenticated {method.upper()} {url} → expected 401, got {resp.status_code}")

    MATRIX = [
        # (url, method, role, expected)
        # ── IsAuthenticated ──────────────────────────
        ('/api/incidents/incidents/',    'get', 'superadmin', 'ok'),
        ('/api/incidents/incidents/',    'get', 'admin',      'ok'),
        ('/api/incidents/incidents/',    'get', 'worker',     'ok'),
        ('/api/incidents/incidents/',    'get', 'resident',   'ok'),
        ('/api/incidents/incidents/',    'get', 'customer',   'ok'),
        # ── IsAdmin only ─────────────────────────────
        ('/api/materials/warehouse/',    'get', 'superadmin', 'ok'),
        ('/api/materials/warehouse/',    'get', 'admin',      'ok'),
        ('/api/materials/warehouse/',    'get', 'worker',     'denied'),
        ('/api/materials/warehouse/',    'get', 'resident',   'denied'),
        ('/api/materials/warehouse/',    'get', 'customer',   'denied'),
        ('/api/materials/inbound/',      'get', 'admin',      'ok'),
        ('/api/materials/inbound/',      'get', 'worker',     'denied'),
        ('/api/materials/inbound/',      'get', 'customer',   'denied'),
        # ── report template create (IsAdmin for write) ──
        ('/api/reports/templates/',      'get', 'worker',     'ok'),
        ('/api/reports/templates/',      'get', 'customer',   'ok'),
    ]

    def test_permission_matrix(self):
        user_map = {
            'superadmin': self.superadmin,
            'admin':      self.admin,
            'worker':     self.worker,
            'resident':   self.resident,
            'customer':   self.customer,
        }
        for url, method, role, expected in self.MATRIX:
            user = user_map[role]
            with self.subTest(role=role, method=method.upper(), url=url):
                self._assert(user, method, url, expected)
