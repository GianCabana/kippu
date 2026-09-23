from django.shortcuts import get_object_or_404, render

from mesas.models import Mesa
from pedidos.carrito import Carrito

from .models import Producto


def lista_carta(request, codigo=None):
    mesa = None
    cantidad_carrito = 0
    detalle_carrito = []
    total_carrito = 0

    if codigo is not None:
        mesa = get_object_or_404(
            Mesa,
            codigo=codigo,
            activa=True,
        )

        carrito = Carrito(request, mesa)
        detalle_carrito, total_carrito = carrito.obtener_detalle()
        cantidad_carrito = carrito.cantidad_total()

    productos = (
        Producto.objects.filter(
            disponible=True,
            categoria__activa=True,
        )
        .select_related("categoria")
        .order_by("categoria__nombre", "categoria_id", "nombre")
    )

    return render(
        request,
        "carta/lista.html",
        {
            "productos": productos,
            "mesa": mesa,
            "cantidad_carrito": cantidad_carrito,
            "detalle_carrito": detalle_carrito,
            "total_carrito": total_carrito,
        },
    )