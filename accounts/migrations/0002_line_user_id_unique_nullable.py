from django.db import migrations, models


def blank_to_null(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(line_user_id="").update(line_user_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="line_user_id",
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name="LINE user ID"),
        ),
        migrations.RunPython(blank_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="line_user_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="LINE user ID"),
        ),
    ]
