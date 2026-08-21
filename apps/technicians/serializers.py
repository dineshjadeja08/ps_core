from rest_framework import serializers

from apps.technicians.models import TechnicianAssignment, TechnicianProfile, TechnicianSkill


class TechnicianSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicianSkill
        fields = ("id", "name", "description")


class TechnicianProfileSerializer(serializers.ModelSerializer):
    skills = TechnicianSkillSerializer(many=True, read_only=True)
    service_areas = serializers.SerializerMethodField()

    class Meta:
        model = TechnicianProfile
        fields = (
            "id",
            "employee_code",
            "display_name",
            "phone",
            "skills",
            "service_areas",
            "is_available",
            "is_active",
            "joined_at",
        )

    def get_service_areas(self, obj):
        return [
            {
                "id": str(area.id),
                "name": area.name,
                "postal_code": area.postal_code,
                "city": area.city,
            }
            for area in obj.service_areas.all()
        ]


class AssignTechnicianRequestSerializer(serializers.Serializer):
    technician_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)


class TechnicianAssignmentSerializer(serializers.ModelSerializer):
    technician = TechnicianProfileSerializer(read_only=True)

    class Meta:
        model = TechnicianAssignment
        fields = ("id", "booking", "technician", "assigned_by", "assigned_at", "unassigned_at", "notes")
        read_only_fields = fields
