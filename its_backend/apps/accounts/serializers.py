from django.contrib import auth
from rest_framework import serializers

from its_backend.apps.accounts.models import CustomUser


class SignUpSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "password",
            "organisation",
            "username",
            "is_student",
            "is_tutor",
            "is_manager",
        ]

    def create(self, validated_data):
        return CustomUser.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        instance.is_student = validated_data.get("is_student", instance.is_student)
        instance.is_tutor = validated_data.get("is_tutor", instance.is_tutor)
        instance.save()
        return instance


class SignInSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "password",
            "organisation",
            "username",
            "is_student",
            "is_tutor",
            "is_manager",
        ]

    def validate(self, data):
        email = data.get("email", None)
        password = data.get("password", None)

        user = auth.authenticate(username=email, password=password)

        if user is None:
            raise serializers.ValidationError(
                "A user with this email and password does not exist."
            )

        return user


class SocialCallbackSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "organisation",
            "username",
            "is_student",
            "is_tutor",
            "is_manager",
        ]


class RetrieveUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "organisation",
            "username",
            "is_student",
            "is_tutor",
            "is_manager",
        ]


class UpdateUserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "organisation",
            "username",
            "is_student",
            "is_tutor",
            "is_manager",
        ]

    def update(self, instance, validated_data):
        fields = ["username", "organisation"]
        for field in fields:
            try:
                setattr(instance, field, validated_data[field])
            except KeyError:
                pass
        instance.save()
        return instance
