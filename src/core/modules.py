"""
MODULE_REGISTRY — NPMS 모듈 레지스트리
각 모듈의 레이블, 아이콘, URL, 최소 접근 역할을 정의합니다.
새 모듈 추가 시 이곳에 등록하면 권한 관리 UI에 자동 반영됩니다.
"""

# 역할 우선순위 (index가 낮을수록 높은 권한)
ROLE_HIERARCHY = ['superadmin', 'admin', 'worker', 'resident', 'customer']

ROLE_LABELS = {
    'superadmin': '슈퍼관리자',
    'admin':      '관리자',
    'worker':     '현장기사',
    'resident':   '상주자',
    'customer':   '고객',
}

MODULE_REGISTRY = {
    # ── 대시보드 ───────────────────────────────
    'dashboard': {
        'label':    '대시보드',
        'icon':     'bi-speedometer2',
        'url':      '/npms/',
        'min_role': 'customer',
        'color':    'primary',
    },
    # ── 장애 ──────────────────────────────────
    'incidents': {
        'label':    '장애 목록',
        'icon':     'bi-exclamation-triangle',
        'url':      '/npms/incidents/list/',
        'min_role': 'customer',
        'color':    'danger',
    },
    # ── 인력 ──────────────────────────────────
    'worker_list': {
        'label':    '인력 관리',
        'icon':     'bi-person-badge',
        'url':      '/npms/workforce/workers/',
        'min_role': 'admin',
        'color':    'info',
    },
    'schedule': {
        'label':    '업무 일정',
        'icon':     'bi-calendar3',
        'url':      '/npms/workforce/',
        'min_role': 'admin',
        'color':    'info',
    },
    'attendance': {
        'label':    '근태기록부',
        'icon':     'bi-person-check',
        'url':      '/npms/workforce/attendance/',
        'min_role': 'admin',
        'color':    'info',
    },
    # ── 현장 ──────────────────────────────────
    'gps': {
        'label':    '위치 추적',
        'icon':     'bi-geo-alt',
        'url':      '/npms/gps/',
        'min_role': 'worker',
        'color':    'primary',
    },
    'materials': {
        'label':    '자재 관리',
        'icon':     'bi-boxes',
        'url':      '/npms/materials/',
        'min_role': 'worker',
        'color':    'secondary',
    },
    'assets': {
        'label':    '장비 관리',
        'icon':     'bi-hdd-network',
        'url':      '/npms/assets/',
        'min_role': 'worker',
        'color':    'success',
    },
    # ── 네트워크 ──────────────────────────────
    'network': {
        'label':    'NMS 모니터링',
        'icon':     'bi-activity',
        'url':      '/npms/network/',
        'min_role': 'worker',
        'color':    'info',
    },
    'ap_analyzer': {
        'label':    'AP 신호 측정',
        'icon':     'bi-wifi',
        'url':      '/npms/ap-analyzer/',
        'min_role': 'worker',
        'color':    'info',
    },
    # ── 학교 ──────────────────────────────────
    'schools': {
        'label':    '학교 정보',
        'icon':     'bi-building',
        'url':      '/npms/schools/list/',
        'min_role': 'worker',
        'color':    'primary',
    },
    'school_map': {
        'label':    '학교 위치 지도',
        'icon':     'bi-geo-alt-fill',
        'url':      '/npms/schools/map/',
        'min_role': 'worker',
        'color':    'success',
    },
    # ── 관리 ──────────────────────────────────
    'progress': {
        'label':    '진척관리',
        'icon':     'bi-clipboard2-check',
        'url':      '/npms/progress/',
        'min_role': 'worker',
        'color':    'success',
    },
    'audit': {
        'label':    '감리관리',
        'icon':     'bi-shield-check',
        'url':      '/npms/audit/',
        'min_role': 'admin',
        'color':    'warning',
    },
    'wbs': {
        'label':    'WBS 관리',
        'icon':     'bi-diagram-3',
        'url':      '/npms/wbs/',
        'min_role': 'admin',
        'color':    'secondary',
    },
    'sla': {
        'label':    'SLA 관리',
        'icon':     'bi-shield-check',
        'url':      '/npms/incidents/sla/',
        'min_role': 'admin',
        'color':    'warning',
    },
    # ── 보고 ──────────────────────────────────
    'performance': {
        'label':    '성과보고서',
        'icon':     'bi-file-earmark-bar-graph',
        'url':      '/npms/performance/',
        'min_role': 'admin',
        'color':    'warning',
    },
    'reports': {
        'label':    '업무보고서',
        'icon':     'bi-file-earmark-text',
        'url':      '/npms/reports/',
        'min_role': 'worker',
        'color':    'primary',
    },
    'statistics': {
        'label':    '통계',
        'icon':     'bi-bar-chart-line',
        'url':      '/npms/statistics/',
        'min_role': 'admin',
        'color':    'primary',
    },
    # ── 파일/공지 ─────────────────────────────
    'deliverables': {
        'label':    '산출물 관리',
        'icon':     'bi-archive',
        'url':      '/npms/deliverables/',
        'min_role': 'worker',
        'color':    'secondary',
    },
    'bulletin': {
        'label':    '업무공지/자료실',
        'icon':     'bi-megaphone',
        'url':      '/npms/bulletin/',
        'min_role': 'customer',
        'color':    'info',
    },
    'nas': {
        'label':    'NAS 파일',
        'icon':     'bi-folder2-open',
        'url':      '/npms/nas/',
        'min_role': 'worker',
        'color':    'warning',
    },
    'photos': {
        'label':    '사진 관리',
        'icon':     'bi-camera',
        'url':      '/npms/photos/',
        'min_role': 'worker',
        'color':    'secondary',
    },
    # ── 교육 ──────────────────────────────────
    'education': {
        'label':    '교육관리',
        'icon':     'bi-mortarboard',
        'url':      '/npms/education/',
        'min_role': 'worker',
        'color':    'success',
    },
    # ── 시스템 ────────────────────────────────
    'system': {
        'label':    '시스템 설정',
        'icon':     'bi-gear',
        'url':      '/npms/system/',
        'min_role': 'admin',
        'color':    'dark',
    },
    # ── 보안관제 ──────────────────────────────
    'security': {
        'label':    '보안관제',
        'icon':     'bi-shield-lock',
        'url':      '/npms/security/',
        'min_role': 'admin',
        'color':    'danger',
    },
}


def can_access(role: str, module_key: str) -> bool:
    """주어진 역할이 모듈에 접근 가능한지 반환
    1순위: ModuleRolePerm (역할별 독립 설정)
    2순위: MODULE_REGISTRY min_role (계층 기반 기본값)
    """
    mod = MODULE_REGISTRY.get(module_key)
    if not mod:
        return False
    # 1순위: 독립 역할 권한 테이블
    try:
        from apps.sysconfig.models import ModuleRolePerm
        perm = ModuleRolePerm.objects.filter(module_key=module_key, role=role).first()
        if perm is not None:
            return perm.allowed
    except Exception:
        pass
    # 2순위: min_role 계층 기반 (기본값)
    min_r = mod['min_role']
    role_idx = ROLE_HIERARCHY.index(role) if role in ROLE_HIERARCHY else 999
    min_idx  = ROLE_HIERARCHY.index(min_r) if min_r in ROLE_HIERARCHY else 999
    return role_idx <= min_idx


def get_access_matrix() -> dict:
    """역할 × 모듈 접근 가능 여부 매트릭스 반환"""
    return {
        role: {key: can_access(role, key) for key in MODULE_REGISTRY}
        for role in ROLE_HIERARCHY
    }
