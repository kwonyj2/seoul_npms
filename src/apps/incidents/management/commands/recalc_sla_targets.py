"""
management command: recalc_sla_targets
기존 IncidentSLA 레코드의 arrival_target / resolve_target 을
업무시간 기준으로 재계산하고, Incident.sla_arrival_ok / sla_resolve_ok 도 갱신.
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = '기존 IncidentSLA 목표시각을 업무시간 기준으로 재계산'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='저장 없이 결과만 출력')

    def handle(self, *args, **options):
        from apps.incidents.models import Incident, IncidentSLA
        from core.sla_utils import add_business_hours

        dry_run = options['dry_run']
        sla_arrival = getattr(settings, 'SLA_ARRIVAL_HOURS', 2)
        sla_resolve = getattr(settings, 'SLA_RESOLVE_HOURS', 8)

        qs = IncidentSLA.objects.select_related(
            'incident', 'incident__original_incident'
        ).filter(is_adjusted=False)  # 고객 협의 조정 건은 제외
        total = qs.count()
        skipped = IncidentSLA.objects.filter(is_adjusted=True).count()
        self.stdout.write(f'총 {total}건 처리 시작... (고객협의 조정 {skipped}건 제외)')

        updated = 0
        for sla in qs.iterator(chunk_size=200):
            inc = sla.incident
            sla_base = (
                inc.original_incident.received_at
                if inc.is_recurrence and inc.original_incident
                else inc.received_at
            )
            new_arrival = add_business_hours(sla_base, sla_arrival)
            new_resolve = add_business_hours(sla_base, sla_resolve)

            sla.arrival_target = new_arrival
            sla.resolve_target = new_resolve

            # 준수 여부 재판정
            if inc.arrived_at:
                sla.arrival_ok = inc.arrived_at <= new_arrival
                inc.sla_arrival_ok = sla.arrival_ok
            if inc.completed_at:
                sla.resolve_ok = inc.completed_at <= new_resolve
                inc.sla_resolve_ok = sla.resolve_ok

            if not dry_run:
                sla.save(update_fields=['arrival_target', 'resolve_target',
                                        'arrival_ok', 'resolve_ok'])
                inc.save(update_fields=['sla_arrival_ok', 'sla_resolve_ok'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY-RUN] " if dry_run else ""}완료: {updated}/{total}건 재계산'
        ))
