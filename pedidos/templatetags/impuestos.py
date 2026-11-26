from django import template

from pedidos.impuestos import desglose_iva

register = template.Library()


@register.filter
def iva_incluido(monto):
    """{% with d=monto|iva_incluido %} → d.neto y d.iva en pesos enteros."""
    return desglose_iva(monto)
