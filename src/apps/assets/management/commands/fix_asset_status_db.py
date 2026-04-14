"""
운용서버 장비 상태 일괄 보정 (DB 기준)

1. current_school이 있는데 status='warehouse' → status='installed' + current_center 설정
2. project_name='창고'이고 status='warehouse' → AssetInbound 자동 생성 (입고일: 2026-05-01)

사용법:
  python manage.py fix_asset_status_db --dry-run   # 변경 없이 미리보기
  python manage.py fix_asset_status_db              # 실제 실행
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = '운용서버 장비 상태 일괄 보정 — 학교 배정 장비 installed 전환 + 창고 장비 입고 레코드 생성'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='DB 변경 없이 결과만 출력')

    def handle(self, *args, **options):
        from apps.assets.models import Asset, AssetInbound, AssetHistory
        from apps.accounts.models import User

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — DB 변경 없음 **\n'))

        admin = User.objects.filter(role='superadmin').first()
        inbound_date = date(2026, 5, 1)

        # ── 1단계: 교육지원청 장비 → edu_office ──
        edu_assets = Asset.objects.filter(
            status='warehouse',
            project_name__icontains='교육지원청',
        )
        edu_count = 0
        for asset in edu_assets:
            if dry_run:
                self.stdout.write(
                    f'  [교육지원청] {asset.serial_number}: warehouse → edu_office'
                    f' | 사업명={asset.project_name}'
                )
            else:
                asset.status = 'edu_office'
                asset.save(update_fields=['status'])
            edu_count += 1

        self.stdout.write(f'\n1단계: 교육지원청 장비 상태 수정 — {edu_count}건')

        # ── 2단계: 학교 배정 장비 → installed ──
        wrong_status = Asset.objects.filter(
            current_school__isnull=False,
        ).exclude(status='installed').select_related('current_school__support_center')

        fix_count = 0
        for asset in wrong_status:
            if dry_run:
                self.stdout.write(
                    f'  [상태수정] {asset.serial_number}: {asset.get_status_display()} → 학교 설치'
                    f' | {asset.current_school.name}'
                )
            else:
                asset.status = 'installed'
                asset.current_center = asset.current_school.support_center
                asset.save(update_fields=['status', 'current_center'])
            fix_count += 1

        self.stdout.write(f'2단계: 학교 배정 장비 상태 수정 — {fix_count}건')

        # ── 3단계: 사업명에 '창고' 포함 장비 → 입고 레코드 생성 ──
        warehouse_assets = Asset.objects.filter(
            status='warehouse',
            project_name__icontains='창고',
        )
        # 이미 입고 레코드 있는 장비 제외
        existing_inbound_ids = set(
            AssetInbound.objects.values_list('asset_id', flat=True)
        )

        inbound_count = 0
        for asset in warehouse_assets:
            if asset.id in existing_inbound_ids:
                continue
            if dry_run:
                self.stdout.write(
                    f'  [입고생성] {asset.serial_number} | 입고일: {inbound_date}'
                )
            else:
                AssetInbound.objects.create(
                    inbound_number=AssetInbound.generate_number(inbound_date),
                    asset=asset,
                    from_location_type='education_office',
                    from_location_name='서울시교육청',
                    to_location_type='warehouse',
                    inbound_date=inbound_date,
                    received_by=admin,
                    note='기존 데이터 일괄 입고 처리',
                )
            inbound_count += 1

        self.stdout.write(f'3단계: 창고 장비 입고 레코드 생성 — {inbound_count}건')

        # ── 나머지 창고 장비 현황 (사업명에 '창고' 없는) ──
        remaining = Asset.objects.filter(status='warehouse').exclude(project_name__icontains='창고')
        if remaining.exists():
            self.stdout.write(f'\n[참고] 사업명에 \"창고\" 없는 창고 장비 {remaining.count()}대:')
            from django.db.models import Count
            for d in remaining.values('project_name').annotate(cnt=Count('id')).order_by('-cnt'):
                self.stdout.write(f'  "{d["project_name"] or "(빈값)"}": {d["cnt"]}대')

        # ── 결과 요약 ──
        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 교육지원청: {edu_count}건, 학교설치: {fix_count}건, 입고생성: {inbound_count}건'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN이므로 실제 변경 없음'))
