"""Textos de la carta en el idioma activo (fase 3).

La carta se escribe en español; los campos *_en son opcionales. Si el cliente ve la carta en inglés
y el campo en inglés está vacío, se muestra el texto en español en vez de dejarlo en blanco.
"""
from django.utils.translation import get_language


def en_ingles():
    return (get_language() or "").startswith("en")


def traducir(objeto, campo):
    texto = getattr(objeto, campo, "")
    if objeto is not None and en_ingles():
        return getattr(objeto, f"{campo}_en", "") or texto
    return texto
