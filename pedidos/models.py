from django.db import models
from django.conf import settings
import uuid

class Pedido(models.Model):

    class Estado(models.TextChoices):
        SIN_PAGAR = ('sin_pagar', 'Pendiente de pago')
        PENDIENTE = ('pendiente', 'Pendiente')
        EN_PREPARACION = ('en_preparacion', 'En preparación')
        LISTO = ('listo', 'Listo')
        ENTREGADO = ('entregado', 'Entregado')
        CANCELADO = ('cancelado', 'Cancelado')
    mesa = models.ForeignKey('mesas.Mesa', on_delete=models.PROTECT, related_name='pedidos')
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.SIN_PAGAR)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.PROTECT, related_name='pedidos', null=True, blank=True)
    cliente_clave = models.CharField(max_length=64, blank=True, db_index=True)
    checkout_clave = models.CharField(max_length=64, unique=True, null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']

    def __str__(self):
        return f'Pedido #{self.pk} - Mesa {self.mesa.numero}'

class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('carta.Producto', on_delete=models.PROTECT, related_name='detalles_pedido')
    nombre_producto = models.CharField(max_length=255)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    def __str__(self):
        return f'{self.cantidad} × {self.nombre_producto}'

class Cuenta(models.Model):

    class Estado(models.TextChoices):
        ABIERTA = ('abierta', 'Abierta')
        CERRADA = ('cerrada', 'Cerrada')
    mesa = models.ForeignKey('mesas.Mesa', on_delete=models.PROTECT, related_name='cuentas')
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    creada = models.DateTimeField(auto_now_add=True)
    cerrada = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creada']
        constraints = [models.UniqueConstraint(fields=['mesa'], condition=models.Q(estado='abierta'), name='una_cuenta_abierta_por_mesa')]

    def __str__(self):
        return f'Cuenta #{self.pk} - Mesa {self.mesa.numero}'

class Pago(models.Model):

    class Metodo(models.TextChoices):
        EFECTIVO = ('efectivo', 'Efectivo')
        DEBITO = ('debito', 'Tarjeta de débito')
        CREDITO = ('credito', 'Tarjeta de crédito')
        TRANSFERENCIA = ('transferencia', 'Transferencia')
        WEBPAY = ('webpay', 'Webpay Plus (integración)')
    cuenta = models.ForeignKey('Cuenta', on_delete=models.PROTECT, related_name='pagos')
    pedido = models.OneToOneField('Pedido', on_delete=models.PROTECT, related_name='pago', null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=Metodo.choices)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pagos_registrados', null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    intento_webpay = models.OneToOneField('IntentoWebpay', on_delete=models.PROTECT, related_name='pago_confirmado', null=True, blank=True)

    class Meta:
        ordering = ['-creado']
        constraints = [models.CheckConstraint(condition=models.Q(monto__gt=0), name='pago_monto_positivo')]

    def __str__(self):
        return f'Pago #{self.pk} - Cuenta #{self.cuenta_id}'

def generar_orden_webpay():
    return 'K' + uuid.uuid4().hex[:25]

class IntentoWebpay(models.Model):

    class Estado(models.TextChoices):
        CREADO = ('creado', 'Creado')
        INICIADO = ('iniciado', 'Iniciado')
        POR_VERIFICAR = ('por_verificar', 'Por verificar')
        AUTORIZADO = ('autorizado', 'Autorizado')
        RECHAZADO = ('rechazado', 'Rechazado')
        ANULADO = ('anulado', 'Anulado')
        FALLIDO = ('fallido', 'Fallido')
    pedido = models.ForeignKey('Pedido', on_delete=models.PROTECT, related_name='intentos_webpay', null=True, blank=True)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.PROTECT, related_name='intentos_webpay')
    orden_compra = models.CharField(max_length=26, unique=True, default=generar_orden_webpay, editable=False)
    session_id = models.UUIDField(default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.CREADO)
    iniciado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='intentos_webpay', null=True, blank=True)
    codigo_autorizacion = models.CharField(max_length=32, blank=True)
    codigo_respuesta = models.IntegerField(null=True, blank=True)
    tipo_pago = models.CharField(max_length=8, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado']
        constraints = [models.CheckConstraint(condition=models.Q(monto__gt=0), name='intento_webpay_monto_positivo'), models.UniqueConstraint(fields=['cuenta'], condition=models.Q(pedido__isnull=True, estado__in=['creado', 'iniciado', 'por_verificar']), name='un_intento_webpay_activo_por_cuenta'), models.UniqueConstraint(fields=['pedido'], condition=models.Q(pedido__isnull=False, estado__in=['creado', 'iniciado', 'por_verificar']), name='un_intento_activo_por_pedido')]

    def __str__(self):
        return f'{self.orden_compra} - {self.get_estado_display()}'
    detalle = models.JSONField(default=list, blank=True)
    url_webpay = models.URLField(max_length=255, blank=True)
    ultimos_digitos = models.CharField(max_length=4, blank=True)
    fecha_transaccion = models.CharField(max_length=64, blank=True)
    observacion = models.CharField(max_length=255, blank=True)
    retorno_confirmable = models.BooleanField(default=False)

    # Una cancelación local impide confirmar después un token abandonado.
    cancelacion_solicitada = models.BooleanField(default=False)
    formulario_abierto = models.BooleanField(default=False)
    # Cada botón de reintento tiene un único sucesor, incluso con doble clic.
    reintento_de = models.OneToOneField('self', on_delete=models.PROTECT,
        related_name='siguiente_intento', null=True, blank=True)
