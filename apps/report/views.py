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

        report_data = generate_final_report(session)
        if report:
            for key, value in report_data.items():
                setattr(report, key, value)
            report.save()
        else:
            report = FinalReport.objects.create(
                user=request.user,
                session=session,
                overall_score=report_data['overall_score'],
                summary=report_data['summary'],
                strengths=report_data['strengths'],
                weaknesses=report_data['weaknesses'],
                recommendations=report_data['recommendations'],
                question_count=report_data['question_count'],
                answer_count=report_data['answer_count'],
                evaluated_answer_count=report_data['evaluated_answer_count'],
                raw_data=report_data['raw_data'],
            )

        serializer = FinalReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED if not report or force else status.HTTP_200_OK)


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
        reports = FinalReport.objects.filter(user=request.user).order_by('-created_at')
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

    def create_report(self, request, session):
        report_data = generate_final_report(session)
        return FinalReport.objects.create(
            user=request.user,
            session=session,
            overall_score=report_data['overall_score'],
            summary=report_data['summary'],
            strengths=report_data['strengths'],
            weaknesses=report_data['weaknesses'],
            recommendations=report_data['recommendations'],
            question_count=report_data['question_count'],
            answer_count=report_data['answer_count'],
            evaluated_answer_count=report_data['evaluated_answer_count'],
            raw_data=report_data['raw_data'],
        )

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
            report = self.create_report(request, session)

        serializer = FinalReportSessionSerializer(report)
        return Response(serializer.data, status=status.HTTP_200_OK)
