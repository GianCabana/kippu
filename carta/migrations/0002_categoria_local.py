from django.db import migrations, models
import carta.models
import django.db.models.deletion


def asignar_local_principal(apps, schema_editor):
    Local = apps.get_model("mesas", "Local")
    Categoria = apps.get_model("carta", "Categoria")
    local = Local.objects.get(slug="kippu-principal")
    Categoria.objects.filter(local__isnull=True).update(local=local)


class Migration(migrations.Migration):
    dependencies = [
        ("mesas", "0002_local_mesa_local"),
        ("carta", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="local",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="categorias",
                to="mesas.local",
            ),
        ),
        migrations.RunPython(asignar_local_principal, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="categoria",
            name="nombre",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="categoria",
            name="local",
            field=models.ForeignKey(
                default=carta.models.local_principal_pk,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="categorias",
                to="mesas.local",
            ),
        ),
        migrations.AlterModelOptions(
            name="categoria",
            options={
                "ordering": ["local__nombre", "nombre"],
                "verbose_name": "categoría",
                "verbose_name_plural": "categorías",
            },
        ),
        migrations.AddConstraint(
            model_name="categoria",
            constraint=models.UniqueConstraint(
                fields=("local", "nombre"),
                name="carta_local_categoria_unica",
            ),
        ),
    ]
