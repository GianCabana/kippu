from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.db import transaction

from .models import Cuenta, DetallePedido, Pedido, IntentoWebpay, Pago
from .pagos import ESTADOS_ACTIVOS, intento_activo, sincronizar_carrito, renovar_carrito, cliente_clave
from django.db.models import Q

from carta.models import Producto
from mesas.models import Mesa
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .carrito import Carrito, ErrorOpciones
from .cierre import revisar_cierre, cerrar_cuenta
from .pagos import ErrorPago, calcular_propina
from django.http import HttpResponse
from django.utils.cache import patch_cache_control, patch_vary_headers


def _opciones_post(request):
    valores = request.POST.getlist("opcion")
    for nombre in request.POST:
        if nombre.startswith("opcion_grupo_"):
            valores.extend(request.POST.getlist(nombre))
    return valores


def _redireccion_carrito(request, url):
    if request.headers.get('HX-Request') == 'true':
        respuesta = HttpResponse(status=200)
        respuesta['HX-Redirect'] = url
    else:
        respuesta = redirect(url)
    patch_cache_control(respuesta, no_store=True, private=True)
    patch_vary_headers(respuesta, ['HX-Request', 'Cookie'])
    return respuesta


def _respuesta_carrito(request, mesa, carrito):
    if request.headers.get('HX-Request') != 'true':
        return redirect('carta:por_mesa', codigo=mesa.codigo)
    detalle, total = carrito.obtener_detalle()
    requiere_mayoria_edad = any(
        item['producto'].requiere_mayoria_edad
        for item in detalle
    )
    propina_10 = calcular_propina(total, '10')
    respuesta = render(request, 'carta/fragmentos/carrito.html', {
        'mesa': mesa, 'detalle_carrito': detalle,
        'cantidad_carrito': carrito.cantidad_total(), 'total_carrito': total,
        'propina_10': propina_10, 'total_con_propina': total + propina_10,
        'requiere_mayoria_edad': requiere_mayoria_edad,
    })
    patch_cache_control(respuesta, no_store=True, private=True)
    patch_vary_headers(respuesta, ['HX-Request', 'Cookie'])
    return respuesta


@require_POST
@transaction.atomic
def agregar_al_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa.objects.select_for_update(),
        codigo=codigo,
        activa=True,
        local__activo=True,
    )

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
        disponible=True,
        categoria__activa=True,
        categoria__local=mesa.local,
    )

    activo = intento_activo(request, mesa)
    if activo:
        from .vistas_webpay import _url_resultado
        messages.info(request, 'Resuelve el pago en curso antes de modificar el carrito.')
        return _redireccion_carrito(request, _url_resultado(activo.pk))
    sincronizar_carrito(request, mesa)

    carrito = Carrito(request, mesa)

    try:
        opciones = Carrito.validar_opciones(
            producto,
            _opciones_post(request),
        )
    except ErrorOpciones as exc:
        messages.warning(request, str(exc))
        return _respuesta_carrito(request, mesa, carrito)

    if carrito.agregar(producto, [opcion.pk for opcion in opciones]):
        renovar_carrito(request, mesa)
        messages.success(
            request,
            f"Agregaste {producto.nombre}.",
        )
    elif carrito.ultimo_error == "opciones_distintas":
        messages.warning(
            request,
            "Ese producto ya está en el carrito con otra configuración. "
            "Quítalo antes de elegir opciones diferentes.",
        )
    else:
        messages.warning(
            request,
            "Puedes agregar hasta 20 unidades de cada producto.",
        )

    return _respuesta_carrito(request, mesa, carrito)


@require_POST
@transaction.atomic
def quitar_del_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa.objects.select_for_update(),
        codigo=codigo,
        activa=True,
        local__activo=True,
    )

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
        categoria__local=mesa.local,
    )

    activo = intento_activo(request, mesa)
    if activo:
        from .vistas_webpay import _url_resultado
        messages.info(request, 'Resuelve el pago en curso antes de modificar el carrito.')
        return _redireccion_carrito(request, _url_resultado(activo.pk))
    sincronizar_carrito(request, mesa)

    carrito = Carrito(request, mesa)
    carrito.quitar(producto)
    renovar_carrito(request, mesa)

    messages.success(
        request,
        f"Quitaste una unidad de {producto.nombre}.",
    )

    return _respuesta_carrito(request, mesa, carrito)
@require_POST
def enviar_pedido(request, codigo):
    # La URL antigua también debe pasar por Webpay; nunca envía sin pagar.
    from .vistas_webpay import iniciar_cliente
    return iniciar_cliente(request, codigo)

@staff_member_required
def cocina(request):
    pedidos = (
        Pedido.objects.filter(
            pago__isnull=False,
            estado__in=[
                Pedido.Estado.PENDIENTE,
                Pedido.Estado.EN_PREPARACION,
            ]
        )
        .select_related("mesa", "mesa__local")
        .prefetch_related("detalles")
        .order_by("creado", "pk")
    )

    return render(
        request,
        "pedidos/cocina.html",
        {"pedidos": pedidos},
    )
@staff_member_required
@require_POST
def cambiar_estado(request, pedido_id):
    nuevo_estado = request.POST.get("estado")

    transiciones = {
        Pedido.Estado.EN_PREPARACION: Pedido.Estado.PENDIENTE,
        Pedido.Estado.LISTO: Pedido.Estado.EN_PREPARACION,
    }

    estado_anterior = transiciones.get(nuevo_estado)

    if estado_anterior is None:
        messages.error(request, "El cambio solicitado no es válido.")
        return redirect("pedidos:cocina")

    pedido = get_object_or_404(
        Pedido.objects.select_related("mesa", "mesa__local"),
        pk=pedido_id,
    )

    actualizado = Pedido.objects.filter(
        pk=pedido.pk,
        pago__isnull=False,
        estado=estado_anterior,
    ).update(estado=nuevo_estado)

    if actualizado:
        messages.success(
            request,
            f"Pedido #{pedido.pk}: "
            f"{Pedido.Estado(nuevo_estado).label}.",
        )
    else:
        messages.warning(
            request,
            "El pedido ya cambió de estado. Revisa la pantalla.",
        )

    return redirect("pedidos:cocina")
@staff_member_required
def entregas(request):
    pedidos = (
        Pedido.objects.filter(estado=Pedido.Estado.LISTO, pago__isnull=False)
        .select_related("mesa", "mesa__local")
        .prefetch_related("detalles")
        .order_by("creado", "pk")
    )

    return render(
        request,
        "pedidos/entregas.html",
        {"pedidos": pedidos},
    )


@staff_member_required
@require_POST
def marcar_entregado(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related("mesa", "mesa__local"),
        pk=pedido_id,
    )

    actualizado = Pedido.objects.filter(
        pk=pedido.pk,
        pago__isnull=False,
        estado=Pedido.Estado.LISTO,
    ).update(estado=Pedido.Estado.ENTREGADO)

    if actualizado:
        messages.success(
            request,
            f"Pedido #{pedido.pk} entregado: {pedido.mesa.local.nombre}, "
            f"Mesa {pedido.mesa.numero}.",
        )
    else:
        messages.warning(
            request,
            "El pedido ya no está en estado Listo. Revisa la pantalla.",
        )

    return redirect("pedidos:entregas")
@never_cache
def mis_pedidos(request, codigo):
    mesa = get_object_or_404(
        Mesa,
        codigo=codigo,
        activa=True,
        local__activo=True,
    )

    sincronizar_carrito(request, mesa)
    clave_pedidos = f"pedidos_{mesa.codigo}"
    pedidos_sesion = request.session.get(clave_pedidos, [])

    pedidos = (
        Pedido.objects.filter(Q(pk__in=pedidos_sesion) | Q(cliente_clave=cliente_clave(request)), mesa=mesa)
        .prefetch_related("detalles", "intentos_webpay")
        .order_by("-creado", "-pk")
    )

    from .vistas_webpay import _url_resultado
    for pedido in pedidos:
        intentos = list(pedido.intentos_webpay.all())
        ultimo = next((i for i in intentos if i.estado == 'autorizado'), intentos[0] if intentos else None)
        pedido.resultado_url = _url_resultado(ultimo.pk) if ultimo else ''

    return render(
        request,
        "pedidos/mis_pedidos.html",
        {
            "mesa": mesa,
            "pedidos": pedidos,
        },
    )
@staff_member_required
def caja(request):
    pagos = Pago.objects.select_related('cuenta__mesa', 'cuenta__mesa__local', 'pedido', 'intento_webpay').order_by('-creado')[:100]
    pendientes = IntentoWebpay.objects.filter(estado__in=ESTADOS_ACTIVOS).select_related('cuenta__mesa', 'cuenta__mesa__local', 'pedido').order_by('creado')
    cuentas = list(Cuenta.objects.filter(estado=Cuenta.Estado.ABIERTA).select_related('mesa', 'mesa__local').order_by('mesa__local__nombre', 'mesa__numero'))
    for cuenta in cuentas:
        cuenta.revision = revisar_cierre(cuenta)
    cerradas = Cuenta.objects.filter(estado=Cuenta.Estado.CERRADA).select_related('mesa', 'mesa__local').order_by('-cerrada')[:10]
    return render(request, 'pedidos/caja.html', {'pagos': pagos, 'pendientes': pendientes,
        'cuentas': cuentas, 'cerradas': cerradas})


@staff_member_required
@require_POST
def cerrar_mesa(request, cuenta_id):
    get_object_or_404(Cuenta, pk=cuenta_id)
    try:
        cuenta, cerrada = cerrar_cuenta(cuenta_id)
    except ErrorPago as exc:
        messages.warning(request, str(exc))
    else:
        if cerrada:
            messages.success(request, f'{cuenta.mesa.local.nombre}, Mesa {cuenta.mesa.numero}: cuenta '
                f'#{cuenta.pk} cerrada. Lista para una nueva visita.')
        else:
            messages.info(request, f'La cuenta #{cuenta.pk} ya estaba cerrada.')
    return redirect('pedidos:caja')
