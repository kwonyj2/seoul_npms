# Generated manually for asset management system redesign
# 장비관리 시스템 전면 재설계

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0002_devicenetworkconfig'),
        ('schools', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ─────────────────────────────────────
        # 1. Asset 모델 수정
        # ─────────────────────────────────────

        # asset_tag: null=True 허용 (미부여 장비 다수 존재)
        migrations.AlterField(
            model_name='asset',
            name='asset_tag',
            field=models.CharField(
                blank=True, null=True, unique=True, max_length=50,
                verbose_name='관리번호',
                help_text='스티커 부착 관리번호 (향후 일괄 부여)'
            ),
        ),

        # status choices 업데이트 (repair 제거)
        migrations.AlterField(
            model_name='asset',
            name='status',
            field=models.CharField(
                choices=[
                    ('warehouse', '창고 보관'),
                    ('center', '센터 보관'),
                    ('installed', '학교 설치'),
                    ('rma', 'RMA 진행'),
                    ('disposed', '폐기'),
                    ('returned', '교육청 반납'),
                ],
                default='warehouse', max_length=20, verbose_name='상태'
            ),
        ),

        # 불필요 필드 제거 (GPS, QR)
        migrations.RemoveField(model_name='asset', name='install_lat'),
        migrations.RemoveField(model_name='asset', name='install_lng'),
        migrations.RemoveField(model_name='asset', name='qr_code_url'),

        # RMA 교체품 특별관리 필드 추가
        migrations.AddField(
            model_name='asset',
            name='is_rma_replaced',
            field=models.BooleanField(
                default=False, verbose_name='RMA 교체품 여부',
                help_text='RMA 수리불가로 S/N이 변경된 교체품'
            ),
        ),
        migrations.AddField(
            model_name='asset',
            name='replaced_from',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replacement_assets',
                to='assets.asset',
                verbose_name='원본 장비(RMA 교체 전)'
            ),
        ),

        # 인덱스 추가
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(
                fields=['status', 'current_center'],
                name='assets_status_center_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(
                fields=['is_rma_replaced'],
                name='assets_rma_replaced_idx'
            ),
        ),

        # ─────────────────────────────────────
        # 2. AssetInbound 모델 수정
        # ─────────────────────────────────────

        # 구 필드 제거
        migrations.RemoveField(model_name='assetinbound', name='from_source'),
        migrations.RemoveField(model_name='assetinbound', name='signature_data'),

        # asset FK related_name 추가
        migrations.AlterField(
            model_name='assetinbound',
            name='asset',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inbounds',
                to='assets.asset', verbose_name='장비'
            ),
        ),

        # received_by related_name 변경
        migrations.AlterField(
            model_name='assetinbound',
            name='received_by',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_inbounds_received',
                to=settings.AUTH_USER_MODEL, verbose_name='입고담당자'
            ),
        ),

        # ordering 업데이트
        migrations.AlterModelOptions(
            name='assetinbound',
            options={
                'verbose_name': '장비 입고',
                'db_table': 'asset_inbound',
                'ordering': ['-inbound_date', '-created_at'],
            },
        ),

        # 출처 필드 추가
        migrations.AddField(
            model_name='assetinbound',
            name='from_location_type',
            field=models.CharField(
                choices=[
                    ('education_office', '교육청'),
                    ('vendor', '제조사(RMA반환)'),
                    ('school', '학교(회수)'),
                    ('center', '센터'),
                    ('other', '기타'),
                ],
                default='education_office', max_length=30, verbose_name='출처 구분'
            ),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='from_center',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_inbound_from',
                to='schools.supportcenter', verbose_name='출처 센터'
            ),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='from_location_name',
            field=models.CharField(
                blank=True, max_length=200, verbose_name='출처 명칭',
                help_text='교육청명, 학교명, 제조사명 등'
            ),
        ),

        # 목적지 필드 추가
        migrations.AddField(
            model_name='assetinbound',
            name='to_location_type',
            field=models.CharField(
                choices=[('warehouse', '창고'), ('center', '센터')],
                default='warehouse', max_length=20, verbose_name='입고 목적지'
            ),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='to_center',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_inbound_to',
                to='schools.supportcenter', verbose_name='입고 센터'
            ),
        ),

        # 인계/인수 정보 필드 추가
        migrations.AddField(
            model_name='assetinbound',
            name='handover_person',
            field=models.CharField(blank=True, max_length=50, verbose_name='인계자명'),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='handover_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='인계자연락처'),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='handover_signature',
            field=models.TextField(blank=True, verbose_name='인계자서명'),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='receiver_person',
            field=models.CharField(blank=True, max_length=50, verbose_name='인수자명'),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='receiver_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='인수자연락처'),
        ),
        migrations.AddField(
            model_name='assetinbound',
            name='receiver_signature',
            field=models.TextField(blank=True, verbose_name='인수자서명'),
        ),

        # ─────────────────────────────────────
        # 3. AssetOutbound 모델 수정
        # ─────────────────────────────────────

        # 구 필드 제거
        migrations.RemoveField(model_name='assetoutbound', name='signature_data'),

        # asset FK related_name 추가
        migrations.AlterField(
            model_name='assetoutbound',
            name='asset',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='outbounds',
                to='assets.asset', verbose_name='장비'
            ),
        ),

        # issued_by related_name 변경
        migrations.AlterField(
            model_name='assetoutbound',
            name='issued_by',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_outbounds_issued',
                to=settings.AUTH_USER_MODEL, verbose_name='출고담당자'
            ),
        ),

        # to_center related_name 추가
        migrations.AlterField(
            model_name='assetoutbound',
            name='to_center',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_outbound_to',
                to='schools.supportcenter', verbose_name='수령 센터'
            ),
        ),

        # ordering 업데이트
        migrations.AlterModelOptions(
            name='assetoutbound',
            options={
                'verbose_name': '장비 출고',
                'db_table': 'asset_outbound',
                'ordering': ['-outbound_date', '-created_at'],
            },
        ),

        # 출발지 필드 추가
        migrations.AddField(
            model_name='assetoutbound',
            name='from_location_type',
            field=models.CharField(
                choices=[('warehouse', '창고'), ('center', '센터')],
                default='warehouse', max_length=20, verbose_name='출고 출처'
            ),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='from_center',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asset_outbound_from',
                to='schools.supportcenter', verbose_name='출고 센터'
            ),
        ),

        # 목적지 타입 필드 추가
        migrations.AddField(
            model_name='assetoutbound',
            name='to_location_type',
            field=models.CharField(
                choices=[
                    ('center', '센터'),
                    ('school', '학교'),
                    ('vendor', '제조사(RMA발송)'),
                ],
                default='center', max_length=20, verbose_name='출고 목적지'
            ),
        ),

        # 인계/인수 정보 필드 추가
        migrations.AddField(
            model_name='assetoutbound',
            name='handover_person',
            field=models.CharField(blank=True, max_length=50, verbose_name='인계자명'),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='handover_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='인계자연락처'),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='handover_signature',
            field=models.TextField(blank=True, verbose_name='인계자서명'),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='receiver_person',
            field=models.CharField(blank=True, max_length=50, verbose_name='인수자명'),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='receiver_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='인수자연락처'),
        ),
        migrations.AddField(
            model_name='assetoutbound',
            name='receiver_signature',
            field=models.TextField(blank=True, verbose_name='인수자서명'),
        ),

        # ─────────────────────────────────────
        # 4. AssetHistory action choices 업데이트
        # ─────────────────────────────────────
        migrations.AlterField(
            model_name='assethistory',
            name='action',
            field=models.CharField(
                choices=[
                    ('inbound', '입고'),
                    ('outbound', '출고'),
                    ('install', '설치'),
                    ('return', '반납/회수'),
                    ('replace', '교체'),
                    ('rma_send', 'RMA 발송'),
                    ('rma_return', 'RMA 반환(수리)'),
                    ('rma_replaced', 'RMA 교체품 수령'),
                    ('dispose', '폐기'),
                    ('tag', '관리번호 부여'),
                    ('edit', '정보 수정'),
                ],
                max_length=20, verbose_name='작업유형'
            ),
        ),

        # ─────────────────────────────────────
        # 5. AssetRMA 수정 — 교체품 FK 추가
        # ─────────────────────────────────────
        migrations.AlterField(
            model_name='assetrma',
            name='status',
            field=models.CharField(
                choices=[
                    ('sent', 'RMA 발송'),
                    ('received', '제조사 수령'),
                    ('repaired', '수리 완료'),
                    ('returned', '반환 완료(동일 S/N)'),
                    ('replaced', '교체품 수령(S/N 변경)'),
                ],
                default='sent', max_length=20, verbose_name='상태'
            ),
        ),
        migrations.AddField(
            model_name='assetrma',
            name='replacement_asset',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='original_rma',
                to='assets.asset',
                verbose_name='교체품 장비(is_rma_replaced=True)'
            ),
        ),

        # ─────────────────────────────────────
        # 6. AssetInspection 삭제 (사용 안 함)
        # ─────────────────────────────────────
        migrations.DeleteModel(name='AssetInspection'),

        # ─────────────────────────────────────
        # 7. AssetReturn 신규 생성
        # ─────────────────────────────────────
        migrations.CreateModel(
            name='AssetReturn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('return_number', models.CharField(db_index=True, max_length=30,
                                                    unique=True, verbose_name='반납번호')),
                ('from_location_type', models.CharField(
                    choices=[('school', '학교'), ('center', '센터')],
                    default='school', max_length=20, verbose_name='반납 출처'
                )),
                ('to_location_type', models.CharField(
                    choices=[('center', '센터'), ('warehouse', '창고')],
                    default='center', max_length=20, verbose_name='반납 목적지'
                )),
                ('return_date', models.DateField(verbose_name='반납일')),
                ('reason', models.CharField(
                    blank=True, max_length=200, verbose_name='반납 사유',
                    help_text='고장, 교체, 잉여 등'
                )),
                ('handover_person', models.CharField(blank=True, max_length=50,
                                                      verbose_name='인계자명')),
                ('handover_phone', models.CharField(blank=True, max_length=20,
                                                     verbose_name='인계자연락처')),
                ('handover_signature', models.TextField(blank=True, verbose_name='인계자서명')),
                ('receiver_person', models.CharField(blank=True, max_length=50,
                                                      verbose_name='인수자명')),
                ('receiver_phone', models.CharField(blank=True, max_length=20,
                                                     verbose_name='인수자연락처')),
                ('receiver_signature', models.TextField(blank=True, verbose_name='인수자서명')),
                ('note', models.TextField(blank=True, verbose_name='비고')),
                ('pdf_path', models.CharField(blank=True, max_length=500,
                                               verbose_name='반납증PDF경로')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='등록일시')),
                ('asset', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='returns',
                    to='assets.asset', verbose_name='장비'
                )),
                ('from_school', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asset_returns_from_school',
                    to='schools.school', verbose_name='반납 학교'
                )),
                ('from_center', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asset_returns_from_center',
                    to='schools.supportcenter', verbose_name='반납 센터'
                )),
                ('to_center', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asset_returns_to_center',
                    to='schools.supportcenter', verbose_name='수령 센터'
                )),
                ('received_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asset_returns_received',
                    to=settings.AUTH_USER_MODEL, verbose_name='수령담당자'
                )),
            ],
            options={
                'verbose_name': '장비 반납/회수',
                'db_table': 'asset_returns',
                'ordering': ['-return_date', '-created_at'],
            },
        ),

        # ─────────────────────────────────────
        # 8. AssetModelConfig 신규 생성
        # ─────────────────────────────────────
        migrations.CreateModel(
            name='AssetModelConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('vlan_mgmt', models.PositiveSmallIntegerField(
                    blank=True, null=True, verbose_name='관리 VLAN'
                )),
                ('vlan_data', models.CharField(
                    blank=True, max_length=200, verbose_name='데이터 VLAN 목록',
                    help_text='예: 10,20,30'
                )),
                ('uplink_port', models.CharField(blank=True, max_length=50,
                                                   verbose_name='업링크 포트')),
                ('uplink_speed', models.CharField(blank=True, max_length=30,
                                                    verbose_name='업링크 속도')),
                ('ssh_enabled', models.BooleanField(default=True, verbose_name='SSH 활성')),
                ('snmp_community', models.CharField(blank=True, max_length=100,
                                                     verbose_name='SNMP Community')),
                ('firmware_ver', models.CharField(blank=True, max_length=100,
                                                    verbose_name='표준 펌웨어 버전')),
                ('config_commands', models.TextField(
                    blank=True, verbose_name='설정 CLI 명령어',
                    help_text='향후 장비 자동 설정 투입용 CLI 명령어 (C3100-24TL 등)'
                )),
                ('config_note', models.TextField(blank=True, verbose_name='설정 메모')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='수정일시')),
                ('asset_model', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='model_config',
                    to='assets.assetmodel', verbose_name='장비 모델'
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL, verbose_name='최종수정자'
                )),
            ],
            options={
                'verbose_name': '장비 모델 표준 설정',
                'db_table': 'asset_model_configs',
            },
        ),
    ]
