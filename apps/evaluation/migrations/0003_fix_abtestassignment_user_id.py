# Manual migration - 2026-06-16
# ABTestAssignment.user_id UUIDField -> BigIntegerField
# User.id is BigAutoField(int); UUIDField was wrong in 0002.
# RemoveConstraint + AlterUniqueTogether already done in 0003_align_e7_eval_fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0003_align_e7_eval_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='abtestassignment',
            name='user_id',
            field=models.BigIntegerField(db_index=True),
        ),
    ]
