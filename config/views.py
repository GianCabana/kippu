from django.conf import settings
from django.http import Http404
from django.views.static import serve


def servir_media(request, ruta):
    """Fotos de /media: en desarrollo (DEBUG) o en la web si DJANGO_SERVIR_MEDIA=True."""
    if not (settings.DEBUG or settings.SERVIR_MEDIA):
        raise Http404
    # serve() rechaza rutas que salgan de MEDIA_ROOT (por ejemplo ../).
    respuesta = serve(request, ruta, document_root=settings.MEDIA_ROOT)
    respuesta["Cache-Control"] = "public, max-age=86400"
    return respuesta
