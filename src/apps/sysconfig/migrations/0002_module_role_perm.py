from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sysconfig', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleRolePerm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_key', models.CharField(max_length=50, verbose_name='모듈 키')),
                ('role', models.CharField(max_length=20, verbose_name='역할')),
                ('allowed', models.BooleanField(default=True, verbose_name='허용')),
            ],
            options={
                'verbose_name': '모듈 역할 권한',
                'db_table': 'sysconfig_module_role_perm',
            },
        ),
        migrations.AlterUniqueTogether(
            name='moduleroleperm',
            unique_together={('module_key', 'role')},
        ),
    ]
