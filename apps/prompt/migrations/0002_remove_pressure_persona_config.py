from django.db import migrations, models


def delete_pressure_persona_config(apps, schema_editor):
    PersonaConfig = apps.get_model('prompt', 'PersonaConfig')
    PersonaConfig.objects.filter(persona_type='pressure').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('prompt', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(delete_pressure_persona_config, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='personaconfig',
            name='persona_type',
            field=models.CharField(
                choices=[
                    ('coach', '코치형'),
                    ('practical', '실무형'),
                    ('verifier', '검증형'),
                ],
                max_length=30,
                unique=True,
            ),
        ),
    ]
