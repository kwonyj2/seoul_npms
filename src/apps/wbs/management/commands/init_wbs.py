"""
2026 사업 WBS 기본 데이터 일괄 생성
Usage:
  docker exec npms_web python manage.py init_wbs
  docker exec npms_web python manage.py init_wbs --project 1
  docker exec npms_web python manage.py init_wbs --clear
"""
from datetime import date
from django.core.management.base import BaseCommand
from apps.audit.models import AuditProject, ArtifactTemplate
from apps.wbs.models import WBSItem

# ─────────────────────────────────────────────────────────────────────────────
# 2026 WBS 정의
# (code, depth, phase, name, weight, planned_start, planned_end,
#  progress_source, linked_template_code, is_milestone)
# ─────────────────────────────────────────────────────────────────────────────
WBS_DATA = [
    # ══════════════════════════════
    # 1. 계획 단계 (가중치 0.20)
    # ══════════════════════════════
    ('1',     1, 'plan',    '계획 단계',                    0.20,   '2026-05-01', '2026-06-30', 'children', None, True),

    ('1.1',   2, 'plan',    '사업 착수',                    0.05,   '2026-05-01', '2026-05-15', 'children', None, False),
    ('1.1.1', 3, 'plan',    '착수계 제출',                  0.0100, '2026-05-01', '2026-05-07', 'artifact', 'SEN-PMR-004-01', True),
    ('1.1.2', 3, 'plan',    '비상연락망·조직도 작성',       0.0100, '2026-05-01', '2026-05-10', 'artifact', 'SEN-PMR-001-02', False),
    ('1.1.3', 3, 'plan',    '청렴서약서·개인정보동의서',    0.0100, '2026-05-01', '2026-05-10', 'artifact', 'SEN-PMR-003-01', False),
    ('1.1.4', 3, 'plan',    '보안서약서',                   0.0100, '2026-05-01', '2026-05-10', 'artifact', 'SEN-SER-001-01', False),
    ('1.1.5', 3, 'plan',    '자격증명 서류 제출',           0.0100, '2026-05-01', '2026-05-15', 'artifact', 'SEN-OHR-004-01', False),

    ('1.2',   2, 'plan',    '사업 계획 수립',               0.08,   '2026-05-01', '2026-06-10', 'children', None, False),
    ('1.2.1', 3, 'plan',    '사업수행계획서 작성',          0.0200, '2026-05-01', '2026-05-20', 'artifact', 'SEN-PMR-001-01', True),
    ('1.2.2', 3, 'plan',    'WBS 작성',                     0.0200, '2026-05-01', '2026-05-20', 'artifact', 'SEN-PMR-001-03', False),
    ('1.2.3', 3, 'plan',    '품질관리계획서 작성',          0.0200, '2026-05-10', '2026-05-25', 'artifact', 'SEN-QUR-001-01', False),
    ('1.2.4', 3, 'plan',    '보안관리계획서 작성',          0.0200, '2026-05-10', '2026-05-25', 'artifact', 'SEN-SER-001-02', False),
    ('1.2.5', 3, 'plan',    '위험관리대장 작성',            0.0200, '2026-05-15', '2026-06-10', 'artifact', 'SEN-PMR-001-09', False),

    ('1.3',   2, 'plan',    '현황 파악',                    0.05,   '2026-05-10', '2026-06-15', 'children', None, False),
    ('1.3.1', 3, 'plan',    '학교 현황 조사 및 등록',       0.0200, '2026-05-10', '2026-06-15', 'manual',   None, False),
    ('1.3.2', 3, 'plan',    '장비 현황 등록 (NPMS 자산)',   0.0200, '2026-05-10', '2026-06-15', 'manual',   None, False),
    ('1.3.3', 3, 'plan',    '기동·종료 절차서 작성',        0.0100, '2026-05-15', '2026-06-10', 'artifact', 'SEN-PSR-002-01', False),

    ('1.4',   2, 'plan',    'SLA 기준선 설정',              0.02,   '2026-05-15', '2026-06-30', 'children', None, False),
    ('1.4.1', 3, 'plan',    'SLA 지표 정의 및 기준 확정',   0.0100, '2026-05-15', '2026-06-30', 'manual',   None, False),
    ('1.4.2', 3, 'plan',    '초기 SLA 측정값 등록',         0.0100, '2026-06-01', '2026-06-30', 'manual',   None, False),

    # ══════════════════════════════
    # 착수감리 (마일스톤)
    # ══════════════════════════════
    ('1.5',   2, 'plan',    '착수감리 대응',                0.00,   '2026-06-01', '2026-06-30', 'artifact', 'SEN-PMR-004-04', True),

    # ══════════════════════════════
    # 2. 수행 단계 (가중치 0.60)
    # ══════════════════════════════
    ('2',     1, 'execute', '수행 단계',                    0.60,   '2026-07-01', '2026-11-30', 'children', None, True),

    ('2.1',   2, 'execute', '일상 운영·유지관리',           0.18,   '2026-07-01', '2026-11-30', 'children', None, False),
    ('2.1.1', 3, 'execute', '네트워크 운영 관제 (월별)',    0.0200, '2026-07-01', '2026-11-30', 'manual',   None, False),
    ('2.1.2', 3, 'execute', '지능형관제시스템 운영 (월별)', 0.0200, '2026-07-01', '2026-11-30', 'manual',   None, False),
    ('2.1.3', 3, 'execute', '콜센터 운영 (월별)',           0.0200, '2026-07-01', '2026-11-30', 'manual',   None, False),
    ('2.1.4', 3, 'execute', 'SLA 월간 보고',                0.0200, '2026-07-01', '2026-11-30', 'manual',   None, False),
    ('2.1.5', 3, 'execute', '월간 운영현황 보고서',         0.0200, '2026-07-01', '2026-11-30', 'artifact', 'SEN-PMR-002-01', False),

    ('2.2',   2, 'execute', '장애 대응',                    0.12,   '2026-07-01', '2026-11-30', 'children', None, False),
    ('2.2.1', 3, 'execute', '장애 접수 및 처리',            0.0400, '2026-07-01', '2026-11-30', 'incident', None, False),
    ('2.2.2', 3, 'execute', '장애처리보고서 작성',          0.0400, '2026-07-01', '2026-11-30', 'artifact', 'SEN-IMR-007-01', False),
    ('2.2.3', 3, 'execute', '재발방지 조치 (시정·예방)',    0.0200, '2026-07-01', '2026-11-30', 'artifact', 'SEN-QUR-001-08', False),
    ('2.2.4', 3, 'execute', '장애접수 대장 관리',           0.0200, '2026-07-01', '2026-11-30', 'artifact', 'SEN-IMR-007-03', False),

    ('2.3',   2, 'execute', '정기점검 (연 3회)',             0.15,   '2026-07-01', '2026-11-30', 'children', None, False),
    ('2.3.1', 3, 'execute', '1차 정기점검',                  0.0500, '2026-07-01', '2026-08-31', 'inspection', None, True),
    ('2.3.2', 3, 'execute', '2차 정기점검',                  0.0500, '2026-09-01', '2026-10-31', 'inspection', None, True),
    ('2.3.3', 3, 'execute', '3차 정기점검',                  0.0500, '2026-11-01', '2026-11-30', 'inspection', None, True),

    ('2.4',   2, 'execute', '특별점검',                     0.06,   '2026-07-01', '2026-11-30', 'children', None, False),
    ('2.4.1', 3, 'execute', '특별점검 (수시)',               0.0600, '2026-07-01', '2026-11-30', 'inspection', None, False),

    ('2.5',   2, 'execute', '교육·보안',                    0.05,   '2026-07-01', '2026-11-30', 'children', None, False),
    ('2.5.1', 3, 'execute', '학교 네트워크 담당자 교육',    0.0200, '2026-07-01', '2026-11-30', 'artifact', 'SEN-PSR-001-01', False),
    ('2.5.2', 3, 'execute', '보안교육 실시',                0.0200, '2026-07-01', '2026-11-30', 'artifact', 'SEN-SER-002-01', False),
    ('2.5.3', 3, 'execute', '휴대용 저장매체 관리',         0.0100, '2026-07-01', '2026-11-30', 'artifact', 'SEN-SER-001-03', False),

    ('2.6',   2, 'execute', '중간감리 대응',                0.04,   '2026-08-01', '2026-09-30', 'children', None, False),
    ('2.6.1', 3, 'execute', '중간감리 산출물 준비',         0.0200, '2026-08-01', '2026-09-30', 'artifact', 'SEN-PMR-004-05', True),
    ('2.6.2', 3, 'execute', '중간감리 시정조치 처리',       0.0200, '2026-09-01', '2026-09-30', 'artifact', 'SEN-QUR-001-06', False),

    # ══════════════════════════════
    # 3. 종료 단계 (가중치 0.20)
    # ══════════════════════════════
    ('3',     1, 'close',   '종료 단계',                    0.20,   '2026-12-01', '2026-12-31', 'children', None, True),

    ('3.1',   2, 'close',   '종료감리 대응',                0.06,   '2026-11-15', '2026-12-20', 'children', None, False),
    ('3.1.1', 3, 'close',   '종료감리 산출물 준비',         0.0300, '2026-11-15', '2026-12-15', 'artifact', 'SEN-PMR-004-06', True),
    ('3.1.2', 3, 'close',   '종료감리 시정조치 처리',       0.0300, '2026-12-01', '2026-12-20', 'artifact', 'SEN-QUR-001-07', False),

    ('3.2',   2, 'close',   '사업 마무리',                  0.08,   '2026-12-01', '2026-12-31', 'children', None, False),
    ('3.2.1', 3, 'close',   '연간 운영결과 보고서',         0.0300, '2026-12-01', '2026-12-31', 'artifact', 'SEN-PMR-002-02', False),
    ('3.2.2', 3, 'close',   '장비 인수인계 확인서',         0.0200, '2026-12-15', '2026-12-31', 'artifact', 'SEN-OHR-001-04', False),
    ('3.2.3', 3, 'close',   '완료계 제출',                  0.0300, '2026-12-20', '2026-12-31', 'artifact', 'SEN-PMR-004-07', True),

    ('3.3',   2, 'close',   '성과 평가',                    0.06,   '2026-12-01', '2026-12-31', 'children', None, False),
    ('3.3.1', 3, 'close',   'SLA 연간 달성률 집계',         0.0300, '2026-12-01', '2026-12-31', 'manual',   None, False),
    ('3.3.2', 3, 'close',   '품질점검 결과보고서',          0.0300, '2026-12-01', '2026-12-31', 'artifact', 'SEN-QUR-001-03', False),
]


class Command(BaseCommand):
    help = '2026 사업 WBS 기본 데이터 일괄 생성'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, default=None)
        parser.add_argument('--clear', action='store_true',
                            help='기존 WBS 항목 삭제 후 재생성')

    def handle(self, *args, **options):
        project_id = options['project']
        if project_id:
            project = AuditProject.objects.get(pk=project_id)
        else:
            project = AuditProject.objects.filter(is_active=True).first()

        if not project:
            self.stderr.write('활성 감리 프로젝트 없음')
            return

        self.stdout.write(f'프로젝트: {project}')

        if options['clear']:
            deleted, _ = WBSItem.objects.filter(project=project).delete()
            self.stdout.write(f'기존 {deleted}건 삭제')

        # 산출물 템플릿 코드 → 객체 매핑
        tmpl_map = {
            t.code.upper(): t
            for t in ArtifactTemplate.objects.filter(project=project)
        }

        # 코드 → WBSItem 객체 캐시 (parent FK 연결용)
        item_cache: dict[str, WBSItem] = {}
        created = skipped = 0

        for seq, row in enumerate(WBS_DATA):
            (code, depth, phase, name, weight,
             ps, pe, src, tmpl_code, is_milestone) = row

            if WBSItem.objects.filter(project=project, code=code).exists():
                skipped += 1
                item_cache[code] = WBSItem.objects.get(project=project, code=code)
                continue

            parent_code = '.'.join(code.split('.')[:-1]) if '.' in code else None
            parent_obj  = item_cache.get(parent_code) if parent_code else None
            tmpl_obj    = tmpl_map.get(tmpl_code.upper()) if tmpl_code else None

            item = WBSItem.objects.create(
                project         = project,
                code            = code,
                depth           = depth,
                parent          = parent_obj,
                phase           = phase,
                seq             = seq,
                name            = name,
                weight          = weight,
                planned_start   = date.fromisoformat(ps),
                planned_end     = date.fromisoformat(pe),
                progress_source = src,
                linked_template = tmpl_obj,
                is_milestone    = is_milestone,
            )
            item_cache[code] = item
            created += 1
            self.stdout.write(f'  [NEW] {code} {name}')

        self.stdout.write(f'\n완료 — 생성: {created}  건너뜀: {skipped}')
        self.stdout.write('점검계획(InspectionPlan) 연결은 관리자 화면에서 수동 지정하세요.')
        self.stdout.write('  WBSItem 2.3.1 / 2.3.2 / 2.3.3 / 2.4.1 의 linked_inspection 필드')
