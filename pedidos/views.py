from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import transaction

from .models import Cuenta, DetallePedido, Pedido

from carta.models import Producto
from mesas.models import Mesa
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .carrito import Carrito


@require_POST
def agregar_al_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa,
        codigo=codigo,
        activa=True,
    )

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
        disponible=True,
        categoria__activa=True,
    )

    carrito = Carrito(request, mesa)

    if carrito.agregar(producto):
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
def quitar_del_carrito(request, codigo, producto_id):
    mesa = get_object_or_404(
        Mesa,
        codigo=codigo,
        activa=True,
    )

    producto = get_object_or_404(
        Producto,
        pk=producto_id,
    )

    carrito = Carrito(request, mesa)
    carrito.quitar(producto)

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
    with transaction.atomic():
        # Coordina los pedidos simultáneos de una misma mesa.
        mesa = get_object_or_404(
            Mesa.objects.select_for_update(),
            codigo=codigo,
            activa=True,
        )

        carrito = Carrito(request, mesa)

        if not carrito.productos:
            messages.warning(request, "Tu carrito está vacío.")
            return redirect("carta:por_mesa", codigo=mesa.codigo)

        productos = list(
            Producto.objects.filter(
                pk__in=carrito.productos.keys(),
                disponible=True,
                categoria__activa=True,
            )
        )

        if len(productos) != len(carrito.productos):
            messages.error(
                request,
                "Algún producto ya no está disponible. "
                "Quítalo del carrito antes de enviar el pedido.",
            )
            return redirect("carta:por_mesa", codigo=mesa.codigo)

        for producto in productos:
            cantidad = carrito.productos[str(producto.pk)]

            if (
                type(cantidad) is not int
                or cantidad < 1
                or cantidad > Carrito.MAXIMO_POR_PRODUCTO
            ):
                messages.error(
                    request,
                    "Hay una cantidad inválida en el carrito.",
                )
                return redirect("carta:por_mesa", codigo=mesa.codigo)

        cuenta, _ = Cuenta.objects.get_or_create(
            mesa=mesa,
            estado=Cuenta.Estado.ABIERTA,
        )

        pedido = Pedido.objects.create(
            mesa=mesa,
            cuenta=cuenta,
        )

        DetallePedido.objects.bulk_create(
            [
                DetallePedido(
                    pedido=pedido,
                    producto=producto,
                    nombre_producto=producto.nombre,
                    precio_unitario=producto.precio,
                    cantidad=carrito.productos[str(producto.pk)],
                )
                for producto in productos
            ]
        )

    clave_pedidos = f"pedidos_{mesa.codigo}"
    pedidos_sesion = request.session.get(clave_pedidos, [])
    pedidos_sesion.append(pedido.pk)
    request.session[clave_pedidos] = pedidos_sesion

    carrito.productos = {}
    carrito.guardar()

    messages.success(
        request,
        f"¡Pedido #{pedido.pk} enviado! Puedes seguir su estado aquí.",
    )

    return redirect("pedidos:mis_pedidos", codigo=mesa.codigo)
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
        Pedido.objects.filter(estado=Pedido.Estado.LISTO)
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
def mis_pedidos(request, codigo):
    mesa = get_object_or_404(
        Mesa,
        codigo=codigo,
        activa=True,
    )

    clave_pedidos = f"pedidos_{mesa.codigo}"
    pedidos_sesion = request.session.get(clave_pedidos, [])

    pedidos = (
        Pedido.objects.filter(
            mesa=mesa,
            pk__in=pedidos_sesion,
        )
        .prefetch_related("detalles")
        .order_by("-creado", "-pk")
    )

    return render(
        request,
        "pedidos/mis_pedidos.html",
        {
            "mesa": mesa,
            "pedidos": pedidos,
        },
    )