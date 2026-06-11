from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from apps.interview.models import InterviewSession
from .models import FinalReport
from .serializers import FinalReportSerializer, FinalReportListSerializer, FinalReportSessionSerializer
from .services.report_generator import generate_final_report


class ReportGenerationFailed(RuntimeError):
  pass


def is_failed_report_summary(summary):
  metadata = (summary or {}).get('evaluation_metadata', {})
  answer_count = int(metadata.get('answer_count') or 0)
  evaluated_count = int(metadata.get('evaluated_answer_count') or 0)
  return answer_count > 0 and evaluated_count == 0


def report_generation_failed_response():
  return Response(
      {
          'detail': '리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.',
          'code': 'AI_REPORT_GENERATION_FAILED',
          'error_code': 'AI_REPORT_GENERATION_FAILED',
          'retryable': True,
      },
      status=status.HTTP_503_SERVICE_UNAVAILABLE,
  )


def _get_existing_report(session):
  try:
    return session.final_report
  except (FinalReport.DoesNotExist, AttributeError):
    return None


def _check_evaluation_failure(report):
  """evaluated_answer_count == 0이면서 실제 답변이 존재 -> 평가 실패 판정."""
  summary = report.summary or {}
  metadata = summary.get('evaluation_metadata', {})
  return metadata.get('answer_count', 0) > 0 and metadata.get('evaluated_answer_count', 0) == 0


def _create_report(session):
  with transaction.atomic():
    summary = generate_final_report(session)
    if is_failed_report_summary(summary):
      raise ReportGenerationFailed()
    return FinalReport.objects.create(session=session, summary=summary)


def _build_session_report_response(session):
  """session 객체를 받아 리포트를 조회/생성 후 Response를 반환하는 공통 헬퍼.

  LatestSessionReportView와 SessionFinalReportView가 공유한다.
  session 소유권 검증은 호출부에서 완료된 것으로 가정한다.
  """
  report = _get_existing_report(session)
  if report and _check_evaluation_failure(report):
    report.delete()
    report = None

  if not report:
    try:
      report = _create_report(session)
    except ReportGenerationFailed:
      return report_generation_failed_response()
    except Exception:
      return report_generation_failed_response()

  serializer = FinalReportSessionSerializer(report)
  return Response(serializer.data, status=status.HTTP_200_OK)


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

    if report and is_failed_report_summary(report.summary):
      report.delete()
      report = None

    if report and not force:
      serializer = FinalReportSerializer(report)
      return Response(serializer.data, status=status.HTTP_200_OK)

    try:
      with transaction.atomic():
        summary = generate_final_report(session)
        if is_failed_report_summary(summary):
          raise ReportGenerationFailed()

        is_new = report is None
        if report:
          report.summary = summary
          report.save(update_fields=['summary'])
        else:
          report = FinalReport.objects.create(session=session, summary=summary)
    except ReportGenerationFailed:
      return report_generation_failed_response()
    except Exception:
      return report_generation_failed_response()

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


class LatestSessionReportView(APIView):
  """GET /sessions/latest/report -- 가장 최근 completed 세션의 리포트를 반환."""
  permission_classes = [permissions.IsAuthenticated]

  def get(self, request):
    session = (
        InterviewSession.objects
        .filter(user=request.user, status='completed')
        .order_by('-created_at')
        .first()
    )
    if not session:
      return Response(
          {'detail': 'No completed session found.'},
          status=status.HTTP_404_NOT_FOUND,
      )
    return _build_session_report_response(session)


class SessionFinalReportView(APIView):
  permission_classes = [permissions.IsAuthenticated]

  def get_session(self, session_id):
    try:
      return InterviewSession.objects.get(id=session_id, user=self.request.user)
    except InterviewSession.DoesNotExist:
      return None

  def get(self, request, session_id):
    session = self.get_session(session_id)
    if not session:
      return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    if session.status != 'completed':
      return Response(
          {'detail': 'Report can be generated only after the session is completed.'},
          status=status.HTTP_404_NOT_FOUND,
      )

    return _build_session_report_response(session)
