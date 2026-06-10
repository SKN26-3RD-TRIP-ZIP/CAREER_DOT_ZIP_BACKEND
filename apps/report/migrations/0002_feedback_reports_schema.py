from django.db import migrations, models


def migrate_legacy_report_data(apps, schema_editor):
  FinalReport = apps.get_model('report', 'FinalReport')
  for report in FinalReport.objects.all():
    raw = report.raw_data or {}
    if isinstance(raw.get('summary'), dict):
      report.summary_json = raw['summary']
    else:
      report.summary_json = {
        'evaluation_metadata': {
          'session_id': str(report.session_id),
          'question_count': report.question_count,
          'answer_count': report.answer_count,
          'evaluated_answer_count': report.evaluated_answer_count,
        },
        'score_summary': {
          'overall_score': report.overall_score,
          'metrics': {},
        },
        'score_detail': {
          'strength': report.strengths or [],
          'weakness': report.weaknesses or [],
          'improvement': report.recommendations or [],
        },
        'dynamically_triggered_tags': {
          'strength_tags': report.strengths or [],
          'weakness_tags': report.weaknesses or [],
        },
      }
    report.save(update_fields=['summary_json'])


class Migration(migrations.Migration):

  dependencies = [
      ('report', '0001_initial'),
  ]

  operations = [
      migrations.AddField(
          model_name='finalreport',
          name='summary_json',
          field=models.JSONField(default=dict),
      ),
      migrations.RunPython(migrate_legacy_report_data, migrations.RunPython.noop),
      migrations.RemoveField(model_name='finalreport', name='summary'),
      migrations.RenameField(
          model_name='finalreport',
          old_name='summary_json',
          new_name='summary',
      ),
      migrations.RemoveField(model_name='finalreport', name='user'),
      migrations.RemoveField(model_name='finalreport', name='overall_score'),
      migrations.RemoveField(model_name='finalreport', name='strengths'),
      migrations.RemoveField(model_name='finalreport', name='weaknesses'),
      migrations.RemoveField(model_name='finalreport', name='recommendations'),
      migrations.RemoveField(model_name='finalreport', name='question_count'),
      migrations.RemoveField(model_name='finalreport', name='answer_count'),
      migrations.RemoveField(model_name='finalreport', name='evaluated_answer_count'),
      migrations.RemoveField(model_name='finalreport', name='raw_data'),
      migrations.RemoveField(model_name='finalreport', name='updated_at'),
      migrations.RenameField(
          model_name='finalreport',
          old_name='created_at',
          new_name='generated_at',
      ),
      migrations.AlterModelTable(
          name='finalreport',
          table='feedback_reports',
      ),
  ]
