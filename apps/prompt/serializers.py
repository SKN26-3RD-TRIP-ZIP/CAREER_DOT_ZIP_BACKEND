from rest_framework import serializers

from .models import PersonaConfig, PromptTemplate, PromptVersion


class PersonaConfigSerializer(serializers.ModelSerializer):
    persona_id = serializers.IntegerField(source='id', read_only=True)
    active_template_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PersonaConfig
        fields = (
            'persona_id',
            'persona_type',
            'description',
            'active_template_id',
            'is_active',
            'created_at',
            'updated_at',
        )


class PersonaActiveTemplateSerializer(serializers.Serializer):
    active_template_id = serializers.PrimaryKeyRelatedField(
        queryset=PromptTemplate.objects.filter(is_active=True),
        allow_null=True,
    )

    def validate_active_template_id(self, value):
        if value is not None and value.persona_config_id != self.context['persona'].id:
            raise serializers.ValidationError('Template does not belong to this persona.')
        return value


class PromptTemplateCreateSerializer(serializers.ModelSerializer):
    persona_config_id = serializers.PrimaryKeyRelatedField(
        queryset=PersonaConfig.objects.all(),
        source='persona_config',
    )

    class Meta:
        model = PromptTemplate
        fields = ('persona_config_id', 'title', 'prompt_type')


class PromptTemplateSerializer(serializers.ModelSerializer):
    template_id = serializers.IntegerField(source='id', read_only=True)
    persona_config_id = serializers.IntegerField(read_only=True)
    persona_type = serializers.CharField(source='persona_config.persona_type', read_only=True)
    default_version_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PromptTemplate
        fields = (
            'template_id',
            'persona_config_id',
            'persona_type',
            'title',
            'prompt_type',
            'default_version_id',
            'created_at',
        )


class PromptVersionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = ('content', 'change_note')
        extra_kwargs = {'change_note': {'required': False}}


class PromptVersionSerializer(serializers.ModelSerializer):
    prompt_ver_id = serializers.IntegerField(source='id', read_only=True)
    template_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PromptVersion
        fields = (
            'prompt_ver_id',
            'template_id',
            'version_number',
            'content',
            'change_note',
            'created_at',
        )


class PromptDefaultVersionSerializer(serializers.Serializer):
    default_version_id = serializers.PrimaryKeyRelatedField(
        queryset=PromptVersion.objects.all(),
        source='default_version',
    )

    def validate_default_version_id(self, value):
        if value.template_id != self.context['template'].id:
            raise serializers.ValidationError('Version does not belong to this template.')
        return value
