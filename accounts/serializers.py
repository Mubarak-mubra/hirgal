from django.contrib.auth import authenticate
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "phone_number", "full_name", "is_active", "is_approved", "is_staff", "date_joined"]
        read_only_fields = ["id", "is_active", "is_approved", "is_staff", "date_joined"]


class RegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    phone_number = serializers.CharField(max_length=20)
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username-kan waa la isticmaalay.")
        return value

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Telefoonkan waa la isticmaalay.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
        )


class LoginSerializer(serializers.Serializer):
    username_or_phone = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = attrs.get("username_or_phone") or attrs.get("username")
        password = attrs.get("password")

        if not identifier or not password:
            raise serializers.ValidationError("Magaca/Telefoonka iyo furaha sirta ah waa loo baahan yahay.")

        user = User.objects.filter(Q(username=identifier) | Q(phone_number=identifier)).first()
        if not user or not user.check_password(password):
            raise serializers.ValidationError("Magaca ama furaha sirta ah ma saxna.")
        if not user.is_approved:
            raise serializers.ValidationError("Koontadaadu wali ma ansixin maamulaha.")

        attrs["user"] = user
        return attrs

    def create_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
