from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('question_bank', '0002_remove_questionbankitem_unique_question_bank_source_file_text_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionbankitem',
            name='is_embedded',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
