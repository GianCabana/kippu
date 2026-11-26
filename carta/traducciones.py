"""Lista los textos marcados para traducir en las páginas del cliente (fase 3).

Reemplaza a makemessages (que necesita xgettext de GNU, ausente en Windows): lee las plantillas con
el mismo convertidor que usa Django (templatize) y el código Python con ast. La usan las pruebas
para exigir que cada texto tenga su traducción en locale/en/LC_MESSAGES/django.po.
"""
import ast
import re
from pathlib import Path

from django.conf import settings
from django.utils.translation.template import templatize  # noqa: F401 (se usa en _textos_de_plantilla)

PLANTILLAS = [
    "templates/base.html",
    "carta/templates/carta/lista.html",
    "carta/templates/carta/fragmentos/carrito.html",
    "carta/templates/carta/fragmentos/imagen_producto.html",
    "pedidos/templates/pedidos/mis_pedidos.html",
    "pedidos/templates/pedidos/fragmentos/linea_tiempo.html",
    "pedidos/templates/pedidos/fragmentos/sello_pedido.html",
    "pedidos/templates/pedidos/fragmentos/barra_webpay.html",
    "pedidos/templates/pedidos/webpay_resultado.html",
    "pedidos/templates/pedidos/webpay_salida.html",
    "pedidos/templates/pedidos/webpay_redirigir.html",
    "pedidos/templates/pedidos/webpay_retorno_sin_datos.html",
]
CODIGO = [
    "carta/models.py",
    "pedidos/carrito.py",
    "pedidos/views.py",
    "pedidos/vistas_presencial.py",
    "pedidos/presencial.py",
    "pedidos/pagos.py",
]
FUNCIONES = {"gettext", "gettext_lazy", "_", "ngettext", "ngettext_lazy", "pgettext"}
_LITERAL = r"""(u?'(?:[^'\\]|\\.)*'|u?"(?:[^"\\]|\\.)*")"""
# templatize no produce Python válido (es para xgettext): se leen solo sus llamadas.
_LLAMADA = re.compile(rf"\b(n?gettext)\(\s*{_LITERAL}(?:\s*,\s*{_LITERAL})?")


def _textos_de_plantilla(fuente):
    textos = []
    for funcion, msgid, plural in _LLAMADA.findall(templatize(fuente)):
        texto = ast.literal_eval(msgid)
        textos.append((texto, ast.literal_eval(plural) if funcion == "ngettext" and plural else None))
    return textos


def _textos_de_python(fuente):
    """[(msgid, msgid_plural o None)] de las llamadas gettext(...) con texto literal."""
    textos = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
        if nombre not in FUNCIONES or not nodo.args:
            continue
        literales = [a.value for a in nodo.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if not literales:
            continue
        if nombre.startswith("ngettext"):
            textos.append((literales[0], literales[1]))
        else:
            textos.append((literales[0], None))
    return textos


def textos_marcados():
    """Conjunto de (msgid, msgid_plural) de plantillas y código del cliente."""
    base = Path(settings.BASE_DIR)
    textos = set()
    for ruta in PLANTILLAS:
        textos.update(_textos_de_plantilla((base / ruta).read_text(encoding="utf-8")))
    for ruta in CODIGO:
        textos.update(_textos_de_python((base / ruta).read_text(encoding="utf-8")))
    return textos
