from django.core.validators import MinValueValidator
from django.db import models


def local_principal_pk():
    from mesas.models import Local

    local, _ = Local.objects.get_or_create(
        slug="kippu-principal",
        defaults={"nombre": "Kippu Principal", "activo": True},
    )
    return local.pk


class Categoria(models.Model):
    local = models.ForeignKey(
        "mesas.Local",
        on_delete=models.PROTECT,
        related_name="categorias",
        default=local_principal_pk,
    )
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["local__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["local", "nombre"],
                name="carta_local_categoria_unica",
            ),
        ]

    def __str__(self):
        return f"{self.local.nombre} · {self.nombre}"


class Producto(models.Model):
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="productos",
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField("descripción", blank=True)
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(1)],
        help_text="Precio en pesos chilenos, sin decimales.",
    )
    disponible = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio__gte=1),
                name="carta_producto_precio_positivo",
            ),
        ]

    def __str__(self):
        return self.nombre
