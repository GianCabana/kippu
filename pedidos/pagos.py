"""Pago previo por pedido. Bloqueos: Mesa -> Cuenta -> Pedido -> Intento.
El carrito nunca fija el importe: se consultan precios y disponibilidad en BD.
La llamada remota de confirmación usa el timeout del SDK y mantiene el bloqueo
para que dos retornos no confirmen ni registren el mismo pago simultáneamente.
"""
import hashlib
import json
import uuid
from datetime import timedelta
from transbank.common.integration_type import IntegrationType
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from carta.models import Producto
from mesas.models import Mesa
from .carrito import Carrito
from .models import Cuenta, Pedido, DetallePedido, Pago, IntentoWebpay
from .webpay import obtener_webpay

ESTADOS_ACTIVOS = ('creado', 'iniciado', 'por_verificar')


class ErrorPago(ValueError):
    pass


def cliente_clave(request):
    if not request.session.session_key:
        request.session.create()
    return hashlib.sha256(request.session.session_key.encode()).hexdigest()


def clave_checkout(request, mesa, productos):
    revision = request.session.get(f'revision_carrito_{mesa.codigo}', '')
    datos = json.dumps([cliente_clave(request), str(mesa.codigo), revision, productos], sort_keys=True)
    return hashlib.sha256(datos.encode()).hexdigest()


def renovar_carrito(request, mesa):
    request.session[f'revision_carrito_{mesa.codigo}'] = uuid.uuid4().hex


def intento_activo(request, mesa):
    return IntentoWebpay.objects.filter(pedido__mesa=mesa,
        pedido__cliente_clave=cliente_clave(request), estado__in=ESTADOS_ACTIVOS).first()


def sincronizar_carrito(request, mesa):
    """Limpieza idempotente; nunca borra un carrito editado después del pago."""
    carrito = Carrito(request, mesa)
    clave = clave_checkout(request, mesa, carrito.productos)
    pedido = Pedido.objects.filter(checkout_clave=clave, pago__isnull=False).first()
    if pedido:
        ids = request.session.get(f'pedidos_{mesa.codigo}', [])
        if pedido.pk not in ids:
            request.session[f'pedidos_{mesa.codigo}'] = [*ids, pedido.pk]
        carrito.productos = {}
        carrito.guardar()
        renovar_carrito(request, mesa)


def detalle_pedido(pedido):
    lineas, total = [], Decimal('0.00')
    for d in pedido.detalles.order_by('producto_id', 'pk'):
        if d.cantidad <= 0 or d.precio_unitario < 0:
            raise ErrorPago('El pedido contiene cantidades o precios inválidos.')
        total += d.subtotal
        lineas.append({'pedido': pedido.pk, 'producto': d.producto_id,
            'nombre': d.nombre_producto, 'cantidad': d.cantidad,
            'precio_unitario': format(d.precio_unitario, '.2f'),
            'subtotal': format(d.subtotal, '.2f')})
    return lineas, total


def _bloquear_cuenta(cuenta_id):
    mesa_id = Cuenta.objects.values_list('mesa_id', flat=True).get(pk=cuenta_id)
    Mesa.objects.select_for_update().get(pk=mesa_id)
    return Cuenta.objects.select_for_update().get(pk=cuenta_id)


def crear_intento_cliente(request, codigo, return_url):
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(codigo=codigo, activa=True)
        # Protege contra doble clic y contra otro POST mientras el resultado es incierto.
        activo = intento_activo(request, mesa)
        if activo:
            return activo, False
        carrito = Carrito(request, mesa)
        clave = clave_checkout(request, mesa, carrito.productos)
        pedido = Pedido.objects.filter(checkout_clave=clave).first()
        if pedido and Pago.objects.filter(pedido=pedido).exists():
            return pedido.intentos_webpay.get(pago_confirmado__isnull=False), False
        # Un borrador descartado al cerrar no debe impedir empezar una visita nueva.
        if (pedido and pedido.estado == Pedido.Estado.CANCELADO
                and pedido.cuenta.estado == Cuenta.Estado.CERRADA):
            renovar_carrito(request, mesa)
            clave = clave_checkout(request, mesa, carrito.productos)
            pedido = None
        if not carrito.productos:
            raise ErrorPago('Tu carrito está vacío.')
        productos = list(Producto.objects.filter(pk__in=carrito.productos,
            disponible=True, categoria__activa=True).order_by('pk'))
        if len(productos) != len(carrito.productos):
            raise ErrorPago('Un producto ya no está disponible. Revisa tu carrito.')
        total = Decimal('0')
        for producto in productos:
            cantidad = carrito.productos[str(producto.pk)]
            if type(cantidad) is not int or not 1 <= cantidad <= Carrito.MAXIMO_POR_PRODUCTO or producto.precio < 0:
                raise ErrorPago('Hay una cantidad o precio inválido en el carrito.')
            total += producto.precio * cantidad
        if total <= 0 or total != total.to_integral_value():
            raise ErrorPago('El total debe ser positivo y estar expresado en pesos enteros.')
        cuenta, _ = Cuenta.objects.get_or_create(mesa=mesa, estado=Cuenta.Estado.ABIERTA)
        if cuenta.intentos_webpay.filter(pedido__isnull=True, estado__in=ESTADOS_ACTIVOS).exists():
            raise ErrorPago('Existe un pago anterior de esta cuenta por verificar. Consulta al personal.')
        if cuenta.pagos.filter(pedido__isnull=True).exists():
            raise ErrorPago('Esta cuenta tiene un pago del flujo anterior. Consulta al personal.')
        if not pedido:
            Pedido.objects.filter(mesa=mesa, cliente_clave=cliente_clave(request),
                estado=Pedido.Estado.SIN_PAGAR, pago__isnull=True).update(estado=Pedido.Estado.CANCELADO)
            pedido = Pedido.objects.create(mesa=mesa, cuenta=cuenta,
                cliente_clave=cliente_clave(request), checkout_clave=clave)
            DetallePedido.objects.bulk_create([DetallePedido(pedido=pedido, producto=p,
                nombre_producto=p.nombre, precio_unitario=p.precio,
                cantidad=carrito.productos[str(p.pk)]) for p in productos])
        elif pedido.cuenta_id != cuenta.pk or pedido.estado != Pedido.Estado.SIN_PAGAR:
            raise ErrorPago('Este pedido ya no admite pagos. Actualiza tu carrito.')
        # Reintentar tras rechazo usa los precios vigentes; no cambia una autorización.
        else:
            actuales = [(p.pk, p.nombre, p.precio, carrito.productos[str(p.pk)]) for p in productos]
            guardados = list(pedido.detalles.order_by('producto_id').values_list(
                'producto_id', 'nombre_producto', 'precio_unitario', 'cantidad'))
            if actuales != guardados:
                raise ErrorPago('El producto o su precio cambió. Modifica el carrito antes de pagar nuevamente.')
        lineas, total = detalle_pedido(pedido)
        intento = IntentoWebpay.objects.create(cuenta=cuenta, pedido=pedido,
            monto=total, detalle=lineas,
            iniciado_por=request.user if request.user.is_authenticated else None)
    try:
        respuesta = obtener_webpay().create(intento.orden_compra, str(intento.session_id),
                                            int(intento.monto), return_url)
        token, url = respuesta.get('token'), respuesta.get('url')
        parsed = urlsplit(url or '')
        if not isinstance(token, str) or len(token) != 64 or parsed.scheme != 'https' or parsed.hostname != 'webpay3gint.transbank.cl' or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ErrorPago('Respuesta de creación no válida.')
    except Exception:
        IntentoWebpay.objects.filter(pk=intento.pk, estado__in=ESTADOS_ACTIVOS).update(
            estado=IntentoWebpay.Estado.FALLIDO,
            observacion='No se pudo abrir Webpay. Tu carrito se conserva; puedes reintentar.',
            actualizado=timezone.now())
        intento.refresh_from_db()
        return intento, False
    with transaction.atomic():
        _bloquear_cuenta(intento.cuenta_id)
        intento = IntentoWebpay.objects.select_for_update().get(pk=intento.pk)
        intento.token, intento.url_webpay = token, url
        intento.estado = IntentoWebpay.Estado.INICIADO
        intento.save()
    return intento, True


def _coincide(respuesta, intento):
    try:
        monto = Decimal(str(respuesta.get('amount')))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return (monto.is_finite() and monto == intento.monto
        and respuesta.get('buy_order') == intento.orden_compra
        and respuesta.get('session_id') == str(intento.session_id))


def resolver_intento(intento_id, confirmar=False):
    referencia = IntentoWebpay.objects.only('cuenta_id').get(pk=intento_id)
    with transaction.atomic():
        cuenta = _bloquear_cuenta(referencia.cuenta_id)
        intento = IntentoWebpay.objects.select_for_update().get(pk=intento_id)
        if Pago.objects.filter(intento_webpay=intento).exists():
            return intento
        if intento.estado in ('rechazado', 'anulado', 'fallido'):
            return intento
        if confirmar:
            intento.retorno_confirmable = True
        intento.estado = IntentoWebpay.Estado.POR_VERIFICAR
        if not intento.token:
            intento.observacion = 'El inicio está en curso. Vuelve a consultar este mismo intento.'
            intento.save()
            return intento
        try:
            cliente = obtener_webpay()
            respuesta = cliente.status(intento.token)
            if not _coincide(respuesta, intento):
                raise ErrorPago('La respuesta no coincide con el intento.')
            if respuesta.get('status') == 'INITIALIZED' and intento.retorno_confirmable:
                respuesta = cliente.commit(intento.token)
            if not _coincide(respuesta, intento):
                raise ErrorPago('No coincide el monto, la orden o la sesión.')
        except Exception:
            intento.observacion = 'No se pudo verificar el resultado. No pagues de nuevo; consulta este mismo intento.'
            intento.save()
            return intento
        status, code = respuesta.get('status'), respuesta.get('response_code')
        intento.codigo_respuesta = code if type(code) is int else None
        if status == 'AUTHORIZED' and type(code) is int and code == 0:
            autorizacion = str(respuesta.get('authorization_code') or '')
            if not autorizacion:
                intento.observacion = 'Falta el código de autorización. Consulta al personal antes de reintentar.'
                intento.save()
                return intento
            intento.codigo_autorizacion = autorizacion[:32]
            intento.tipo_pago = str(respuesta.get('payment_type_code') or '')[:8]
            tarjeta = str((respuesta.get('card_detail') or {}).get('card_number') or '')
            intento.ultimos_digitos = tarjeta[-4:] if tarjeta.isdigit() else ''
            intento.fecha_transaccion = str(respuesta.get('transaction_date') or '')[:64]
            intento.estado = IntentoWebpay.Estado.AUTORIZADO
            if intento.pedido_id:
                pedido = Pedido.objects.select_for_update().get(pk=intento.pedido_id)
                # No debe existir otro pago del pedido, aunque hubiera un intento antiguo.
                if Pago.objects.filter(pedido=pedido).exists():
                    intento.observacion = 'Otra autorización existe para este pedido. Revisión del personal requerida.'
                    intento.save()
                    return intento
                Pago.objects.create(cuenta=cuenta, pedido=pedido, intento_webpay=intento,
                    monto=intento.monto, metodo=Pago.Metodo.WEBPAY,
                    registrado_por_id=intento.iniciado_por_id)
                try:
                    lineas, total = detalle_pedido(pedido)
                except ErrorPago:
                    lineas, total = [], Decimal('-1')
                if (pedido.estado == Pedido.Estado.SIN_PAGAR and cuenta.estado == Cuenta.Estado.ABIERTA
                        and total == intento.monto and lineas == intento.detalle):
                    pedido.estado = Pedido.Estado.PENDIENTE
                    pedido.save(update_fields=['estado'])
                    intento.observacion = ''
                else:
                    intento.observacion = 'Pago registrado, pero el pedido cambió. No se envió a cocina; consulta al personal.'
            else:
                # Compatibilidad con retornos de intentos anteriores a esta actualización.
                Pago.objects.create(cuenta=cuenta, intento_webpay=intento, monto=intento.monto,
                    metodo=Pago.Metodo.WEBPAY, registrado_por_id=intento.iniciado_por_id)
                intento.observacion = 'Pago del flujo anterior registrado. El personal debe revisar esta cuenta.'
            # Pagar no cierra la cuenta ni da por entregado el pedido.
        elif status == 'INITIALIZED' and not intento.retorno_confirmable:
            # Política LOCAL de recuperación de demos, nunca para producción.
            # Se consulta primero la API y se verifican monto, orden y sesión.
            # 20 min da margen sobre 5 min de acceso + 10 min de formulario TEST.
            antiguedad = timezone.now() - intento.creado
            if (cliente.options.integration_type == IntegrationType.TEST
                    and antiguedad >= timedelta(minutes=20)
                    and respuesta.get('response_code') is None
                    and not respuesta.get('authorization_code')
                    and not intento.codigo_autorizacion):
                intento.estado = IntentoWebpay.Estado.FALLIDO
                intento.url_webpay = ''
                intento.observacion = ('Intento de prueba vencido, sin autorización en la consulta. '
                    'Vuelve a la carta para iniciar un pago nuevo o cierra la mesa desde Caja.')
            else:
                intento.estado = IntentoWebpay.Estado.INICIADO
                if antiguedad >= timedelta(minutes=5):
                    intento.observacion = ('El enlace inicial ya superó 5 minutos. No lo reutilices. '
                        'En integración, verifica nuevamente al cumplirse 20 minutos desde su creación. '
                        'En producción se requiere revisión del proveedor.')
                else:
                    intento.observacion = 'El pago no está completado. Puedes continuar este mismo intento.'
        elif status == 'FAILED':
            intento.estado = IntentoWebpay.Estado.RECHAZADO
            intento.observacion = 'Pago rechazado. Tu carrito se conserva y el pedido no pasó a cocina.'
        elif status in ('REVERSED', 'NULLIFIED'):
            intento.estado = IntentoWebpay.Estado.ANULADO
            intento.observacion = 'Pago anulado. Tu carrito se conserva y el pedido no pasó a cocina.'
        else:
            intento.observacion = 'Webpay aún no confirma un resultado final. Verifica antes de reintentar.'
        intento.save()
        return intento
