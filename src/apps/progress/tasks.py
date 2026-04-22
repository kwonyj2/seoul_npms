from celery import shared_task


@shared_task(name='apps.progress.tasks.generate_yearly_holidays')
def generate_yearly_holidays():
    """매년 1/1 자동 실행: 올해+내년 음력 공휴일 + 대체공휴일 생성"""
    from django.core.management import call_command
    call_command('generate_holidays')
