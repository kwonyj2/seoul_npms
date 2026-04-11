"""
network 앱 모델
NMS - 장비 모니터링, SNMP, 토폴로지 자동 생성
"""
from django.db import models


class NetworkDevice(models.Model):
    """네트워크 장비 (모니터링 대상)"""
    DEVICE_TYPE_CHOICES = [
        ('switch',     '스위치'),
        ('poe_switch', 'PoE 스위치'),
        ('ap',         '무선 AP'),
        ('router',     '라우터'),
        ('firewall',   '방화벽'),
        ('server',     '서버'),
    ]
    STATUS_CHOICES = [
        ('up',      '정상'),
        ('down',    '장애'),
        ('warning', '경고'),
        ('unknown', '미확인'),
    ]
    school        = models.ForeignKey('schools.School', on_delete=models.CASCADE, verbose_name='학교', related_name='network_devices')
    asset         = models.OneToOneField('assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
                                          verbose_name='자산 연결', related_name='network_device')
    device_type   = models.CharField('장비유형', max_length=20, choices=DEVICE_TYPE_CHOICES)
    name          = models.CharField('장비명', max_length=100)
    ip_address    = models.GenericIPAddressField('IP주소', null=True, blank=True, db_index=True)
    mac_address   = models.CharField('MAC주소', max_length=17, blank=True)
    hostname      = models.CharField('호스트명', max_length=100, blank=True)
    manufacturer  = models.CharField('제조사', max_length=100, blank=True)
    model         = models.CharField('모델명', max_length=100, blank=True)
    firmware      = models.CharField('펌웨어', max_length=50, blank=True)
    serial_number = models.CharField('S/N', max_length=100, blank=True)
    status        = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='unknown')
    location      = models.CharField('설치위치', max_length=200, blank=True)
    network_type  = models.CharField('망구분', max_length=20, blank=True)
    snmp_enabled  = models.BooleanField('SNMP 활성', default=False)
    ssh_enabled   = models.BooleanField('SSH 활성', default=False)
    last_seen     = models.DateTimeField('마지막 응답', null=True, blank=True)
    uptime_seconds= models.BigIntegerField('가동시간(초)', null=True, blank=True)
    created_at    = models.DateTimeField('등록일시', auto_now_add=True)
    updated_at    = models.DateTimeField('수정일시', auto_now=True)

    class Meta:
        db_table = 'network_devices'
        verbose_name = '네트워크 장비'
        verbose_name_plural = '네트워크 장비 목록'
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['status', 'last_seen']),
        ]

    def __str__(self):
        return f'{self.school.name} - {self.name} ({self.ip_address})'


class NetworkPort(models.Model):
    """장비 포트"""
    STATUS_CHOICES = [
        ('up',       '활성'),
        ('down',     '비활성'),
        ('disabled', '비사용'),
    ]
    device    = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='장비', related_name='ports')
    port_num  = models.PositiveSmallIntegerField('포트번호')
    port_name = models.CharField('포트명', max_length=50, blank=True)
    status    = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='down')
    speed_mbps= models.PositiveIntegerField('속도(Mbps)', null=True, blank=True)
    vlan_id   = models.PositiveSmallIntegerField('VLAN ID', null=True, blank=True)
    connected_mac = models.CharField('연결 MAC', max_length=17, blank=True)
    is_poe    = models.BooleanField('PoE 포트', default=False)
    poe_power_mw  = models.PositiveIntegerField('PoE 전력(mW)', null=True, blank=True)
    updated_at= models.DateTimeField('갱신일시', auto_now=True)

    class Meta:
        db_table = 'network_ports'
        verbose_name = '네트워크 포트'
        unique_together = [['device', 'port_num']]
        ordering = ['device', 'port_num']

    def __str__(self):
        return f'{self.device.name} Port {self.port_num}'


class NetworkLink(models.Model):
    """장비 간 연결 (토폴로지 링크)"""
    LINK_TYPE_CHOICES = [
        ('lldp', 'LLDP'),
        ('cdp',  'CDP'),
        ('arp',  'ARP/MAC'),
        ('manual', '수동등록'),
    ]
    CABLE_TYPE_CHOICES = [
        ('fiber', '광'),
        ('cat6',  'Cat6'),
        ('cat5e', 'Cat5e'),
        ('cat5',  'Cat5'),
        ('unknown', '미확인'),
    ]
    from_device  = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='출발장비', related_name='outgoing_links')
    from_port    = models.ForeignKey(NetworkPort, on_delete=models.SET_NULL, null=True, blank=True,
                                      verbose_name='출발포트', related_name='outgoing_links')
    to_device    = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='도착장비', related_name='incoming_links')
    to_port      = models.ForeignKey(NetworkPort, on_delete=models.SET_NULL, null=True, blank=True,
                                      verbose_name='도착포트', related_name='incoming_links')
    link_type    = models.CharField('수집방식', max_length=10, choices=LINK_TYPE_CHOICES)
    cable_type   = models.CharField('케이블종류', max_length=10, choices=CABLE_TYPE_CHOICES, default='unknown')
    network_type = models.CharField('망구분', max_length=20, blank=True)
    speed_mbps   = models.PositiveIntegerField('속도(Mbps)', null=True, blank=True)
    is_active    = models.BooleanField('활성', default=True)
    discovered_at= models.DateTimeField('발견일시', auto_now_add=True)

    class Meta:
        db_table = 'network_links'
        verbose_name = '네트워크 링크'


class NetworkTopology(models.Model):
    """학교 네트워크 토폴로지 스냅샷"""
    school       = models.ForeignKey('schools.School', on_delete=models.CASCADE, verbose_name='학교', related_name='topologies')
    topology_data= models.JSONField('토폴로지 데이터', default=dict,
                                     help_text='{"nodes": [...], "edges": [...]}')
    scanned_at   = models.DateTimeField('스캔일시', auto_now_add=True)

    class Meta:
        db_table = 'network_topology'
        verbose_name = '네트워크 토폴로지'
        ordering = ['-scanned_at']

    def __str__(self):
        return f'{self.school.name} - {self.scanned_at}'


class NetworkEvent(models.Model):
    """네트워크 이벤트/알림"""
    SEVERITY_CHOICES = [
        ('critical', '긴급'),
        ('major',    '심각'),
        ('minor',    '경미'),
        ('info',     '정보'),
    ]
    EVENT_TYPE_CHOICES = [
        ('device_down',   '장비 다운'),
        ('device_up',     '장비 복구'),
        ('port_down',     '포트 다운'),
        ('port_up',       '포트 복구'),
        ('high_traffic',  '트래픽 과부하'),
        ('snmp_timeout',  'SNMP 타임아웃'),
        ('loop_detected', '루핑 감지'),
        ('new_device',    '신규 장비 감지'),
    ]
    device     = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='장비', related_name='events')
    event_type = models.CharField('이벤트유형', max_length=30, choices=EVENT_TYPE_CHOICES)
    severity   = models.CharField('심각도', max_length=10, choices=SEVERITY_CHOICES)
    message    = models.TextField('메시지')
    is_resolved= models.BooleanField('해결여부', default=False)
    resolved_at= models.DateTimeField('해결일시', null=True, blank=True)
    incident   = models.ForeignKey('incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True,
                                    verbose_name='연관장애', related_name='network_events')
    occurred_at= models.DateTimeField('발생일시', auto_now_add=True)

    class Meta:
        db_table = 'network_events'
        verbose_name = '네트워크 이벤트'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['is_resolved', 'occurred_at']),
        ]


class SnmpDevice(models.Model):
    """SNMP 수집 설정"""
    device          = models.OneToOneField(NetworkDevice, on_delete=models.CASCADE, verbose_name='장비', related_name='snmp')
    community       = models.CharField('Community String', max_length=50, default='public')
    version         = models.CharField('SNMP 버전', max_length=5, default='v2c', choices=[('v1','v1'),('v2c','v2c'),('v3','v3')])
    port            = models.PositiveSmallIntegerField('포트', default=161)
    poll_interval_s = models.PositiveSmallIntegerField('수집주기(초)', default=300)
    is_active       = models.BooleanField('수집 활성', default=True)
    last_poll_at    = models.DateTimeField('마지막수집', null=True, blank=True)

    class Meta:
        db_table = 'snmp_devices'
        verbose_name = 'SNMP 설정'


class SnmpMetric(models.Model):
    """SNMP 수집 데이터"""
    device       = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='장비', related_name='snmp_metrics')
    metric_name  = models.CharField('지표명', max_length=100)
    oid          = models.CharField('OID', max_length=200, blank=True)
    value        = models.CharField('값', max_length=500)
    collected_at = models.DateTimeField('수집일시', db_index=True)

    class Meta:
        db_table = 'snmp_metrics'
        verbose_name = 'SNMP 지표'
        ordering = ['-collected_at']
        indexes = [
            models.Index(fields=['device', 'metric_name', 'collected_at']),
        ]


class NetworkCommand(models.Model):
    """원격 명령 실행 이력"""
    STATUS_CHOICES = [
        ('pending',   '대기'),
        ('running',   '실행중'),
        ('success',   '성공'),
        ('failed',    '실패'),
    ]
    COMMAND_TYPE_CHOICES = [
        ('port_restart', '포트 재시작'),
        ('device_reboot','장비 재부팅'),
        ('vlan_change',  'VLAN 변경'),
        ('ssid_change',  'SSID 변경'),
        ('fw_update',    '펌웨어 업데이트'),
        ('custom',       '직접 명령'),
    ]
    device       = models.ForeignKey(NetworkDevice, on_delete=models.CASCADE, verbose_name='장비', related_name='commands')
    command_type = models.CharField('명령유형', max_length=20, choices=COMMAND_TYPE_CHOICES)
    command      = models.TextField('실행명령')
    result       = models.TextField('실행결과', blank=True)
    status       = models.CharField('상태', max_length=10, choices=STATUS_CHOICES, default='pending')
    executed_by  = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='실행자')
    executed_at  = models.DateTimeField('실행일시', auto_now_add=True)

    class Meta:
        db_table = 'network_commands'
        verbose_name = '원격 명령'
        ordering = ['-executed_at']
