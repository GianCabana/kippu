"""Tiempo estimado de un pedido según la cola de cocina de su local (fase 3).

Kippu no guarda cuánto tarda la cocina en cada plato, así que el tiempo se estima con una base
fija más unos minutos por cada pedido pagado que ya está en cocina. Son supuestos ajustables:
si un local los necesita distintos, se pueden pasar a la configuración del local más adelante.
"""
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist

from .models import Pedido

MINUTOS_BASE = 15          # un pedido sin cola
MINUTOS_POR_PEDIDO = 3     # cada pedido pagado que está antes en cocina
MARGEN_MINUTOS = 5         # el estimado se muestra como rango
UMBRAL_ALTA_DEMANDA = 6    # desde cuántos pedidos en cocina se avisa al cliente
EN_COCINA = (Pedido.Estado.PENDIENTE, Pedido.Estado.EN_PREPARACION)


def _cola(local, antes_de=None, excluir=None):
    pedidos = Pedido.objects.filter(mesa__local=local, pago__isnull=False, estado__in=EN_COCINA)
    if antes_de is not None:
        pedidos = pedidos.filter(pago__creado__lt=antes_de)
    if excluir is not None:
        pedidos = pedidos.exclude(pk=excluir)
    return pedidos.count()


def _rango(cola):
    minimo = MINUTOS_BASE + MINUTOS_POR_PEDIDO * cola
    return {
        "cola": cola,
        "minimo": minimo,
        "maximo": minimo + MARGEN_MINUTOS,
        "alta_demanda": cola >= UMBRAL_ALTA_DEMANDA,
    }


def espera_actual(local):
    """Para quien todavía no paga: cuánto esperaría si pagara ahora."""
    return _rango(_cola(local))


def espera_del_pedido(pedido):
    """Para un pedido pagado que sigue en cocina: rango de hora en que estaría listo. None si no aplica."""
    if pedido is None or pedido.estado not in EN_COCINA:
        return None
    try:
        pagado = pedido.pago.creado
    except ObjectDoesNotExist:
        return None
    espera = _rango(_cola(pedido.mesa.local_id, antes_de=pagado, excluir=pedido.pk))
    espera["desde"] = pagado + timedelta(minutes=espera["minimo"])
    espera["hasta"] = pagado + timedelta(minutes=espera["maximo"])
    return espera
