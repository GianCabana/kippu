"""Vistas del pago presencial en caja (D-07): crear y cancelar desde el teléfono, cobrar y cancelar en caja."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import Pedido
from .pagos import ErrorPago, recordar_nombre
from .presencial import YaPorCobrar, cancelar_por_cobrar, cobrar_por_cobrar, crear_por_cobrar
from .views import _mesa_del_cliente, _pedidos_del_navegador


@never_cache
@require_POST
def pagar_en_caja(request, codigo):
    mesa = _mesa_del_cliente(codigo)
    recordar_nombre(request)
    try:
        pedido = crear_por_cobrar(request, codigo)
    except YaPorCobrar as exc:
        messages.info(request, str(exc))
        return redirect('pedidos:mis_pedidos', codigo=mesa.codigo)
    except ErrorPago as exc:
        messages.error(request, str(exc))
        return redirect('carta:por_mesa', codigo=mesa.codigo)
    messages.success(request, f'Pedido #{pedido.pk} enviado a caja. Acércate a pagar para que pase a cocina.')
    return redirect('pedidos:mis_pedidos', codigo=mesa.codigo)


@never_cache
@require_POST
def cancelar_del_cliente(request, codigo, pedido_id):
    mesa = _mesa_del_cliente(codigo)
    # Solo los pedidos de este navegador: el de otra persona da 404.
    pedido = get_object_or_404(_pedidos_del_navegador(request, mesa), pk=pedido_id)
    if cancelar_por_cobrar(pedido.pk):
        messages.success(request, f'Cancelaste el pedido #{pedido.pk}.')
    else:
        messages.info(request, f'El pedido #{pedido.pk} ya no se puede cancelar desde aquí.')
    return redirect('pedidos:mis_pedidos', codigo=mesa.codigo)


@staff_member_required
@require_POST
def cobrar(request, pedido_id):
    # Pendiente D-3: el pedido llega por la URL hasta ligar usuario y local.
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    try:
        pago, nuevo = cobrar_por_cobrar(pedido.pk, request.POST.get('metodo', ''), request.user)
    except ErrorPago as exc:
        messages.warning(request, str(exc))
    else:
        if nuevo:
            messages.success(request, f'Pedido #{pedido.pk} cobrado ({pago.get_metodo_display().lower()}). '
                                      'Ya está en cocina.')
        else:
            messages.info(request, f'El pedido #{pedido.pk} ya estaba cobrado.')
    return redirect('pedidos:caja')


@staff_member_required
@require_POST
def cancelar_en_caja(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if cancelar_por_cobrar(pedido.pk):
        messages.success(request, f'Pedido #{pedido.pk} cancelado. No pasó a cocina.')
    else:
        messages.info(request, f'El pedido #{pedido.pk} ya no estaba por cobrar.')
    return redirect('pedidos:caja')
