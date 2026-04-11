from rest_framework import serializers
from django.utils import timezone
from .models import (MaterialCategory, Material, WarehouseInventory,
                     CenterInventory, MaterialInbound, MaterialOutbound,
                     MaterialReturn, MaterialUsage, MaterialForecast)
from apps.schools.models import SupportCenter


class MaterialCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = MaterialCategory
        fields = ['id', 'code', 'name', 'type_code', 'order']


class MaterialSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    warehouse_qty = serializers.SerializerMethodField()

    class Meta:
        model  = Material
        fields = ['id', 'code', 'name', 'spec', 'unit',
                  'category', 'category_name', 'min_stock',
                  'supplier', 'is_active', 'warehouse_qty']

    def get_warehouse_qty(self, obj):
        try:
            return obj.warehouse_inventory.quantity
        except Exception:
            return 0


class WarehouseInventorySerializer(serializers.ModelSerializer):
    material_name  = serializers.CharField(source='material.name',          read_only=True)
    material_code  = serializers.CharField(source='material.code',          read_only=True)
    material_spec  = serializers.CharField(source='material.spec',          read_only=True)
    category_name  = serializers.CharField(source='material.category.name', read_only=True)
    unit           = serializers.CharField(source='material.unit',          read_only=True)
    min_stock      = serializers.IntegerField(source='material.min_stock',  read_only=True)
    is_low         = serializers.SerializerMethodField()

    class Meta:
        model  = WarehouseInventory
        fields = ['id', 'material', 'material_name', 'material_code', 'material_spec',
                  'category_name', 'unit', 'quantity', 'min_stock', 'is_low', 'updated_at']

    def get_is_low(self, obj):
        return obj.material.min_stock > 0 and obj.quantity <= obj.material.min_stock


class CenterInventorySerializer(serializers.ModelSerializer):
    center_name   = serializers.CharField(source='support_center.name',   read_only=True)
    material_name = serializers.CharField(source='material.name',         read_only=True)
    material_code = serializers.CharField(source='material.code',         read_only=True)
    material_spec = serializers.CharField(source='material.spec',         read_only=True)
    category_name = serializers.CharField(source='material.category.name',read_only=True)
    unit          = serializers.CharField(source='material.unit',         read_only=True)

    class Meta:
        model  = CenterInventory
        fields = ['id', 'support_center', 'center_name',
                  'material', 'material_name', 'material_code', 'material_spec',
                  'category_name', 'unit', 'quantity', 'updated_at']


class MaterialInboundSerializer(serializers.ModelSerializer):
    material_name    = serializers.CharField(source='material.name',          read_only=True)
    material_code    = serializers.CharField(source='material.code',          read_only=True)
    material_spec    = serializers.CharField(source='material.spec',          read_only=True)
    material_unit    = serializers.CharField(source='material.unit',          read_only=True)
    category_name    = serializers.CharField(source='material.category.name', read_only=True)
    received_by_name = serializers.SerializerMethodField()
    from_center_name = serializers.CharField(source='from_center.name', read_only=True)

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return obj.received_by.name or obj.received_by.username

    class Meta:
        model            = MaterialInbound
        fields           = ['id', 'inbound_number', 'material', 'material_name',
                             'material_code', 'material_spec', 'material_unit', 'category_name',
                             'quantity', 'unit_price', 'inbound_type', 'from_center', 'from_center_name',
                             'supplier', 'handover_person', 'receiver_person',
                             'inbound_date', 'received_by', 'received_by_name', 'note', 'pdf_path',
                             'handover_signature', 'receiver_signature',
                             'handover_phone', 'receiver_phone', 'created_at']
        read_only_fields = ['inbound_number', 'from_center_name']

    def create(self, validated_data):
        validated_data['inbound_number'] = MaterialInbound.generate_number()
        validated_data.setdefault('unit_price', 0)
        inbound = super().create(validated_data)
        # 창고 재고 증가
        inv, _ = WarehouseInventory.objects.get_or_create(
            material=inbound.material, defaults={'quantity': 0}
        )
        inv.quantity += inbound.quantity
        inv.save()
        # 반납 입고: 해당 센터 재고 감소 + 센터 출고 이력 자동 생성
        if inbound.inbound_type == 'return' and inbound.from_center:
            center_inv = CenterInventory.objects.filter(
                material=inbound.material, support_center=inbound.from_center
            ).first()
            if center_inv:
                center_inv.quantity = max(0, center_inv.quantity - inbound.quantity)
                center_inv.save()
            # 센터 출고 이력 자동 생성 (창고 반납)
            MaterialOutbound.objects.create(
                outbound_number=MaterialOutbound.generate_number(inbound.inbound_date),
                material=inbound.material,
                quantity=inbound.quantity,
                from_warehouse=False,
                from_center=inbound.from_center,
                to_center=None,
                outbound_date=inbound.inbound_date,
                issued_by=inbound.received_by,
                handover_person=inbound.handover_person,
                handover_phone=inbound.handover_phone,
                receiver_person=inbound.receiver_person,
                receiver_phone=inbound.receiver_phone,
                note=f'창고 반납 (입고번호: {inbound.inbound_number})',
            )
        return inbound

    def update(self, instance, validated_data):
        old_qty = instance.quantity
        inbound = super().update(instance, validated_data)
        new_qty = inbound.quantity
        # 수량 변경 시 창고 재고 차이만큼 조정
        diff = new_qty - old_qty
        if diff != 0:
            inv, _ = WarehouseInventory.objects.get_or_create(
                material=inbound.material, defaults={'quantity': 0}
            )
            inv.quantity = max(0, inv.quantity + diff)
            inv.save()
        return inbound


class MaterialOutboundSerializer(serializers.ModelSerializer):
    material_name  = serializers.CharField(source='material.name',          read_only=True)
    material_code  = serializers.CharField(source='material.code',          read_only=True)
    material_spec  = serializers.CharField(source='material.spec',          read_only=True)
    material_unit  = serializers.CharField(source='material.unit',          read_only=True)
    category_name  = serializers.CharField(source='material.category.name', read_only=True)
    to_center_name        = serializers.CharField(source='to_center.name',   read_only=True, default=None)
    from_center_name      = serializers.CharField(source='from_center.name', read_only=True, default=None)
    to_worker_name        = serializers.CharField(source='to_worker.name',   read_only=True, default=None)
    issued_by_name        = serializers.SerializerMethodField()
    issued_by_center_name = serializers.SerializerMethodField()

    def get_issued_by_name(self, obj):
        if not obj.issued_by:
            return None
        return obj.issued_by.name or obj.issued_by.username

    def get_issued_by_center_name(self, obj):
        if obj.from_center:
            return obj.from_center.name
        if not obj.issued_by or not obj.issued_by.support_center:
            return None
        return obj.issued_by.support_center.name

    class Meta:
        model            = MaterialOutbound
        fields           = ['id', 'outbound_number', 'material', 'material_name',
                             'material_code', 'material_spec', 'material_unit', 'category_name',
                             'quantity', 'from_warehouse', 'from_center', 'from_center_name',
                             'to_center', 'to_center_name',
                             'to_worker', 'to_worker_name', 'to_school', 'outbound_date',
                             'issued_by', 'issued_by_name', 'issued_by_center_name',
                             'handover_person', 'receiver_person', 'note', 'pdf_path',
                             'handover_signature', 'receiver_signature',
                             'handover_phone', 'receiver_phone', 'created_at']
        read_only_fields = ['outbound_number', 'from_center_name']

    def validate(self, attrs):
        material = attrs.get('material')
        qty      = attrs.get('quantity', 0)
        # 수정 시에는 기존 수량과의 차이만큼만 검증
        if self.instance:
            diff = qty - self.instance.quantity if (material and qty) else 0
            if diff > 0:
                try:
                    inv = WarehouseInventory.objects.get(material=material or self.instance.material)
                    if inv.quantity < diff:
                        raise serializers.ValidationError(
                            f'창고 재고 부족: 현재 {inv.quantity}, 추가필요 {diff}'
                        )
                except WarehouseInventory.DoesNotExist:
                    raise serializers.ValidationError('창고 재고 없음')
        elif material and qty:
            try:
                inv = WarehouseInventory.objects.get(material=material)
                if inv.quantity < qty:
                    raise serializers.ValidationError(
                        f'창고 재고 부족: 현재 {inv.quantity}, 요청 {qty}'
                    )
            except WarehouseInventory.DoesNotExist:
                raise serializers.ValidationError('창고 재고 없음 — 입고 먼저 필요')
        return attrs

    def create(self, validated_data):
        date_str = timezone.now().strftime('%Y%m%d')
        seq = MaterialOutbound.objects.filter(
            outbound_number__startswith=f'OUT{date_str}'
        ).count() + 1
        validated_data['outbound_number'] = f'OUT{date_str}_{seq:03d}'
        outbound = super().create(validated_data)
        # 창고 재고 감소 (validate에서 이미 충분한 재고 확인됨)
        inv = WarehouseInventory.objects.get(material=outbound.material)
        inv.quantity -= outbound.quantity
        inv.save()
        # 지원청 재고 자동 증가
        if outbound.to_center:
            cinv, _ = CenterInventory.objects.get_or_create(
                support_center=outbound.to_center,
                material=outbound.material,
                defaults={'quantity': 0}
            )
            cinv.quantity += outbound.quantity
            cinv.save()
        return outbound

    def update(self, instance, validated_data):
        old_qty    = instance.quantity
        old_center = instance.to_center
        outbound   = super().update(instance, validated_data)
        new_qty    = outbound.quantity
        new_center = outbound.to_center
        diff = new_qty - old_qty
        if diff != 0:
            # 창고 재고 역방향 조정
            inv, _ = WarehouseInventory.objects.get_or_create(
                material=outbound.material, defaults={'quantity': 0}
            )
            inv.quantity = max(0, inv.quantity - diff)
            inv.save()
            # 기존 지원청 재고 조정
            if old_center:
                try:
                    cinv = CenterInventory.objects.get(
                        support_center=old_center, material=outbound.material
                    )
                    cinv.quantity = max(0, cinv.quantity - diff)
                    cinv.save()
                except CenterInventory.DoesNotExist:
                    pass
        return outbound


class MaterialReturnSerializer(serializers.ModelSerializer):
    material_name    = serializers.CharField(source='material.name',          read_only=True)
    material_code    = serializers.CharField(source='material.code',          read_only=True)
    material_spec    = serializers.CharField(source='material.spec',          read_only=True)
    material_unit    = serializers.CharField(source='material.unit',          read_only=True)
    category_name    = serializers.CharField(source='material.category.name', read_only=True)
    center_name      = serializers.CharField(source='to_center.name',         read_only=True)
    # to_center: 센터 유저는 perform_create에서 자동 설정하므로 required=False
    to_center        = serializers.PrimaryKeyRelatedField(
        queryset=SupportCenter.objects.all(),
        required=False
    )
    received_by_name = serializers.SerializerMethodField()

    def get_received_by_name(self, obj):
        if not obj.received_by:
            return None
        return obj.received_by.name or obj.received_by.username

    class Meta:
        model            = MaterialReturn
        fields           = ['id', 'return_number', 'material', 'material_name',
                             'material_code', 'material_spec', 'material_unit', 'category_name',
                             'quantity', 'from_school', 'to_center', 'center_name',
                             'return_date', 'received_by', 'received_by_name',
                             'handover_person', 'receiver_person',
                             'handover_phone', 'receiver_phone', 'note', 'created_at']
        read_only_fields = ['return_number']

    def create(self, validated_data):
        validated_data['return_number'] = MaterialReturn.generate_number(
            validated_data.get('return_date')
        )
        ret = super().create(validated_data)
        # 센터 재고 증가
        cinv, _ = CenterInventory.objects.get_or_create(
            support_center=ret.to_center,
            material=ret.material,
            defaults={'quantity': 0}
        )
        cinv.quantity += ret.quantity
        cinv.save()
        return ret

    def update(self, instance, validated_data):
        old_qty    = instance.quantity
        old_center = instance.to_center
        ret        = super().update(instance, validated_data)
        new_qty    = ret.quantity
        new_center = ret.to_center
        # 기존 센터 재고 역조정
        if old_center == new_center:
            diff = new_qty - old_qty
            if diff != 0:
                cinv, _ = CenterInventory.objects.get_or_create(
                    support_center=old_center, material=ret.material, defaults={'quantity': 0}
                )
                cinv.quantity = max(0, cinv.quantity + diff)
                cinv.save()
        else:
            # 센터 변경 시: 기존 센터 감소, 새 센터 증가
            try:
                old_cinv = CenterInventory.objects.get(support_center=old_center, material=ret.material)
                old_cinv.quantity = max(0, old_cinv.quantity - old_qty)
                old_cinv.save()
            except CenterInventory.DoesNotExist:
                pass
            new_cinv, _ = CenterInventory.objects.get_or_create(
                support_center=new_center, material=ret.material, defaults={'quantity': 0}
            )
            new_cinv.quantity += new_qty
            new_cinv.save()
        return ret


class MaterialUsageSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    school_name   = serializers.CharField(source='school.name',   read_only=True)
    worker_name   = serializers.CharField(source='worker.name',   read_only=True)

    class Meta:
        model  = MaterialUsage
        fields = '__all__'


class MaterialForecastSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)

    class Meta:
        model  = MaterialForecast
        fields = '__all__'
