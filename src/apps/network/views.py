from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count, Q

@login_required
def network_monitor_view(request):
    return render(request, 'network/monitor.html')


@login_required
def ap_analyzer_view(request):
    return render(request, 'ap_analyzer/index.html')


from .models import (
    NetworkDevice, NetworkPort, NetworkLink,
    NetworkTopology, NetworkEvent, SnmpDevice, SnmpMetric, NetworkCommand
)
from .serializers import (
    NetworkDeviceListSerializer, NetworkDeviceDetailSerializer,
    NetworkPortSerializer, NetworkTopologySerializer,
    NetworkEventSerializer, SnmpMetricSerializer, NetworkCommandSerializer
)
from core.permissions.roles import IsAdmin
from core.pagination import StandardPagination


class NetworkDeviceViewSet(viewsets.ModelViewSet):
    """네트워크 장비 관리 (NMS)"""
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return NetworkDeviceDetailSerializer
        return NetworkDeviceListSerializer

    def get_queryset(self):
        qs = NetworkDevice.objects.select_related('school', 'asset').order_by('school', 'name')
        school_id = self.request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        device_type = self.request.query_params.get('device_type')
        if device_type:
            qs = qs.filter(device_type=device_type)
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(ip_address__icontains=q) |
                Q(hostname__icontains=q) | Q(serial_number__icontains=q)
            )
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """장비 현황 요약"""
        qs = NetworkDevice.objects.values('status').annotate(cnt=Count('id'))
        status_counts = {item['status']: item['cnt'] for item in qs}
        down_devices = NetworkDevice.objects.filter(status='down').values(
            'id', 'name', 'ip_address', 'school__name'
        )[:10]
        return Response({
            'total':    NetworkDevice.objects.count(),
            'up':       status_counts.get('up', 0),
            'down':     status_counts.get('down', 0),
            'warning':  status_counts.get('warning', 0),
            'unknown':  status_counts.get('unknown', 0),
            'down_devices': list(down_devices),
        })

    @action(detail=True, methods=['get'])
    def ports(self, request, pk=None):
        """장비 포트 목록"""
        device = self.get_object()
        ports = device.ports.all()
        return Response(NetworkPortSerializer(ports, many=True).data)

    @action(detail=True, methods=['post'])
    def execute_command(self, request, pk=None):
        """원격 명령 실행"""
        device = self.get_object()
        command_type = request.data.get('command_type')
        command      = request.data.get('command', '')
        if not command_type:
            return Response({'error': '명령 유형이 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        cmd = NetworkCommand.objects.create(
            device=device,
            command_type=command_type,
            command=command,
            executed_by=request.user,
            status='pending',
        )
        # 비동기 실행은 tasks.py에서 처리 (Celery)
        from .tasks import execute_network_command
        execute_network_command.delay(cmd.id)
        return Response(NetworkCommandSerializer(cmd).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def metrics(self, request, pk=None):
        """SNMP 수집 지표"""
        device = self.get_object()
        metric_name = request.query_params.get('metric')
        qs = device.snmp_metrics.order_by('-collected_at')
        if metric_name:
            qs = qs.filter(metric_name=metric_name)
        qs = qs[:100]
        return Response(SnmpMetricSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def school_status(self, request):
        """학교별 장비 상태 현황"""
        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        devices = NetworkDevice.objects.filter(school_id=school_id)
        total   = devices.count()
        up      = devices.filter(status='up').count()
        down    = devices.filter(status='down').count()
        return Response({
            'school_id': school_id,
            'total': total, 'up': up, 'down': down,
            'warning': devices.filter(status='warning').count(),
            'devices': NetworkDeviceListSerializer(devices, many=True).data,
        })


class NetworkTopologyViewSet(viewsets.ReadOnlyModelViewSet):
    """네트워크 토폴로지 스냅샷"""
    serializer_class = NetworkTopologySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = NetworkTopology.objects.select_related('school')
        school_id = self.request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        return qs

    @action(detail=False, methods=['get'])
    def latest(self, request):
        """학교별 최신 토폴로지"""
        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        topo = NetworkTopology.objects.filter(school_id=school_id).order_by('-scanned_at').first()
        if not topo:
            return Response({'error': '토폴로지 데이터가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(NetworkTopologySerializer(topo).data)

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """현재 장비/링크 데이터로 토폴로지 스냅샷 생성"""
        school_id = request.data.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from .services import generate_and_save_topology
            topo = generate_and_save_topology(school_id)
            return Response(NetworkTopologySerializer(topo).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def live(self, request):
        """저장 없이 현재 장비/링크 데이터를 실시간으로 반환"""
        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)
        from .services import build_topology_data
        return Response(build_topology_data(school_id))

    @action(detail=False, methods=['post'])
    def import_json(self, request):
        """Claude 분석 JSON → NetworkDevice + NetworkLink 저장"""
        from apps.schools.models import School
        from .models import NetworkDevice, NetworkLink

        school_id = request.data.get('school_id')
        data      = request.data.get('data', {})
        if not school_id or not data:
            return Response({'error': 'school_id와 data가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': '학교를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])

        # 기존 장비/링크 초기화 (재등록)
        NetworkLink.objects.filter(from_device__school=school, link_type='manual').delete()
        NetworkDevice.objects.filter(school=school, ip_address__isnull=True, snmp_enabled=False).delete()

        name_to_device = {}
        created_devices = 0
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
                created_devices += 1
            name_to_device[name] = dev

        created_links = 0
        CABLE_MAP = {'광': 'fiber', 'Cat6': 'cat6', 'Cat5e': 'cat5e', 'Cat5': 'cat5'}
        for edge in edges:
            fd = name_to_device.get(edge.get('from', ''))
            td = name_to_device.get(edge.get('to', ''))
            if fd and td and fd != td:
                cable_raw = edge.get('cable_type', '')
                NetworkLink.objects.create(
                    from_device=fd, to_device=td,
                    link_type='manual', is_active=True,
                    cable_type=CABLE_MAP.get(cable_raw, 'unknown'),
                    network_type=edge.get('network_type', ''),
                )
                created_links += 1

        return Response({
            'school': school.name,
            'created_devices': created_devices,
            'created_links':   created_links,
        })

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """학교 장비 목록 CSV 다운로드"""
        import csv
        from django.http import HttpResponse
        from apps.schools.models import School
        from .models import NetworkDevice

        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': '학교를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        devices = NetworkDevice.objects.filter(school=school).order_by('network_type', 'name')

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="장비목록_{school.name}.csv"'

        writer = csv.writer(response)
        writer.writerow(['장비명', '모델', '설치위치', '망구분', '장비유형', 'IP주소', '상태'])
        TYPE_KO = {'switch':'스위치','poe_switch':'PoE스위치','ap':'무선AP','router':'라우터','firewall':'방화벽','server':'서버'}
        STATUS_KO = {'up':'정상','down':'장애','warning':'경고','unknown':'미확인'}
        for d in devices:
            writer.writerow([
                d.name, d.model, d.location, d.network_type,
                TYPE_KO.get(d.device_type, d.device_type),
                d.ip_address or '', STATUS_KO.get(d.status, d.status),
            ])
        return response

    @action(detail=False, methods=['get'])
    def snmp_guide(self, request):
        """SNMP 설정 가이드 Word 문서 다운로드"""
        import io
        from django.http import HttpResponse
        from apps.schools.models import School
        from .models import NetworkDevice

        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({'error': '학교를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Cm
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
        except ImportError:
            return Response({'error': 'python-docx가 설치되지 않았습니다.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        devices = NetworkDevice.objects.filter(school=school).order_by('network_type', 'name')
        doc = Document()

        # ── 한글 폰트 전역 설정 (맑은 고딕) ─────────────────────
        KOREAN_FONT = '맑은 고딕'
        style = doc.styles['Normal']
        style.font.name = KOREAN_FONT
        style.font.size = Pt(10)
        rPr = style.element.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            from docx.oxml import OxmlElement
            rFonts = OxmlElement('w:rFonts')
            rPr.append(rFonts)
        rFonts.set(qn('w:ascii'), KOREAN_FONT)
        rFonts.set(qn('w:hAnsi'), KOREAN_FONT)
        rFonts.set(qn('w:eastAsia'), KOREAN_FONT)
        rFonts.set(qn('w:cs'), KOREAN_FONT)
        # 제목 스타일도 한글 폰트 적용
        for heading in ('Heading 1', 'Heading 2', 'Heading 3', 'Title'):
            try:
                h_style = doc.styles[heading]
                h_style.font.name = KOREAN_FONT
                h_rPr = h_style.element.get_or_add_rPr()
                h_rFonts = h_rPr.find(qn('w:rFonts'))
                if h_rFonts is None:
                    from docx.oxml import OxmlElement
                    h_rFonts = OxmlElement('w:rFonts')
                    h_rPr.append(h_rFonts)
                h_rFonts.set(qn('w:ascii'), KOREAN_FONT)
                h_rFonts.set(qn('w:hAnsi'), KOREAN_FONT)
                h_rFonts.set(qn('w:eastAsia'), KOREAN_FONT)
                h_rFonts.set(qn('w:cs'), KOREAN_FONT)
            except KeyError:
                pass

        def _apply_korean_font(run):
            """개별 run에 한글 폰트 명시"""
            run.font.name = KOREAN_FONT
            rPr = run._element.get_or_add_rPr()
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                from docx.oxml import OxmlElement
                rFonts = OxmlElement('w:rFonts')
                rPr.append(rFonts)
            rFonts.set(qn('w:ascii'), KOREAN_FONT)
            rFonts.set(qn('w:hAnsi'), KOREAN_FONT)
            rFonts.set(qn('w:eastAsia'), KOREAN_FONT)
            rFonts.set(qn('w:cs'), KOREAN_FONT)

        # 제목
        title = doc.add_heading(f'{school.name} SNMP 설정 가이드', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            _apply_korean_font(run)

        date_p = doc.add_paragraph(f'작성일: {timezone.now().strftime("%Y년 %m월 %d일")}')
        for run in date_p.runs:
            _apply_korean_font(run)
        doc.add_paragraph()

        def _add_para(text, style=None, bold=False):
            """한글 폰트 자동 적용 paragraph 생성"""
            if style:
                p = doc.add_paragraph(style=style)
                run = p.add_run(text)
            else:
                p = doc.add_paragraph()
                run = p.add_run(text)
            _apply_korean_font(run)
            if bold:
                run.bold = True
            return p

        def _add_heading(text, level):
            h = doc.add_heading(text, level=level)
            for run in h.runs:
                _apply_korean_font(run)
            return h

        # 1. 개요
        _add_heading('1. SNMP 개요', 1)
        _add_para(
            'SNMP(Simple Network Management Protocol)는 네트워크 장비의 상태를 모니터링하기 위한 표준 프로토콜입니다. '
            '본 시스템에서는 SNMPv2c를 사용하여 장비의 가동 상태, 트래픽, 포트 상태를 수집합니다.'
        )

        # 2. 설정 방법
        _add_heading('2. 장비별 SNMP 설정 방법', 1)
        _add_heading('2-1. CBS/C3100/C3500 시리즈 (코어/분배 스위치)', 2)
        for cmd in [
            'snmp-server community public RO',
            'snmp-server community private RW',
            'snmp-server enable traps',
            'snmp-server host [NMS서버IP] traps public',
        ]:
            p = doc.add_paragraph(style='List Bullet')
            run = p.add_run(cmd)
            run.font.name = 'Courier New'

        _add_heading('2-2. GS724T / SG300 시리즈 (접속 스위치)', 2)
        _add_para('웹 관리 인터페이스 접속 → Security → SNMP → Communities 메뉴에서 설정')
        for step in ['Community String: public (Read Only)', 'Trap Host: [NMS서버IP]', 'SNMP Version: v2c']:
            _add_para(step, style='List Bullet')

        # 3. 장비 목록
        _add_heading('3. 장비 목록 및 설정 현황', 1)

        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        hdr = table.rows[0].cells
        for i, h in enumerate(['장비명', '모델', '설치위치', '망구분', 'IP주소', 'SNMP']):
            hdr[i].text = h
            for run in hdr[i].paragraphs[0].runs:
                _apply_korean_font(run)
                run.font.bold = True

        TYPE_KO = {'switch':'스위치','poe_switch':'PoE스위치','ap':'AP','router':'라우터','firewall':'방화벽','server':'서버'}
        for d in devices:
            row = table.add_row().cells
            values = [
                d.name,
                d.model or '-',
                d.location or '-',
                d.network_type or '-',
                d.ip_address or '미등록',
                '설정완료' if d.snmp_enabled else '미설정',
            ]
            for i, v in enumerate(values):
                row[i].text = v
                for run in row[i].paragraphs[0].runs:
                    _apply_korean_font(run)

        # 4. NMS 연동 절차
        _add_heading('4. NMS 연동 절차', 1)
        steps = [
            '장비에 SNMP Community String 설정 (public/private)',
            '장비 IP 주소를 NMS 시스템에 등록',
            '자산 관리 → 네트워크 설정 → SNMP 활성화 체크',
            'NMS 모니터링 탭에서 장비 상태 확인',
            '장애 발생 시 이벤트 알림 자동 수신',
        ]
        for i, s in enumerate(steps, 1):
            _add_para(f'{i}. {s}')

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="SNMP설정가이드_{school.name}.docx"'
        return response

    @action(detail=False, methods=['post'])
    def scan_pptx(self, request):
        """PPTX 구성도 스캔 (NAS /산출물/{school_id}/구성도/*.pptx)

        body:
          {"school_id": 123}   개별 학교만 동기 실행
          {}                    전체 학교 비동기 실행 (Celery)
        """
        from .tasks import scan_network_pptx
        school_id = request.data.get('school_id')
        try:
            if school_id:
                # 개별 학교는 즉시 실행하고 결과 반환
                result = scan_network_pptx(school_id=int(school_id))
                return Response(result, status=status.HTTP_200_OK)
            # 전체는 비동기
            task = scan_network_pptx.delay(school_id=None)
            return Response({'status': 'started', 'task_id': str(task.id)},
                            status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def pptx_status(self, request):
        """특정 학교의 PPTX 파일/파싱 상태 조회"""
        import os
        school_id = request.query_params.get('school_id')
        if not school_id:
            return Response({'error': 'school_id 필요'}, status=status.HTTP_400_BAD_REQUEST)

        base_dir = os.environ.get('NAS_ARTIFACT_ROOT', '/app/nas/media/npms/산출물')
        pptx_dir = os.path.join(base_dir, str(school_id), '구성도')
        files = []
        if os.path.isdir(pptx_dir):
            for f in os.listdir(pptx_dir):
                if f.lower().endswith('.pptx') and not f.startswith('.'):
                    fp = os.path.join(pptx_dir, f)
                    files.append({
                        'filename': f,
                        'size': os.path.getsize(fp),
                        'mtime': os.path.getmtime(fp),
                    })

        topo = NetworkTopology.objects.filter(school_id=school_id).first()
        return Response({
            'school_id': int(school_id),
            'pptx_dir': pptx_dir,
            'pptx_files': sorted(files, key=lambda x: -x['mtime']),
            'topology_exists': topo is not None,
            'slide_titles': topo.slide_titles if topo else [],
            'pptx_path': topo.pptx_path if topo else '',
            'pptx_mtime': topo.pptx_mtime.isoformat() if topo and topo.pptx_mtime else None,
            'updated_at': topo.updated_at.isoformat() if topo else None,
        })


class NetworkEventViewSet(viewsets.ModelViewSet):
    """네트워크 이벤트/알림"""
    serializer_class = NetworkEventSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = NetworkEvent.objects.select_related('device', 'device__school')
        resolved = self.request.query_params.get('resolved')
        if resolved == '0':
            qs = qs.filter(is_resolved=False)
        elif resolved == '1':
            qs = qs.filter(is_resolved=True)
        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        school_id = self.request.query_params.get('school_id')
        if school_id:
            qs = qs.filter(device__school_id=school_id)
        return qs

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """이벤트 해결 처리"""
        event = self.get_object()
        if event.is_resolved:
            return Response({'error': '이미 해결된 이벤트입니다.'}, status=status.HTTP_400_BAD_REQUEST)
        event.is_resolved = True
        event.resolved_at = timezone.now()
        event.save(update_fields=['is_resolved', 'resolved_at'])
        return Response(NetworkEventSerializer(event).data)

    @action(detail=False, methods=['get'])
    def active_summary(self, request):
        """미해결 이벤트 요약"""
        qs = NetworkEvent.objects.filter(is_resolved=False)
        by_severity = qs.values('severity').annotate(cnt=Count('id'))
        return Response({
            'total': qs.count(),
            'by_severity': {item['severity']: item['cnt'] for item in by_severity},
            'latest': NetworkEventSerializer(qs.order_by('-occurred_at')[:5], many=True).data,
        })


class NetworkCommandViewSet(viewsets.ReadOnlyModelViewSet):
    """원격 명령 실행 이력"""
    serializer_class = NetworkCommandSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = NetworkCommand.objects.select_related('device', 'executed_by')
        device_id = self.request.query_params.get('device_id')
        if device_id:
            qs = qs.filter(device_id=device_id)
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        return qs
