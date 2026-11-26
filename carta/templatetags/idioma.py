from django import template

from carta.idioma import traducir

register = template.Library()


@register.filter
def traducido(objeto, campo):
    """{{ producto|traducido:"nombre" }}: nombre_en si la página está en inglés y existe; si no, nombre."""
    return traducir(objeto, campo)
