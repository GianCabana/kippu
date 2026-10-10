"""Pago previo por pedido. Bloqueos: Mesa -> Cuenta -> Pedido -> Intento.
El carrito nunca fija el importe: se consultan precios y disponibilidad en BD.
La llamada remota de confirmación usa el timeout del SDK y mantiene el bloqueo
para que dos retornos no confirmen ni registren el mismo pago simultáneamente.
"""
import hashlib
import json
import unicodedata
import uuid
from datetime import timedelta
from transbank.common.integration_type import IntegrationType
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone
from carta.models import Producto
from mesas.models import Mesa
from .carrito import Carrito, ErrorOpciones
from .models import Cuenta, Pedido, DetallePedido, Pago, IntentoWebpay
from .webpay import obtener_webpay

ESTADOS_ACTIVOS = ('creado', 'iniciado', 'por_verificar')
PEDIDOS_CERRADOS = 'Pedidos cerrados por ahora. Puedes ver la carta; para pedir, consulta al personal.'


class ErrorPago(ValueError):
    pass


def exigir_pedidos_abiertos(mesa):
    """D-42: con el servicio cerrado no se agrega ni se empieza un pago; lo ya iniciado sigue."""
    if not mesa.local.recibe_pedidos:
        raise ErrorPago(PEDIDOS_CERRADOS)


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
    clave = clave_checkout(request, mesa, carrito.snapshot())
    pedido = Pedido.objects.filter(checkout_clave=clave, pago__isnull=False).first()
    if pedido:
        ids = request.session.get(f'pedidos_{mesa.codigo}', [])
        if pedido.pk not in ids:
            request.session[f'pedidos_{mesa.codigo}'] = [*ids, pedido.pk]
        carrito.vaciar()
        renovar_carrito(request, mesa)


def snapshot_opciones(opciones):
    return [
        {
            'id': opcion.pk,
            'grupo': opcion.grupo.nombre,
            'nombre': opcion.nombre,
            'precio_extra': format(opcion.precio_extra, '.2f'),
        }
        for opcion in opciones
    ]


def opciones_detalle_vigentes(detalle):
    guardadas = detalle.opciones or []
    try:
        ids = [int(opcion['id']) for opcion in guardadas]
    except (KeyError, TypeError, ValueError):
        return False
    try:
        opciones = Carrito.validar_opciones(detalle.producto, ids)
    except ErrorOpciones:
        return False
    if snapshot_opciones(opciones) != guardadas:
        return False
    precio_actual = detalle.producto.precio + sum(
        opcion.precio_extra for opcion in opciones
    )
    return precio_actual == detalle.precio_unitario


def detalle_pedido(pedido):
    lineas, total = [], Decimal('0.00')
    for d in pedido.detalles.order_by('producto_id', 'pk'):
        if d.cantidad <= 0 or d.precio_unitario < 0:
            raise ErrorPago('El pedido contiene cantidades o precios inválidos.')
        total += d.subtotal
        linea = {'pedido': pedido.pk, 'producto': d.producto_id,
            'nombre': d.nombre_producto, 'cantidad': d.cantidad,
            'precio_unitario': format(d.precio_unitario, '.2f'),
            'subtotal': format(d.subtotal, '.2f')}
        # Omitir False conserva compatibilidad con snapshots anteriores.
        if d.requiere_mayoria_edad:
            linea['requiere_mayoria_edad'] = True
        if d.opciones:
            linea['opciones'] = d.opciones
        lineas.append(linea)
    return lineas, total


def calcular_propina(subtotal, opcion):
    """Calcula la propina opcional en pesos enteros.

    La interfaz sugiere 10 %. Si el cliente la acepta, cualquier fracción de
    peso se redondea hacia arriba. Solo se aceptan opciones definidas por el
    servidor para impedir que el navegador altere el monto arbitrariamente.
    """
    if opcion in (None, '', '0'):
        return Decimal('0')
    if opcion != '10':
        raise ErrorPago('Selecciona una opción de propina válida.')
    return (subtotal * Decimal('0.10')).quantize(
        Decimal('1'),
        rounding=ROUND_CEILING,
    )


SIGNOS_NOMBRE = " -.'’"


def _caracter_de_nombre(caracter):
    if caracter.isspace():
        return ' '
    # Controles e invisibles (ancho cero, cambio de dirección) se quitan sin dejar hueco.
    if unicodedata.category(caracter).startswith('C'):
        return ''
    return caracter if caracter.isalpha() or caracter in SIGNOS_NOMBRE else ' '


def limpiar_nombre(valor):
    """Nombre opcional del pedido: solo letras (con tildes) y - . ' ; nunca bloquea el pago."""
    largo = Pedido._meta.get_field('nombre').max_length
    texto = unicodedata.normalize('NFC', valor or '')
    texto = ' '.join(''.join(map(_caracter_de_nombre, texto)).split())[:largo].strip()
    return texto if any(caracter.isalpha() for caracter in texto) else ''


def recordar_nombre(request):
    request.session['nombre_pedido'] = limpiar_nombre(request.POST.get('nombre'))


def nombre_recordado(request):
    return request.session.get('nombre_pedido', '')


def _bloquear_cuenta(cuenta_id):
    mesa_id = Cuenta.objects.values_list('mesa_id', flat=True).get(pk=cuenta_id)
    Mesa.objects.select_for_update().get(pk=mesa_id)
    return Cuenta.objects.select_for_update().get(pk=cuenta_id)


def crear_intento_cliente(request, codigo, return_url):
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(
            codigo=codigo,
            activa=True,
            local__activo=True,
        )
        # Protege contra doble clic y contra otro POST mientras el resultado es incierto.
        activo = intento_activo(request, mesa)
        if activo:
            return activo, False
        carrito = Carrito(request, mesa)
        clave = clave_checkout(request, mesa, carrito.snapshot())
        pedido = Pedido.objects.filter(checkout_clave=clave).first()
        if pedido and Pago.objects.filter(pedido=pedido).exists():
            return pedido.intentos_webpay.get(pago_confirmado__isnull=False), False
        # Un borrador descartado al cerrar no debe impedir empezar una visita nueva.
        if (pedido and pedido.estado == Pedido.Estado.CANCELADO
                and pedido.cuenta.estado == Cuenta.Estado.CERRADA):
            renovar_carrito(request, mesa)
            clave = clave_checkout(request, mesa, carrito.snapshot())
            pedido = None
        exigir_pedidos_abiertos(mesa)
        if not carrito.productos:
            raise ErrorPago('Tu carrito está vacío.')
        productos = list(Producto.objects.filter(pk__in=carrito.productos,
            disponible=True, categoria__activa=True,
            categoria__local=mesa.local).order_by('pk'))
        if len(productos) != len(carrito.productos):
            raise ErrorPago('Un producto ya no está disponible. Revisa tu carrito.')
        requiere_mayoria_edad = any(
            producto.requiere_mayoria_edad
            for producto in productos
        )
        mayoria_edad_confirmada = (
            request.POST.get('confirma_mayoria_edad') == 'si'
        )
        if requiere_mayoria_edad and not mayoria_edad_confirmada:
            raise ErrorPago(
                'Debes confirmar que tienes 18 años o más para comprar '
                'los productos marcados +18.'
            )
        subtotal = Decimal('0')
        configuracion = {}
        for producto in productos:
            cantidad = carrito.productos[str(producto.pk)]
            if type(cantidad) is not int or not 1 <= cantidad <= Carrito.MAXIMO_POR_PRODUCTO or producto.precio < 0:
                raise ErrorPago('Hay una cantidad o precio inválido en el carrito.')
            try:
                opciones = Carrito.validar_opciones(
                    producto,
                    carrito.opciones_producto(producto),
                )
            except ErrorOpciones as exc:
                raise ErrorPago(str(exc))
            precio_unitario = producto.precio + sum(
                opcion.precio_extra for opcion in opciones
            )
            opciones_guardadas = snapshot_opciones(opciones)
            configuracion[producto.pk] = {
                'precio_unitario': precio_unitario,
                'opciones': opciones_guardadas,
            }
            subtotal += precio_unitario * cantidad
        if subtotal <= 0 or subtotal != subtotal.to_integral_value():
            raise ErrorPago('El total debe ser positivo y estar expresado en pesos enteros.')
        propina = calcular_propina(subtotal, request.POST.get('propina'))
        nombre = limpiar_nombre(request.POST.get('nombre'))
        total = subtotal + propina
        cuenta, _ = Cuenta.objects.get_or_create(mesa=mesa, estado=Cuenta.Estado.ABIERTA)
        if cuenta.intentos_webpay.filter(pedido__isnull=True, estado__in=ESTADOS_ACTIVOS).exists():
            raise ErrorPago('Existe un pago anterior de esta cuenta por verificar. Consulta al personal.')
        if cuenta.pagos.filter(pedido__isnull=True).exists():
            raise ErrorPago('Esta cuenta tiene un pago del flujo anterior. Consulta al personal.')
        if not pedido:
            Pedido.objects.filter(mesa=mesa, cliente_clave=cliente_clave(request),
                estado=Pedido.Estado.SIN_PAGAR, pago__isnull=True).update(estado=Pedido.Estado.CANCELADO)
            pedido = Pedido.objects.create(mesa=mesa, cuenta=cuenta,
                cliente_clave=cliente_clave(request), checkout_clave=clave,
                propina=propina, nombre=nombre,
                mayoria_edad_confirmada=(
                    requiere_mayoria_edad and mayoria_edad_confirmada
                ))
            DetallePedido.objects.bulk_create([DetallePedido(pedido=pedido, producto=p,
                nombre_producto=p.nombre,
                precio_unitario=configuracion[p.pk]['precio_unitario'],
                cantidad=carrito.productos[str(p.pk)],
                requiere_mayoria_edad=p.requiere_mayoria_edad,
                opciones=configuracion[p.pk]['opciones'])
                for p in productos])
        elif pedido.cuenta_id != cuenta.pk or pedido.estado != Pedido.Estado.SIN_PAGAR:
            raise ErrorPago('Este pedido ya no admite pagos. Actualiza tu carrito.')
        # Reintentar tras rechazo usa los precios vigentes; no cambia una autorización.
        else:
            actuales = [(p.pk, p.nombre,
                configuracion[p.pk]['precio_unitario'],
                carrito.productos[str(p.pk)], p.requiere_mayoria_edad,
                configuracion[p.pk]['opciones'])
                for p in productos]
            guardados = list(pedido.detalles.order_by('producto_id').values_list(
                'producto_id', 'nombre_producto', 'precio_unitario', 'cantidad',
                'requiere_mayoria_edad', 'opciones'))
            if actuales != guardados:
                raise ErrorPago(
                    'El producto, sus opciones o su precio cambiaron. '
                    'Modifica el carrito antes de pagar nuevamente.'
                )
            if pedido.propina != propina:
                pedido.propina = propina
            confirmacion = requiere_mayoria_edad and mayoria_edad_confirmada
            if pedido.mayoria_edad_confirmada != confirmacion:
                pedido.mayoria_edad_confirmada = confirmacion
            pedido.nombre = nombre
            pedido.save(update_fields=['propina', 'mayoria_edad_confirmada', 'nombre'])
        lineas, subtotal_guardado = detalle_pedido(pedido)
        if subtotal_guardado != subtotal:
            raise ErrorPago('El subtotal del pedido cambió. Actualiza el carrito antes de pagar.')
        intento = IntentoWebpay.objects.create(cuenta=cuenta, pedido=pedido,
            monto=total, subtotal=subtotal, propina=propina, detalle=lineas,
            iniciado_por=request.user if request.user.is_authenticated else None)
    return _abrir_transaccion(intento, return_url)


def _abrir_transaccion(intento, return_url):
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


def resolver_intento(intento_id, confirmar=False, cancelar=False):
    referencia = IntentoWebpay.objects.only('cuenta_id').get(pk=intento_id)
    with transaction.atomic():
        cuenta = _bloquear_cuenta(referencia.cuenta_id)
        intento = IntentoWebpay.objects.select_for_update().get(pk=intento_id)
        if Pago.objects.filter(intento_webpay=intento).exists():
            return intento
        if intento.estado in ('rechazado', 'anulado', 'fallido'):
            return intento
        if cancelar and not intento.retorno_confirmable:
            intento.cancelacion_solicitada = True
        if confirmar and not intento.cancelacion_solicitada:
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
                    lineas, subtotal = detalle_pedido(pedido)
                except ErrorPago:
                    lineas, subtotal = [], Decimal('-1')
                requiere_mayoria_edad = pedido.detalles.filter(
                    requiere_mayoria_edad=True,
                ).exists()
                if (pedido.estado == Pedido.Estado.SIN_PAGAR and cuenta.estado == Cuenta.Estado.ABIERTA
                        and subtotal == intento.subtotal
                        and pedido.propina == intento.propina
                        and subtotal + pedido.propina == intento.monto
                        and (not requiere_mayoria_edad
                            or pedido.mayoria_edad_confirmada)
                        and lineas == intento.detalle):
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
            if (intento.cancelacion_solicitada
                    and respuesta.get('response_code') is None
                    and not respuesta.get('authorization_code')
                    and not intento.codigo_autorizacion):
                intento.estado = IntentoWebpay.Estado.ANULADO
                intento.url_webpay = ''
                intento.observacion = ('Intento cancelado sin autorización en la consulta. '
                    'Tu carrito se conserva. Puedes reintentar con un pago nuevo.')
            elif (cliente.options.integration_type == IntegrationType.TEST
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
                    intento.observacion = 'El pago no está completado. Puedes cancelar o reintentar el pago.'
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


def reintentar_pago(intento_id, usuario, return_url):
    """Abandona el anterior únicamente tras consultar; crea un sucesor idempotente."""
    ref = IntentoWebpay.objects.only('cuenta_id').get(pk=intento_id)
    sucesor = IntentoWebpay.objects.filter(reintento_de_id=intento_id).first()
    if sucesor:
        return sucesor, False
    # Confirmar la cancelación en su propia transacción. Si luego cambió un precio,
    # el usuario debe poder editar el carrito sin reactivar el intento abandonado.
    resolver_intento(intento_id, cancelar=True)
    with transaction.atomic():
        cuenta = _bloquear_cuenta(ref.cuenta_id)
        anterior = IntentoWebpay.objects.select_for_update().get(pk=intento_id)
        siguiente = IntentoWebpay.objects.filter(reintento_de=anterior).first()
        if siguiente:
            return siguiente, False
        if not anterior.pedido_id:
            raise ErrorPago('Este intento es de una cuenta antigua. Cancélalo y vuelve a tu carrito para crear un pedido nuevo.')
        pagado = Pago.objects.filter(pedido_id=anterior.pedido_id).first()
        if pagado:
            if pagado.intento_webpay_id:
                return pagado.intento_webpay, False
            raise ErrorPago('Este pedido ya tiene un pago registrado.')
        if anterior.estado not in ('rechazado', 'anulado', 'fallido'):
            return anterior, False
        if cuenta.estado != Cuenta.Estado.ABIERTA:
            raise ErrorPago('Esta cuenta está cerrada. Vuelve a la carta para una nueva compra.')
        pedido = Pedido.objects.select_for_update().get(pk=anterior.pedido_id)
        if pedido.estado != Pedido.Estado.SIN_PAGAR:
            raise ErrorPago('El pedido no está pendiente de pago. Revisa su estado con el personal.')
        activo = pedido.intentos_webpay.filter(estado__in=ESTADOS_ACTIVOS).first()
        if activo:
            return activo, False
        exigir_pedidos_abiertos(pedido.mesa)
        detalles = list(pedido.detalles.select_related('producto__categoria').order_by('producto_id'))
        if not detalles or any(not d.producto.disponible or not d.producto.categoria.activa
                or not opciones_detalle_vigentes(d) or d.cantidad < 1
                or d.requiere_mayoria_edad != d.producto.requiere_mayoria_edad
                or d.cantidad > Carrito.MAXIMO_POR_PRODUCTO for d in detalles):
            raise ErrorPago(
                'Cambió la disponibilidad o el precio de una opción o '
                'producto. Vuelve '
                'a la carta y modifica el carrito antes de pagar.'
            )
        if (any(d.requiere_mayoria_edad for d in detalles)
                and not pedido.mayoria_edad_confirmada):
            raise ErrorPago(
                'Falta la confirmación de mayoría de edad. Vuelve a la '
                'carta antes de pagar.'
            )
        lineas, subtotal = detalle_pedido(pedido)
        propina = pedido.propina
        total = subtotal + propina
        if (subtotal <= 0 or subtotal != subtotal.to_integral_value()
                or propina < 0 or propina != propina.to_integral_value()
                or total <= 0 or total != total.to_integral_value()):
            raise ErrorPago('El importe del pedido no es válido.')
        nuevo = IntentoWebpay.objects.create(cuenta=cuenta, pedido=pedido,
            reintento_de=anterior, monto=total, subtotal=subtotal,
            propina=propina, detalle=lineas,
            iniciado_por=usuario if usuario.is_authenticated else None)
    return _abrir_transaccion(nuevo, return_url)


def consumir_formulario(intento_id):
    ref = IntentoWebpay.objects.only('cuenta_id').get(pk=intento_id)
    with transaction.atomic():
        cuenta = _bloquear_cuenta(ref.cuenta_id)
        intento = IntentoWebpay.objects.select_for_update().get(pk=intento_id)
        pagado = (Pago.objects.filter(pedido_id=intento.pedido_id).exists()
                  if intento.pedido_id else Pago.objects.filter(cuenta=cuenta).exists())
        if (pagado or cuenta.estado != Cuenta.Estado.ABIERTA
                or intento.estado != IntentoWebpay.Estado.INICIADO
                or intento.formulario_abierto or intento.cancelacion_solicitada
                or intento.retorno_confirmable or not intento.url_webpay
                or timezone.now() - intento.creado >= timedelta(minutes=5)):
            return intento, False
        intento.formulario_abierto = True
        intento.save(update_fields=['formulario_abierto', 'actualizado'])
        return intento, True
