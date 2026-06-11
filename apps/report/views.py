from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.interview.models import InterviewSession
from .models import FinalReport
from .serializers import FinalReportSerializer, FinalReportListSerializer, FinalReportSessionSerializer
from .services.report_generator import generate_final_report


class FinalReportGenerateView(APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get_session(self, session_id):
    try:
      return InterviewSession.objects.get(id=session_id, user=self.request.user)
    except InterviewSession.DoesNotExist:
      return None

  def post(self, request, session_id):
    session = self.get_session(session_id)
    if not session:
      return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    force = request.data.get('force_regenerate', False)
    try:
      report = session.final_report
    except FinalReport.DoesNotExist:
      report = None

    if report and not force:
      serializer = FinalReportSerializer(report)
      return Response(serializer.data, status=status.HTTP_200_OK)

    summary = generate_final_report(session)
    is_new = report is None
    if report:
      report.summary = summary
      report.save(update_fields=['summary'])
    else:
      report = FinalReport.objects.create(session=session, summary=summary)

    serializer = FinalReportSerializer(report)
    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
    )


class FinalReportDetailView(APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get_report(self, session_id):
    try:
      session = InterviewSession.objects.get(id=session_id, user=self.request.user)
      return session.final_report
    except (InterviewSession.DoesNotExist, FinalReport.DoesNotExist, AttributeError):
      return None

  def get(self, request, session_id):
    report = self.get_report(session_id)
    if not report:
      return Response({'detail': 'Report not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = FinalReportSerializer(report)
    return Response(serializer.data, status=status.HTTP_200_OK)


class FinalReportListView(APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request):
    reports = (
        FinalReport.objects
        .filter(session__user=request.user)
        .select_related('session')
        .order_by('-generated_at')
    )
    serializer = FinalReportListSerializer(reports, many=True)
    return Response({'total': reports.count(), 'results': serializer.data}, status=status.HTTP_200_OK)


class SessionFinalReportView(APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get_session(self, session_id):
    try:
      return InterviewSession.objects.get(id=session_id, user=self.request.user)
    except InterviewSession.DoesNotExist:
      return None

  def get_existing_report(self, session):
    try:
      return session.final_report
    except (FinalReport.DoesNotExist, AttributeError):
      return None

  def create_report(self, session):
    return FinalReport.objects.create(
        session=session,
        summary=generate_final_report(session),
    )

  def _check_evaluation_failure(self, report, session):
    """평가 실패를 감지한다.

    evaluated_answer_count == 0이면서 실제 답변이 존재하는 경우,
    OpenAI 호출이 real mode에서 전부 실패한 것으로 판단한다.
    (mock mode에서는 0점 fallback이 반환되므로 evaluated_answer_count > 0)
    """
    summary = report.summary or {}
    metadata = summary.get("evaluation_metadata", {})
    evaluated = metadata.get("evaluated_answer_count", 0)
    answer_count = metadata.get("answer_count", 0)
    return answer_count > 0 and evaluated == 0

  def get(self, request, session_id):
    session = self.get_session(session_id)
    if not session:
      return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    if session.status != 'completed':
      return Response(
          {'detail': 'Report can be generated only after the session is completed.'},
          status=status.HTTP_404_NOT_FOUND,
      )

    report = self.get_existing_report(session)
    if not report:
      report = self.create_report(session)
    elif self._check_evaluation_failure(report, session):
      # 이전 요청에서 평가가 전부 실패한 채 리포트가 저장된 경우.
      # Evaluation row가 없으므로 evaluate_session_answers는 멱등하게 재시도한다.
      new_summary = generate_final_report(session)
      report.summary = new_summary
      report.save(update_fields=['summary'])

    if self._check_evaluation_failure(report, session):
      return Response(
          {
              'error': 'evaluation_failed',
              'detail': 'AI 평가 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
          },
          status=status.HTTP_503_SERVICE_UNAVAILABLE,
      )

    serializer = FinalReportSessionSerializer(report)
    return Response(serializer.data, status=status.HTTP_200_OK)
