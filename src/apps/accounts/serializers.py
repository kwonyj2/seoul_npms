from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from .models import User, UserSession


class UserListSerializer(serializers.ModelSerializer):
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'email', 'phone', 'role', 'role_display',
                  'support_center', 'support_center_name', 'is_active', 'service_expiry',
                  'profile_image', 'created_at']


class UserDetailSerializer(serializers.ModelSerializer):
    support_center_name = serializers.CharField(source='support_center.name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    is_service_active = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'email', 'phone', 'role', 'role_display',
                  'support_center', 'support_center_name', 'home_address', 'home_lat', 'home_lng',
                  'profile_image', 'service_expiry', 'is_active', 'is_service_active',
                  'created_at', 'updated_at']

    def get_is_service_active(self, obj):
        return obj.is_service_active()


class UserCreateSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'name', 'phone', 'role', 'support_center',
                  'home_address', 'home_lat', 'home_lng', 'service_expiry', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': '비밀번호가 일치하지 않습니다.'})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['name', 'email', 'phone', 'role', 'support_center',
                  'home_address', 'home_lat', 'home_lng', 'service_expiry',
                  'is_active', 'profile_image']


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('현재 비밀번호가 올바르지 않습니다.')
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not user.is_service_active():
            raise serializers.ValidationError('서비스 이용 기간이 만료되었습니다. 관리자에게 문의하세요.')
        data['user'] = UserDetailSerializer(user).data
        return data


class UserSessionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)
    role_display = serializers.CharField(source='user.get_role_display', read_only=True)

    class Meta:
        model = UserSession
        fields = ['id', 'user', 'user_name', 'role_display', 'ip_address',
                  'current_page', 'login_at', 'last_active', 'is_active']
