"""Idioma según el teléfono, solo en las páginas del cliente (fase 3).

Las páginas que se abren desde el QR (carta, carrito, pago, comprobante y Mis pedidos) usan el idioma
del navegador (encabezado Accept-Language): inglés si el teléfono está en inglés y español en todo lo
demás. El admin y los paneles del personal siguen siempre en español.
"""
from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers

RUTAS_CLIENTE = ("/mesa/", "/pedidos/mesa/", "/pedidos/webpay/")


def es_pagina_del_cliente(ruta):
    return ruta == "/" or ruta.startswith(RUTAS_CLIENTE)


class IdiomaDelClienteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cliente = es_pagina_del_cliente(request.path)
        idioma = translation.get_language_from_request(request) if cliente else settings.LANGUAGE_CODE
        # override devuelve el idioma anterior al terminar: no queda pegado al hilo para otra petición.
        with translation.override(idioma):
            request.LANGUAGE_CODE = translation.get_language()
            respuesta = self.get_response(request)
        if cliente:
            # La misma URL cambia según el idioma del teléfono: ningún caché debe mezclarlas.
            patch_vary_headers(respuesta, ("Accept-Language",))
            respuesta.headers.setdefault("Content-Language", request.LANGUAGE_CODE)
        return respuesta
