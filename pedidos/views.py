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

from .carrito import Carrito
from .cierre import revisar_cierre, cerrar_cuenta
from .pagos import ErrorPago


@require_POST
@transaction.atomic
def agregar_al_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa.objects.select_for_update(),
        codigo=codigo,
        activa=True,
    )

    activo = intento_activo(request, mesa)
    if activo:
        from .vistas_webpay import _url_resultado
        messages.info(request, 'Resuelve el pago en curso antes de modificar el carrito.')
        return redirect(_url_resultado(activo.pk))
    sincronizar_carrito(request, mesa)

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
        disponible=True,
        categoria__activa=True,
    )

    carrito = Carrito(request, mesa)

    if carrito.agregar(producto):
        renovar_carrito(request, mesa)
        messages.success(
            request,
            f"Agregaste {producto.nombre}.",
        )
    else:
        messages.warning(
            request,
            "Puedes agregar hasta 20 unidades de cada producto.",
        )

    return redirect(
        "carta:por_mesa",
        codigo=mesa.codigo,
    )


@require_POST
@transaction.atomic
def quitar_del_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa.objects.select_for_update(),
        codigo=codigo,
        activa=True,
    )

    activo = intento_activo(request, mesa)
    if activo:
        from .vistas_webpay import _url_resultado
        messages.info(request, 'Resuelve el pago en curso antes de modificar el carrito.')
        return redirect(_url_resultado(activo.pk))
    sincronizar_carrito(request, mesa)

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
    )

    carrito = Carrito(request, mesa)
    carrito.quitar(producto)
    renovar_carrito(request, mesa)

    messages.success(
        request,
        f"Quitaste una unidad de {producto.nombre}.",
    )

    return redirect(
        "carta:por_mesa",
        codigo=mesa.codigo,
    )
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
        .select_related("mesa")
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

    pedido = get_object_or_404(Pedido, pk=pedido_id)

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
        .select_related("mesa")
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
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    actualizado = Pedido.objects.filter(
        pk=pedido.pk,
        pago__isnull=False,
        estado=Pedido.Estado.LISTO,
    ).update(estado=Pedido.Estado.ENTREGADO)

    if actualizado:
        messages.success(
            request,
            f"Pedido #{pedido.pk} entregado a Mesa {pedido.mesa.numero}.",
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
    pagos = Pago.objects.select_related('cuenta__mesa', 'pedido', 'intento_webpay').order_by('-creado')[:100]
    pendientes = IntentoWebpay.objects.filter(estado__in=ESTADOS_ACTIVOS).select_related('cuenta__mesa', 'pedido').order_by('creado')
    cuentas = list(Cuenta.objects.filter(estado=Cuenta.Estado.ABIERTA).select_related('mesa').order_by('mesa__numero'))
    for cuenta in cuentas:
        cuenta.revision = revisar_cierre(cuenta)
    cerradas = Cuenta.objects.filter(estado=Cuenta.Estado.CERRADA).select_related('mesa').order_by('-cerrada')[:10]
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
            messages.success(request, f'Mesa {cuenta.mesa.numero}: cuenta #{cuenta.pk} cerrada. Lista para una nueva visita.')
        else:
            messages.info(request, f'La cuenta #{cuenta.pk} ya estaba cerrada.')
    return redirect('pedidos:caja')
