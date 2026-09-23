import uuid
from django.urls import reverse
from django.core.validators import MinValueValidator
from django.db import models


class Mesa(models.Model):
    numero = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
    )
    activa = models.BooleanField(default=True)
    codigo = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    class Meta:
        ordering = ["numero"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(numero__gte=1),
                name="mesas_numero_positivo",
            ),
        ]        
    def __str__(self):
        return f"Mesa {self.numero}"

    def get_absolute_url(self):
        return reverse(
            "carta:por_mesa",
            kwargs={"codigo": self.codigo},
        )