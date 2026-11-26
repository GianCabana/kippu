from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

PESO_MAXIMO_IMAGEN = 2 * 1024 * 1024


def ruta_imagen_producto(producto, archivo):
    # Una carpeta por local. La migración 0005 usa este nombre: no renombrarla.
    return f"productos/{producto.categoria.local.slug}/{archivo}"


def validar_peso_imagen(archivo):
    if archivo.size > PESO_MAXIMO_IMAGEN:
        raise ValidationError("La imagen no puede pesar más de 2 MB.")


def local_principal_pk():
    # La migración carta/0002 usa este nombre; la lógica vive en mesas.
    from mesas.models import local_principal_pk as principal

    return principal()


class Categoria(models.Model):
    local = models.ForeignKey(
        "mesas.Local",
        on_delete=models.PROTECT,
        related_name="categorias",
        default=local_principal_pk,
    )
    nombre = models.CharField(max_length=100)
    nombre_en = models.CharField("nombre en inglés", max_length=100, blank=True, help_text="Opcional. Si queda vacío, en inglés se muestra el texto en español.")
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
    nombre_en = models.CharField("nombre en inglés", max_length=150, blank=True, help_text="Opcional. Si queda vacío, en inglés se muestra el texto en español.")
    descripcion_en = models.TextField("descripción en inglés", blank=True, help_text="Opcional. Si queda vacío, en inglés se muestra el texto en español.")
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(1)],
        help_text="Precio en pesos chilenos, sin decimales.",
    )
    disponible = models.BooleanField(default=True)
    requiere_mayoria_edad = models.BooleanField(
        "requiere mayoría de edad",
        default=False,
        help_text="Marca esta opción para alcohol u otros productos exclusivos para mayores de 18 años.",
    )
    imagen = models.ImageField(
        "imagen",
        upload_to=ruta_imagen_producto,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validar_peso_imagen],
        help_text="JPG, PNG o WebP de hasta 2 MB. Ideal: WebP de unos 800 px de ancho.",
    )

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


class DiaDestacado(models.Model):
    """Días de la semana en que un producto sale en "Destacado de hoy" arriba de la carta (fase 3)."""

    class Dia(models.IntegerChoices):
        # Mismo número que date.weekday(): lunes = 0.
        LUNES = 0, _("Lunes")
        MARTES = 1, _("Martes")
        MIERCOLES = 2, _("Miércoles")
        JUEVES = 3, _("Jueves")
        VIERNES = 4, _("Viernes")
        SABADO = 5, _("Sábado")
        DOMINGO = 6, _("Domingo")

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="dias_destacado",
    )
    dia = models.PositiveSmallIntegerField("día", choices=Dia.choices)

    class Meta:
        verbose_name = "día destacado"
        verbose_name_plural = "días destacados"
        ordering = ["dia", "producto__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "dia"],
                name="carta_destacado_dia_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(dia__lte=6),
                name="carta_destacado_dia_valido",
            ),
        ]

    def __str__(self):
        return f"{self.get_dia_display()} · {self.producto.nombre}"


class GrupoOpcion(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="grupos_opciones",
    )
    nombre = models.CharField(max_length=100)
    nombre_en = models.CharField("nombre en inglés", max_length=100, blank=True, help_text="Opcional. Si queda vacío, en inglés se muestra el texto en español.")
    requerido = models.BooleanField(default=False)
    seleccion_multiple = models.BooleanField(
        "permite varias opciones",
        default=False,
    )
    max_selecciones = models.PositiveSmallIntegerField(
        "máximo de selecciones",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "grupo de opciones"
        verbose_name_plural = "grupos de opciones"
        ordering = ["orden", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "nombre"],
                name="carta_grupo_nombre_unico_producto",
            ),
            models.CheckConstraint(
                condition=models.Q(max_selecciones__gte=1),
                name="carta_grupo_max_selecciones_positivo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(seleccion_multiple=True)
                    | models.Q(max_selecciones=1)
                ),
                name="carta_grupo_simple_maximo_uno",
            ),
        ]

    def __str__(self):
        return f"{self.producto.nombre} · {self.nombre}"


class OpcionProducto(models.Model):
    grupo = models.ForeignKey(
        GrupoOpcion,
        on_delete=models.CASCADE,
        related_name="opciones",
    )
    nombre = models.CharField(max_length=100)
    nombre_en = models.CharField("nombre en inglés", max_length=100, blank=True, help_text="Opcional. Si queda vacío, en inglés se muestra el texto en español.")
    precio_extra = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Recargo en pesos chilenos. Usa 0 si no cambia el precio.",
    )
    activa = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "opción de producto"
        verbose_name_plural = "opciones de productos"
        ordering = ["orden", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["grupo", "nombre"],
                name="carta_opcion_nombre_unico_grupo",
            ),
            models.CheckConstraint(
                condition=models.Q(precio_extra__gte=0),
                name="carta_opcion_precio_extra_no_negativo",
            ),
        ]

    def __str__(self):
        return f"{self.grupo.nombre} · {self.nombre}"
