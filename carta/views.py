from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.db.models import Prefetch

from mesas.models import Mesa
from pedidos.carrito import Carrito
from pedidos.cierre import cerrar_si_inactiva
from pedidos.presencial import vencer_por_cobrar
from pedidos.pagos import calcular_propina, nombre_recordado, sincronizar_carrito

from .models import DiaDestacado, GrupoOpcion, OpcionProducto, Producto


@never_cache
def lista_carta(request, codigo=None):
    mesa = None
    detalle_carrito = []
    cantidad_carrito = 0
    total_carrito = 0
    requiere_mayoria_edad = False
    productos = Producto.objects.none()
    # Lunes = 0, en la hora de Chile (TIME_ZONE): el destacado cambia a medianoche del local.
    hoy = timezone.localdate().weekday()
    destacados_hoy = []

    if codigo is not None:
        mesa = get_object_or_404(
            Mesa.objects.select_related("local"),
            codigo=codigo,
            activa=True,
            local__activo=True,
        )
        vencer_por_cobrar(mesa)
        cerrar_si_inactiva(mesa)
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
        # Solo productos que ya están en la carta: la ficha de detalle se reutiliza.
        destacados_hoy = list(
            productos.filter(dias_destacado__dia=hoy).distinct().order_by("nombre")
        )

    propina_10 = calcular_propina(total_carrito, "10")
    return render(request, "carta/lista.html", {
        "productos": productos,
        "destacados_hoy": destacados_hoy,
        "dia_hoy": DiaDestacado.Dia(hoy).label,
        "mesa": mesa,
        "local": mesa.local if mesa else None,
        "detalle_carrito": detalle_carrito,
        "cantidad_carrito": cantidad_carrito,
        "total_carrito": total_carrito,
        "propina_10": propina_10,
        "total_con_propina": total_carrito + propina_10,
        "requiere_mayoria_edad": requiere_mayoria_edad,
        "nombre_pedido": nombre_recordado(request),
    })
