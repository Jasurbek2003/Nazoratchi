from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer[None]):
    login = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class MeUpdateSerializer(serializers.Serializer[None]):
    language = serializers.ChoiceField(choices=User.Language.choices, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    current_password = serializers.CharField(max_length=128, required=False, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, required=False, trim_whitespace=False)

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError(
                "Vaqt zonasi noto'g'ri (masalan, Asia/Tashkent)."
            ) from exc
        return value

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        if ("new_password" in attrs) != ("current_password" in attrs):
            raise serializers.ValidationError(
                "Parolni almashtirish uchun current_password va new_password kerak."
            )
        return attrs
