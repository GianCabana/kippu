"""Pago presencial en caja (D-07): el pedido espera en por_cobrar y entra a cocina solo cuando el
personal cobra. Mismo orden de bloqueo que Webpay: Mesa -> Cuenta -> Pedido."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from mesas.models import Mesa
from .carrito import Carrito
from .models import Pago, Pedido
from .pagos import (ErrorPago, _bloquear_cuenta, clave_checkout, cliente_clave, detalle_pedido,
                    intento_activo, preparar_pedido, renovar_carrito)

# Sin cobrar en este tiempo, el pedido se cancela solo (se revisa sin reloj aparte, como la 41).
VENCE_POR_COBRAR = timedelta(minutes=30)
METODOS_CAJA = (Pago.Metodo.EFECTIVO, Pago.Metodo.DEBITO, Pago.Metodo.CREDITO)


class YaPorCobrar(ErrorPago):
    pass


def vencer_por_cobrar(mesa=None, ahora=None):
    limite = (ahora or timezone.now()) - VENCE_POR_COBRAR
    pedidos = Pedido.objects.filter(estado=Pedido.Estado.POR_COBRAR, pago__isnull=True, creado__lte=limite)
    if mesa is not None:
        pedidos = pedidos.filter(mesa=mesa)
    return pedidos.update(estado=Pedido.Estado.CANCELADO)


def _vencido(pedido):
    return timezone.now() - pedido.creado >= VENCE_POR_COBRAR


def crear_por_cobrar(request, codigo):
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(codigo=codigo, activa=True, local__activo=True)
        vencer_por_cobrar(mesa)
        if Pedido.objects.filter(cliente_clave=cliente_clave(request), estado=Pedido.Estado.POR_COBRAR).exists():
            raise YaPorCobrar('Ya tienes un pedido por pagar en caja. Págalo o cancélalo antes de pedir otro.')
        if intento_activo(request, mesa):
            raise ErrorPago('Tienes un pago con Webpay en curso. Resuélvelo antes de pagar en caja.')
        carrito = Carrito(request, mesa)
        clave = clave_checkout(request, mesa, carrito.snapshot())
        pedido = Pedido.objects.filter(checkout_clave=clave).first()
        pedido, _, _, _, _ = preparar_pedido(request, mesa, carrito, clave, pedido)
        pedido.estado = Pedido.Estado.POR_COBRAR
        pedido.save(update_fields=['estado'])
        # El carrito ya es un pedido: se vacía como después de pagar.
        carrito.vaciar()
        renovar_carrito(request, mesa)
        ids = request.session.get(f'pedidos_{mesa.codigo}', [])
        request.session[f'pedidos_{mesa.codigo}'] = [*ids, pedido.pk]
    return pedido


def _bloquear_pedido(pedido_id):
    cuenta_id = Pedido.objects.values_list('cuenta_id', flat=True).get(pk=pedido_id)
    if cuenta_id is None:
        raise ErrorPago('Este pedido no tiene cuenta. Requiere revisión.')
    cuenta = _bloquear_cuenta(cuenta_id)
    return cuenta, Pedido.objects.select_for_update().get(pk=pedido_id)


def cobrar_por_cobrar(pedido_id, metodo, usuario):
    """Devuelve (pago, nuevo). Un segundo envío devuelve el pago ya registrado."""
    if metodo not in METODOS_CAJA:
        raise ErrorPago('Método de pago no válido. Usa efectivo, débito o crédito.')
    error = ''
    with transaction.atomic():
        cuenta, pedido = _bloquear_pedido(pedido_id)
        pago = Pago.objects.filter(pedido=pedido).first()
        if pago:
            return pago, False
        if pedido.estado == Pedido.Estado.POR_COBRAR and _vencido(pedido):
            pedido.estado = Pedido.Estado.CANCELADO
            pedido.save(update_fields=['estado'])
            error = f'El pedido #{pedido.pk} venció sin cobrar (30 minutos) y se canceló.'
        elif pedido.estado != Pedido.Estado.POR_COBRAR:
            error = f'El pedido #{pedido.pk} ya no está por cobrar ({pedido.get_estado_display().lower()}).'
        elif cuenta.estado != cuenta.Estado.ABIERTA:
            error = 'La cuenta de este pedido está cerrada. Requiere revisión.'
        else:
            lineas, subtotal = detalle_pedido(pedido)
            monto = subtotal + pedido.propina
            if not lineas or monto <= 0 or monto != monto.to_integral_value():
                error = 'El importe del pedido no es válido. Requiere revisión.'
            else:
                pago = Pago.objects.create(cuenta=cuenta, pedido=pedido, monto=monto,
                                           metodo=metodo, registrado_por=usuario)
                pedido.estado = Pedido.Estado.PENDIENTE
                pedido.save(update_fields=['estado'])
                return pago, True
    raise ErrorPago(error)


def cancelar_por_cobrar(pedido_id):
    """Solo cancela si sigue por cobrar y sin pago. Devuelve si lo canceló."""
    with transaction.atomic():
        _, pedido = _bloquear_pedido(pedido_id)
        if pedido.estado != Pedido.Estado.POR_COBRAR or Pago.objects.filter(pedido=pedido).exists():
            return False
        pedido.estado = Pedido.Estado.CANCELADO
        pedido.save(update_fields=['estado'])
        return True
