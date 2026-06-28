from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import TermsAgreement
from apps.accounts.services.terms import required_terms_reconsent_status, set_marketing_consent


class TermsAgreementSerializer(serializers.ModelSerializer):
    terms_agreement_id = serializers.IntegerField(source='id', read_only=True)

    class Meta:
        model = TermsAgreement
        fields = (
            'terms_agreement_id',
            'kind',
            'version',
            'is_required',
            'agreed',
            'agreed_at',
            'withdrawn_at',
            'source',
            'created_at',
        )


class MarketingConsentSerializer(serializers.Serializer):
    agreed = serializers.BooleanField()
    version = serializers.CharField(required=False, allow_blank=True, max_length=50)


def _page_params(request):
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.query_params.get('size', 20))
    except (TypeError, ValueError):
        size = 20
    return max(page, 1), min(max(size, 1), 100)


class MyTermsAgreementListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        page, size = _page_params(request)
        queryset = TermsAgreement.objects.filter(user=request.user).order_by('-created_at', '-id')
        total = queryset.count()
        offset = (page - 1) * size
        serializer = TermsAgreementSerializer(queryset[offset:offset + size], many=True)
        return Response(
            {
                'total': total,
                'page': page,
                'size': size,
                'required_reconsent': required_terms_reconsent_status(request.user),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class MarketingConsentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = MarketingConsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agreement = set_marketing_consent(
            user=request.user,
            agreed=serializer.validated_data['agreed'],
            version=serializer.validated_data.get('version') or None,
            request=request,
        )
        return Response(TermsAgreementSerializer(agreement).data, status=status.HTTP_200_OK)
