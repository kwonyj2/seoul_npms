from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workforce', '0003_add_device_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('birth_date',     models.DateField(blank=True, null=True, verbose_name='생년월일')),
                ('join_date',      models.DateField(blank=True, null=True, verbose_name='입사일')),
                ('career_summary', models.TextField(blank=True, verbose_name='경력요약')),
                ('bio',            models.TextField(blank=True, verbose_name='소개')),
                ('notes',          models.TextField(blank=True, verbose_name='비고')),
                ('updated_at',     models.DateTimeField(auto_now=True, verbose_name='수정일시')),
                ('worker', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='worker_profile',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='인력',
                )),
            ],
            options={
                'verbose_name':        '인력 프로필',
                'verbose_name_plural': '인력 프로필 목록',
                'db_table':            'worker_profiles',
            },
        ),
    ]
