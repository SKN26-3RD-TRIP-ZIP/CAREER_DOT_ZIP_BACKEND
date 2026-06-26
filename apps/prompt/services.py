from dataclasses import dataclass

from .models import PersonaConfig, PromptTemplate, PromptVersion


PERSONA_TYPE_ALIASES = {
    'friendly': 'coach',
    'coach': 'coach',
    'coaching': 'coach',
    'practical': 'practical',
    'verify': 'verifier',
    'verifier': 'verifier',
}


@dataclass(frozen=True)
class RuntimePrompt:
    content: str
    version_id: int
    prompt_type: str | None = None
    template_id: int | None = None
    template_title: str | None = None
    version_number: int | None = None
    version_label: str | None = None
    is_active_version: bool = False


def _runtime_prompt_from_version(version) -> RuntimePrompt:
    template = version.template
    return RuntimePrompt(
        content=version.content,
        version_id=version.id,
        prompt_type=template.prompt_type,
        template_id=template.id,
        template_title=template.title,
        version_number=version.version_number,
        version_label=f'v{version.version_number}',
        is_active_version=(
            template.is_active and template.default_version_id == version.id
        ),
    )


def normalize_prompt_persona_type(persona_type):
    normalized = str(persona_type or '').strip().lower()
    return PERSONA_TYPE_ALIASES.get(normalized, normalized)


def get_runtime_prompt_version(persona_type, prompt_type) -> RuntimePrompt | None:
    persona_type = normalize_prompt_persona_type(persona_type)
    if not persona_type or not prompt_type:
        return None

    persona = (
        PersonaConfig.objects.filter(
            persona_type=persona_type,
            is_active=True,
        )
        .select_related('active_template__default_version')
        .first()
    )
    if persona is None:
        return None

    active_template = persona.active_template
    if (
        active_template is not None
        and active_template.is_active
        and active_template.prompt_type == prompt_type
        and active_template.default_version_id
    ):
        version = active_template.default_version
        version.template = active_template
        return _runtime_prompt_from_version(version)

    template = (
        PromptTemplate.objects.filter(
            persona_config=persona,
            prompt_type=prompt_type,
            is_active=True,
            default_version_id__isnull=False,
        )
        .select_related('default_version')
        .order_by('-updated_at', '-created_at')
        .first()
    )
    if template is None:
        return None

    version = template.default_version
    version.template = template
    return _runtime_prompt_from_version(version)


def get_runtime_prompt_version_by_id(
    prompt_version_id,
    persona_type=None,
    prompt_type=None,
) -> RuntimePrompt | None:
    if not prompt_version_id:
        return None

    persona_type = normalize_prompt_persona_type(persona_type)
    version = (
        PromptVersion.objects.filter(id=prompt_version_id)
        .select_related('template__persona_config')
        .first()
    )
    if version is None:
        return None

    template = version.template
    if not template.is_active:
        return None
    if prompt_type and template.prompt_type != prompt_type:
        return None
    version_persona_type = normalize_prompt_persona_type(
        template.persona_config.persona_type
    )
    if persona_type and version_persona_type != persona_type:
        return None

    return _runtime_prompt_from_version(version)
