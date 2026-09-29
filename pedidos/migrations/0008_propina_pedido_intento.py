from decimal import Decimal

from django.db import migrations, models


def completar_subtotales(apps, schema_editor):
    IntentoWebpay = apps.get_model('pedidos', 'IntentoWebpay')
    IntentoWebpay.objects.update(
        subtotal=models.F('monto'),
        propina=Decimal('0'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0007_intentowebpay_cancelacion_solicitada_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='propina',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='intentowebpay',
            name='subtotal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='intentowebpay',
            name='propina',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(completar_subtotales, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='pedido',
            constraint=models.CheckConstraint(
                condition=models.Q(propina__gte=0),
                name='pedido_propina_no_negativa',
            ),
        ),
        migrations.AddConstraint(
            model_name='intentowebpay',
            constraint=models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name='intento_subtotal_no_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='intentowebpay',
            constraint=models.CheckConstraint(
                condition=models.Q(propina__gte=0),
                name='intento_propina_no_negativa',
            ),
        ),
    ]
