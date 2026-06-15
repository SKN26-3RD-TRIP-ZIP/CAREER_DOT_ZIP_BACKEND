from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import PersonaConfig, PromptTemplate
from .permissions import IsPromptAdmin
from .serializers import (
    PersonaActiveTemplateSerializer,
    PersonaConfigSerializer,
    PromptDefaultVersionSerializer,
    PromptTemplateCreateSerializer,
    PromptTemplateSerializer,
    PromptVersionCreateSerializer,
    PromptVersionSerializer,
)


class PromptAdminAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPromptAdmin]


class PersonaListView(PromptAdminAPIView):
    def get(self, request):
        personas = PersonaConfig.objects.select_related('active_template').all()
        serializer = PersonaConfigSerializer(personas, many=True)
        return Response({'total': personas.count(), 'results': serializer.data})


class PersonaActiveTemplateView(PromptAdminAPIView):
    def patch(self, request, persona_id):
        persona = get_object_or_404(PersonaConfig, id=persona_id)
        serializer = PersonaActiveTemplateSerializer(
            data=request.data,
            context={'persona': persona},
        )
        serializer.is_valid(raise_exception=True)
        persona.active_template = serializer.validated_data['active_template_id']
        persona.save(update_fields=('active_template', 'updated_at'))
        return Response(
            {
                'persona_id': persona.id,
                'active_template_id': persona.active_template_id,
                'updated_at': persona.updated_at,
            }
        )


class PromptTemplateListCreateView(PromptAdminAPIView):
    def get(self, request):
        templates = PromptTemplate.objects.filter(is_active=True).select_related(
            'persona_config',
            'default_version',
        ).annotate(version_count=Count('versions'))
        persona_type = request.query_params.get('persona_type')
        prompt_type = request.query_params.get('prompt_type')
        if persona_type:
            templates = templates.filter(persona_config__persona_type=persona_type)
        if prompt_type:
            templates = templates.filter(prompt_type=prompt_type)

        serializer = PromptTemplateSerializer(templates, many=True)
        return Response({'total': templates.count(), 'results': serializer.data})

    def post(self, request):
        serializer = PromptTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(
            PromptTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )


class PromptTemplateDeleteView(PromptAdminAPIView):
    def delete(self, request, template_id):
        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)
        if template.active_personas.exists():
            return Response(
                {'detail': 'Active persona template cannot be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        template.is_active = False
        template.save(update_fields=('is_active', 'updated_at'))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromptVersionListCreateView(PromptAdminAPIView):
    def get_template(self, template_id):
        return get_object_or_404(PromptTemplate, id=template_id, is_active=True)

    def get(self, request, template_id):
        template = self.get_template(template_id)
        versions = template.versions.order_by('-version_number')
        serializer = PromptVersionSerializer(versions, many=True)
        return Response({'total': versions.count(), 'results': serializer.data})

    def post(self, request, template_id):
        serializer = PromptVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            template = get_object_or_404(
                PromptTemplate.objects.select_for_update(),
                id=template_id,
                is_active=True,
            )
            last_version = template.versions.aggregate(
                number=Max('version_number')
            )['number']
            version = serializer.save(
                template=template,
                version_number=(last_version or 0) + 1,
                created_by=request.user,
            )
            if template.default_version_id is None:
                template.default_version = version
                template.save(update_fields=('default_version', 'updated_at'))

        return Response(
            PromptVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )


class PromptDefaultVersionView(PromptAdminAPIView):
    def patch(self, request, template_id):
        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)
        serializer = PromptDefaultVersionSerializer(
            data=request.data,
            context={'template': template},
        )
        serializer.is_valid(raise_exception=True)
        template.default_version = serializer.validated_data['default_version']
        template.save(update_fields=('default_version', 'updated_at'))
        return Response(
            {
                'template_id': template.id,
                'default_version_id': template.default_version_id,
                'updated_at': template.updated_at,
            }
        )
