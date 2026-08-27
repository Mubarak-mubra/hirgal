from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "full_name", "phone_number")


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "full_name", "phone_number", "password")

    def validate_password(self, password):
        validate_password(password)
        return password

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    username_or_phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attributes):
        identifier = attributes["username_or_phone"]
        user = User.objects.filter(username=identifier).first()
        if user is None:
            user = User.objects.filter(phone_number=identifier).first()
        if user is None or not user.check_password(attributes["password"]):
            raise serializers.ValidationError("Magaca isticmaalaha, telefoonka ama furaha sirta ah waa khalad.")
        if not user.is_approved:
            raise serializers.ValidationError("Akoonkaaga wali ma ansixin maamulka.")
        if not user.is_active:
            raise serializers.ValidationError("Akoonkaagu ma shaqaynayo.")
        attributes["user"] = user
        return attributes

    def create_tokens(self, user):
        refresh_token = RefreshToken.for_user(user)
        return {"refresh": str(refresh_token), "access": str(refresh_token.access_token)}
