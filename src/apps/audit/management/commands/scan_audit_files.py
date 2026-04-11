"""
NAS 폴더 자동 스캔 명령
2026감리산출물/{산출물코드}/ 하위의 파일을 읽어 ArtifactFile 레코드 생성/갱신

파일명은 자유롭게 사용 가능. 날짜/장소 패턴이 인식되면 자동 추출하고,
인식 안 되면 발생일·장소를 비워 두고 등록함 (나중에 수동 입력 가능).

사용법:
  docker exec npms_web python manage.py scan_audit_files
  docker exec npms_web python manage.py scan_audit_files --dry-run
  docker exec npms_web python manage.py scan_audit_files --project 1
"""
import os
import re
from datetime import date

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.audit.models import AuditProject, ArtifactTemplate, ArtifactFile


# 산출물 코드 패턴: SEN-XXX-NNN-NN
CODE_RE = re.compile(r'^(SEN-[A-Z]+-\d{3}-\d{2})', re.IGNORECASE)
# 날짜 패턴
DATE8_RE  = re.compile(r'(\d{8})')          # 20260612
DATE6_RE  = re.compile(r'(\d{6})')          # 202605
QUARTER_RE = re.compile(r'(\d{4})Q(\d)')    # 2026Q1


def _parse_date(part: str):
    """문자열에서 날짜 추출 → date 객체 or None, 남은 문자열"""
    m = DATE8_RE.search(part)
    if m:
        s = m.group(1)
        try:
            d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            return d, part.replace(s, '').strip('_')
        except ValueError:
            pass

    m = QUARTER_RE.search(part)
    if m:
        year, q = int(m.group(1)), int(m.group(2))
        month = (q - 1) * 3 + 1
        try:
            d = date(year, month, 1)
            return d, part.replace(m.group(0), '').strip('_')
        except ValueError:
            pass

    m = DATE6_RE.search(part)
    if m:
        s = m.group(1)
        try:
            d = date(int(s[:4]), int(s[4:6]), 1)
            return d, part.replace(s, '').strip('_')
        except ValueError:
            pass

    return None, part


def parse_filename(filename: str, template_code: str):
    """
    파일명 파싱 → (display_name, occurrence_date, location_note)
    """
    base, _ = os.path.splitext(filename)

    # 코드 접두사 제거
    prefix = template_code + '_'
    rest = base[len(prefix):] if base.upper().startswith(prefix.upper()) else base

    occurrence_date, rest = _parse_date(rest)

    # 남은 부분 = 장소 or 설명
    rest = rest.strip('_').strip()

    # 언더스코어로 분리된 경우 앞부분=장소, 뒷부분=추가설명
    parts = [p for p in rest.split('_') if p]
    location_note = parts[0] if parts else ''
    display_name  = rest if rest else template_code

    return display_name, occurrence_date, location_note


class Command(BaseCommand):
    help = 'NAS 2026감리산출물 폴더를 스캔해 ArtifactFile 레코드 자동 생성/갱신'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, default=None,
                            help='특정 프로젝트 ID만 처리 (미지정 시 활성 프로젝트)')
        parser.add_argument('--dry-run', action='store_true',
                            help='실제 DB 저장 없이 결과만 출력')

    def handle(self, *args, **options):
        dry_run    = options['dry_run']
        project_id = options['project']

        if project_id:
            project = AuditProject.objects.get(pk=project_id)
        else:
            project = AuditProject.objects.filter(is_active=True).first()

        if not project:
            self.stderr.write('활성 감리 프로젝트가 없습니다.')
            return

        self.stdout.write(f'프로젝트: {project}')
        if dry_run:
            self.stdout.write('[DRY-RUN 모드 — DB 저장 안 함]')

        base_dir = os.path.join(settings.MEDIA_ROOT, '2026감리산출물')
        if not os.path.isdir(base_dir):
            self.stderr.write(f'폴더 없음: {base_dir}')
            return

        # 템플릿 코드 → 객체 매핑
        tmpl_map = {
            t.code.upper(): t
            for t in ArtifactTemplate.objects.filter(project=project)
        }

        total_new = total_skip = total_err = 0

        for entry in sorted(os.scandir(base_dir), key=lambda e: e.name):
            if not entry.is_dir():
                continue

            code_upper = entry.name.upper()
            tmpl = tmpl_map.get(code_upper)
            if not tmpl:
                self.stdout.write(f'  [SKIP] 미매핑 폴더: {entry.name}')
                continue

            self.stdout.write(f'\n  [{tmpl.code}] {tmpl.name}')

            for fentry in sorted(os.scandir(entry.path), key=lambda e: e.name):
                if not fentry.is_file():
                    continue
                fname = fentry.name
                if fname.startswith('.'):
                    continue

                # 이미 등록된 파일인지 확인 (file_name 기준)
                exists = ArtifactFile.objects.filter(
                    project=project, template=tmpl, file_name=fname
                ).exists()

                if exists:
                    total_skip += 1
                    self.stdout.write(f'    [EXISTS] {fname}')
                    continue

                try:
                    display_name, occ_date, loc_note = parse_filename(fname, tmpl.code)
                    fsize = fentry.stat().st_size

                    # 파일 경로 (MEDIA_ROOT 기준 상대경로)
                    rel_path = os.path.relpath(fentry.path, settings.MEDIA_ROOT)

                    if not dry_run:
                        ArtifactFile.objects.create(
                            project=project,
                            template=tmpl,
                            file=rel_path,          # 상대경로로 저장
                            file_name=fname,
                            display_name=display_name,
                            file_size=fsize,
                            occurrence_date=occ_date,
                            location_note=loc_note,
                            is_scanned=True,
                        )
                    total_new += 1
                    date_str = str(occ_date) if occ_date else '-'
                    self.stdout.write(
                        f'    [NEW] {fname}  날짜={date_str}  장소={loc_note or "-"}'
                    )
                except Exception as e:
                    total_err += 1
                    self.stdout.write(f'    [ERR] {fname}: {e}')

        self.stdout.write(
            f'\n스캔 완료 — 신규: {total_new}  기존: {total_skip}  오류: {total_err}'
        )
