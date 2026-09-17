from django.core.validators import MinValueValidator
from django.db import models


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


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