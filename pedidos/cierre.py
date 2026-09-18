"""Cierre de una visita. No cobra, reembolsa ni desactiva el QR de la mesa."""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import Cuenta, Pedido, Pago, IntentoWebpay
from .pagos import ESTADOS_ACTIVOS, ErrorPago, _bloquear_cuenta, detalle_pedido


def revisar_cierre(cuenta):
    pedidos = list(cuenta.pedidos.prefetch_related('detalles').order_by('pk'))
    pagos = list(cuenta.pagos.select_related('intento_webpay').order_by('pk'))
    por_pedido = {p.pedido_id:p for p in pagos if p.pedido_id}
    borradores = [p for p in pedidos if p.estado == Pedido.Estado.SIN_PAGAR and p.pk not in por_pedido]
    total = sum((p.monto for p in pagos), Decimal('0.00'))
    motivo = ''
    if cuenta.estado != Cuenta.Estado.ABIERTA:
        motivo = 'La cuenta ya está cerrada.'
    elif cuenta.intentos_webpay.filter(estado__in=ESTADOS_ACTIVOS).exists():
        motivo = 'Hay un pago en curso o por verificar.'
    elif cuenta.intentos_webpay.filter(estado=IntentoWebpay.Estado.AUTORIZADO, pago_confirmado__isnull=True).exists():
        motivo = 'Hay una autorización sin pago registrado. Requiere revisión.'
    elif any(p.pedido_id is None for p in pagos):
        motivo = 'Hay un pago de cuenta del flujo anterior. Requiere revisión del historial.'
    elif any(p.pedido_id not in {x.pk for x in pedidos} for p in pagos):
        motivo = 'Un pago pertenece a un pedido de otra cuenta. Requiere revisión.'
    else:
        for pedido in pedidos:
            pago = por_pedido.get(pedido.pk)
            if pago:
                if pedido.estado != Pedido.Estado.ENTREGADO:
                    motivo = 'Falta entregar un pedido pagado o revisar un pedido pagado cancelado.'
                    break
                try:
                    lineas, monto = detalle_pedido(pedido)
                except ErrorPago:
                    motivo = 'El detalle de un pedido requiere revisión.'
                    break
                if not lineas or monto != pago.monto:
                    motivo = 'El monto de un pago no coincide con su pedido.'
                    break
                if pago.intento_webpay_id and (
                    pago.intento_webpay.estado != IntentoWebpay.Estado.AUTORIZADO
                    or pago.intento_webpay.observacion
                    or pago.intento_webpay.monto != pago.monto
                    or pago.intento_webpay.pedido_id != pedido.pk
                ):
                    motivo = 'Un pago Webpay requiere revisión antes de cerrar.'
                    break
            elif pedido.estado not in (Pedido.Estado.SIN_PAGAR, Pedido.Estado.CANCELADO):
                motivo = 'Existe un pedido sin pago registrado. Requiere revisión.'
                break
    return {'puede_cerrar':not motivo, 'motivo':motivo, 'total_pagado':total,
        'cantidad_pedidos':len(pedidos), 'borradores':len(borradores)}


def cerrar_cuenta(cuenta_id):
    with transaction.atomic():
        # Mismo orden de bloqueo que crear/confirmar Webpay: evita cerrar en mitad de un pago.
        cuenta = _bloquear_cuenta(cuenta_id)
        if cuenta.estado == Cuenta.Estado.CERRADA:
            return cuenta, False
        revision = revisar_cierre(cuenta)
        if not revision['puede_cerrar']:
            raise ErrorPago(revision['motivo'])
        # Solo descarta borradores impagados sin transacción activa; nunca pedidos pagados.
        cuenta.pedidos.filter(estado=Pedido.Estado.SIN_PAGAR,
                             pago__isnull=True).update(estado=Pedido.Estado.CANCELADO)
        cuenta.estado = Cuenta.Estado.CERRADA
        cuenta.cerrada = timezone.now()
        cuenta.save(update_fields=['estado','cerrada'])
        return cuenta, True
