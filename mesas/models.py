import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class Local(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "local"
        verbose_name_plural = "locales"

    def __str__(self):
        return self.nombre


def local_principal_pk():
    local, _ = Local.objects.get_or_create(
        slug="kippu-principal",
        defaults={"nombre": "Kippu Principal", "activo": True},
    )
    return local.pk


class Mesa(models.Model):
    local = models.ForeignKey(
        Local,
        on_delete=models.PROTECT,
        related_name="mesas",
        default=local_principal_pk,
    )
    numero = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
    )
    activa = models.BooleanField(default=True)
    codigo = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    class Meta:
        ordering = ["local__nombre", "numero"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(numero__gte=1),
                name="mesas_numero_positivo",
            ),
            models.UniqueConstraint(
                fields=["local", "numero"],
                name="mesas_local_numero_unico",
            ),
        ]

    def __str__(self):
        return f"{self.local.nombre} · Mesa {self.numero}"

    def get_absolute_url(self):
        return reverse(
            "carta:por_mesa",
            kwargs={"codigo": self.codigo},
        )
