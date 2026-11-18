from django import template

from pedidos.espera import espera_actual, espera_del_pedido

register = template.Library()


@register.filter
def espera_estimada(pedido):
    """{% with e=pedido|espera_estimada %}: e.desde, e.hasta y e.alta_demanda, o None."""
    return espera_del_pedido(pedido)


@register.filter
def espera_en_local(local):
    """{% with e=mesa.local|espera_en_local %}: e.minimo, e.maximo y e.alta_demanda."""
    return espera_actual(local)
