from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carta', '0003_producto_requiere_mayoria_edad'),
        ('pedidos', '0008_propina_pedido_intento'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='mayoria_edad_confirmada',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='detallepedido',
            name='requiere_mayoria_edad',
            field=models.BooleanField(default=False),
        ),
    ]
