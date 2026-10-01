from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carta', '0002_categoria_local'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='requiere_mayoria_edad',
            field=models.BooleanField(
                default=False,
                help_text='Marca esta opción para alcohol u otros productos exclusivos para mayores de 18 años.',
                verbose_name='requiere mayoría de edad',
            ),
        ),
    ]
