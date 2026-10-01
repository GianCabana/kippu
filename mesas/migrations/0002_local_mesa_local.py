from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import mesas.models


def asignar_local_principal(apps, schema_editor):
    Local = apps.get_model("mesas", "Local")
    Mesa = apps.get_model("mesas", "Mesa")
    local = Local.objects.create(
        nombre="Kippu Principal",
        slug="kippu-principal",
        activo=True,
    )
    Mesa.objects.filter(local__isnull=True).update(local=local)


class Migration(migrations.Migration):
    dependencies = [
        ("mesas", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Local",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("activo", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "local",
                "verbose_name_plural": "locales",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="mesa",
            name="local",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mesas",
                to="mesas.local",
            ),
        ),
        migrations.RunPython(asignar_local_principal, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="mesa",
            name="numero",
            field=models.PositiveSmallIntegerField(
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AlterField(
            model_name="mesa",
            name="local",
            field=models.ForeignKey(
                default=mesas.models.local_principal_pk,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mesas",
                to="mesas.local",
            ),
        ),
        migrations.AlterModelOptions(
            name="mesa",
            options={"ordering": ["local__nombre", "numero"]},
        ),
        migrations.AddConstraint(
            model_name="mesa",
            constraint=models.UniqueConstraint(
                fields=("local", "numero"),
                name="mesas_local_numero_unico",
            ),
        ),
    ]
