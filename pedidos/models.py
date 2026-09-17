from django.db import models
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.conf import settings


class Pedido(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_PREPARACION = "en_preparacion", "En preparación"
        LISTO = "listo", "Listo"
        ENTREGADO = "entregado", "Entregado"
        CANCELADO = "cancelado", "Cancelado"

    mesa = models.ForeignKey(
        "mesas.Mesa",
        on_delete=models.PROTECT,
        related_name="pedidos",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    cuenta = models.ForeignKey(
        "Cuenta",
        on_delete=models.PROTECT,
        related_name="pedidos",
        null=True,
        blank=True,
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"Pedido #{self.pk} - Mesa {self.mesa.numero}"


class DetallePedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        "carta.Producto",
        on_delete=models.PROTECT,
        related_name="detalles_pedido",
    )
    nombre_producto = models.CharField(max_length=255)
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    cantidad = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    def __str__(self):
        return f"{self.cantidad} × {self.nombre_producto}"

    @staff_member_required
    def cocina(request):
        pedidos = (
        Pedido.objects.filter(
            estado__in=[
                Pedido.Estado.PENDIENTE,
                Pedido.Estado.EN_PREPARACION,
            ]
        )
        .select_related("mesa")
        .prefetch_related("detalles")
        .order_by("creado", "pk")
    )

        return render(
        request,
        "pedidos/cocina.html",
        {"pedidos": pedidos},
    )
class Cuenta(models.Model):
    class Estado(models.TextChoices):
            ABIERTA = "abierta", "Abierta"
            CERRADA = "cerrada", "Cerrada"

    mesa = models.ForeignKey(
        "mesas.Mesa",
        on_delete=models.PROTECT,
        related_name="cuentas",
    )
    estado = models.CharField(
        max_length=10,
        choices= Estado.choices,
        default= Estado.ABIERTA,
    )
    creada = models.DateTimeField(auto_now_add=True)
    cerrada = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-creada"]
        constraints = [
            models.UniqueConstraint(
                fields=["mesa"],
                condition=models.Q(estado="abierta"),
                name="una_cuenta_abierta_por_mesa",
            ),
        ]

    def __str__(self):
        return f"Cuenta #{self.pk} - Mesa {self.mesa.numero}"

    class Pago(models.Model):
        class Metodo(models.TextChoices):
            EFECTIVO = "efectivo", "Efectivo"
            DEBITO = "debito", "Tarjeta de débito"
            CREDITO = "credito", "Tarjeta de crédito"
            TRANSFERENCIA = "transferencia", "Transferencia"

        cuenta = models.OneToOneField(
            "Cuenta",
            on_delete=models.PROTECT,
            related_name="pago",
        )
        monto = models.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
        metodo = models.CharField(
            max_length=20,
            choices=Metodo.choices,
        )
        registrado_por = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.PROTECT,
            related_name="pagos_registrados",
        )
        creado = models.DateTimeField(auto_now_add=True)

        class Meta:
            ordering = ["-creado"]
            constraints = [
                models.CheckConstraint(
                    condition=models.Q(monto__gt=0),
                    name="pago_monto_positivo",
            ),
        ]

    def __str__(self):
        return f"Pago #{self.pk} - Cuenta #{self.cuenta_id}"
    