from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.db.models import Prefetch

from mesas.models import Mesa
from pedidos.carrito import Carrito
from pedidos.pagos import sincronizar_carrito

from .models import GrupoOpcion, OpcionProducto, Producto


@never_cache
def lista_carta(request, codigo=None):
    mesa = None
    detalle_carrito = []
    cantidad_carrito = 0
    total_carrito = 0
    requiere_mayoria_edad = False
    productos = Producto.objects.none()

    if codigo is not None:
        mesa = get_object_or_404(
            Mesa.objects.select_related("local"),
            codigo=codigo,
            activa=True,
            local__activo=True,
        )
        sincronizar_carrito(request, mesa)
        carrito = Carrito(request, mesa)
        detalle_carrito, total_carrito = carrito.obtener_detalle()
        cantidad_carrito = carrito.cantidad_total()
        requiere_mayoria_edad = any(
            item["producto"].requiere_mayoria_edad
            for item in detalle_carrito
        )
        grupos_opciones = GrupoOpcion.objects.filter(
            activo=True,
        ).prefetch_related(
            Prefetch(
                "opciones",
                queryset=OpcionProducto.objects.filter(activa=True).order_by(
                    "orden", "pk"
                ),
            )
        ).order_by("orden", "pk")
        productos = (
            Producto.objects.filter(
                disponible=True,
                categoria__activa=True,
                categoria__local=mesa.local,
            )
            .select_related("categoria", "categoria__local")
            .prefetch_related(
                Prefetch("grupos_opciones", queryset=grupos_opciones)
            )
            .order_by("categoria__nombre", "categoria_id", "nombre")
        )

    return render(request, "carta/lista.html", {
        "productos": productos,
        "mesa": mesa,
        "local": mesa.local if mesa else None,
        "detalle_carrito": detalle_carrito,
        "cantidad_carrito": cantidad_carrito,
        "total_carrito": total_carrito,
        "requiere_mayoria_edad": requiere_mayoria_edad,
    })
