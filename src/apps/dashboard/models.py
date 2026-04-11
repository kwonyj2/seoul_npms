import logging
from django.db import models

logger = logging.getLogger(__name__)


def channel_layer_push(group_name, event):
    """채널 레이어로 그룹 메시지 전송 (sync-safe)"""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(group_name, event)
    except Exception as e:
        logger.debug('channel_layer_push 실패 group=%s: %s', group_name, e)


class Notification(models.Model):
    """앱 내 알림센터"""
    TYPE_CHOICES = [
        ('incident',   '장애'),
        ('sla',        'SLA'),
        ('wbs',        'WBS'),
        ('inspection', '점검'),
        ('report',     '보고서'),
        ('system',     '시스템'),
    ]
    LEVEL_CHOICES = [
        ('info',    '정보'),
        ('warning', '경고'),
        ('danger',  '위험'),
        ('success', '완료'),
    ]

    user      = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='notifications', verbose_name='수신자'
    )
    ntype     = models.CharField('유형', max_length=20, choices=TYPE_CHOICES, default='system')
    level     = models.CharField('레벨', max_length=10, choices=LEVEL_CHOICES, default='info')
    title     = models.CharField('제목', max_length=200)
    message   = models.TextField('내용', blank=True)
    link      = models.CharField('이동 URL', max_length=500, blank=True)
    is_read   = models.BooleanField('읽음', default=False)
    read_at   = models.DateTimeField('읽은 시각', null=True, blank=True)
    created_at= models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        db_table     = 'notifications'
        verbose_name = '알림'
        ordering     = ['-created_at']
        indexes      = [models.Index(fields=['user', 'is_read', '-created_at'])]

    def __str__(self):
        return f'[{self.get_ntype_display()}] {self.title}'

    @classmethod
    def push(cls, user, title, message='', ntype='system',
             level='info', link=''):
        """알림 생성 헬퍼 — Notification.push(user, ...) 로 어디서든 호출"""
        obj = cls.objects.create(
            user=user, title=title, message=message,
            ntype=ntype, level=level, link=link,
        )
        # 실시간 WebSocket 푸시
        unread = cls.objects.filter(user=user, is_read=False).count()
        channel_layer_push(
            f'notification_{user.pk}',
            {
                'type': 'notification.push',
                'count': unread,
                'notification': {
                    'id': obj.pk, 'title': title,
                    'ntype': ntype, 'level': level, 'link': link,
                },
            },
        )
        return obj

    @classmethod
    def broadcast(cls, queryset, title, message='', ntype='system',
                  level='info', link=''):
        """여러 사용자에게 동시 발송"""
        users = list(queryset)
        objs = [
            cls(user=u, title=title, message=message,
                ntype=ntype, level=level, link=link)
            for u in users
        ]
        cls.objects.bulk_create(objs)
        # 각 사용자에게 실시간 WebSocket 푸시
        for u in users:
            unread = cls.objects.filter(user=u, is_read=False).count()
            channel_layer_push(
                f'notification_{u.pk}',
                {
                    'type': 'notification.push',
                    'count': unread,
                    'notification': {'title': title, 'ntype': ntype, 'level': level},
                },
            )
