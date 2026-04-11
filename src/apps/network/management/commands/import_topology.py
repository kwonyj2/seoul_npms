"""
python manage.py import_topology --school "가락고등학교" --json '{"nodes":[...],"edges":[...]}'
"""
import json
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '학교명 + JSON으로 토폴로지 저장'

    def add_arguments(self, parser):
        parser.add_argument('--school', required=True)
        parser.add_argument('--json', required=True, dest='json_data')

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.network.models import NetworkDevice, NetworkLink

        school_name = options['school']
        try:
            data = json.loads(options['json_data'])
        except json.JSONDecodeError as e:
            self.stderr.write(f'JSON 오류: {e}')
            return

        try:
            school = School.objects.get(name=school_name)
        except School.DoesNotExist:
            self.stderr.write(f'학교 없음: {school_name}')
            return

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])

        NetworkLink.objects.filter(from_device__school=school, link_type='manual').delete()
        NetworkDevice.objects.filter(school=school, ip_address__isnull=True, snmp_enabled=False).delete()

        CABLE_MAP = {'광': 'fiber', 'Cat6': 'cat6', 'Cat5e': 'cat5e', 'Cat5': 'cat5'}
        name_to_dev = {}
        created_d = 0
        for node in nodes:
            name = node.get('name', '').strip()
            if not name:
                continue
            dev, created = NetworkDevice.objects.get_or_create(
                school=school, name=name,
                defaults={
                    'device_type':  node.get('device_type', 'switch'),
                    'model':        node.get('model', ''),
                    'location':     node.get('location', ''),
                    'network_type': node.get('network_type', ''),
                    'status':       'unknown',
                },
            )
            if created:
                created_d += 1
            name_to_dev[name] = dev

        created_l = 0
        for edge in edges:
            fd = name_to_dev.get(edge.get('from', ''))
            td = name_to_dev.get(edge.get('to', ''))
            if fd and td and fd != td:
                NetworkLink.objects.create(
                    from_device=fd, to_device=td,
                    link_type='manual', is_active=True,
                    cable_type=CABLE_MAP.get(edge.get('cable_type', ''), 'unknown'),
                    network_type=edge.get('network_type', ''),
                )
                created_l += 1

        self.stdout.write(f'OK|{school_name}|장비 {created_d}개|링크 {created_l}개')
