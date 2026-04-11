from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ModuleConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_key', models.CharField(max_length=50, unique=True, verbose_name='모듈 키')),
                ('min_role', models.CharField(default='worker', max_length=20, verbose_name='최소 역할')),
            ],
            options={
                'verbose_name': '모듈 설정',
                'db_table': 'sysconfig_module',
            },
        ),
        migrations.CreateModel(
            name='NasRoleConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(max_length=20, verbose_name='역할')),
                ('action', models.CharField(choices=[('upload', '파일 업로드'), ('delete', '파일 삭제'), ('create_folder', '폴더 생성')], max_length=20, verbose_name='행위')),
                ('allowed', models.BooleanField(default=False, verbose_name='허용')),
            ],
            options={
                'verbose_name': 'NAS 역할 권한',
                'db_table': 'sysconfig_nas_role',
            },
        ),
        migrations.AlterUniqueTogether(
            name='nasroleconfig',
            unique_together={('role', 'action')},
        ),
    ]
