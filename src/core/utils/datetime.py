from django.utils import timezone
from datetime import datetime

def get_korean_now():
    """한국 시간 기준 현재 시각"""
    return timezone.now()

def format_datetime(dt):
    if dt is None:
        return ''
    return dt.strftime('%Y-%m-%d %H:%M:%S')
