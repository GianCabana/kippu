"""Inicio desde el carrito; retorno público autenticado por token + consulta al proveedor."""
from urllib.parse import urlencode, urlsplit
from uuid import UUID
from datetime import timedelta
from django.utils import timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import Cuenta, IntentoWebpay, Pago, Pedido
from mesas.models import Mesa
from .pagos import ErrorPago, ESTADOS_ACTIVOS, crear_intento_cliente, resolver_intento, sincronizar_carrito, reintentar_pago, consumir_formulario

SALT = "kippu-comprobante-demo-v1"


def _es_personal(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


def _firma(intento_id):
    return signing.dumps({"intento": intento_id}, salt=SALT)


def _url_resultado(intento_id):
    return reverse("pedidos:webpay_resultado", args=[intento_id]) + "?" + urlencode({"firma": _firma(intento_id)})


def _autorizar_resultado(request, intento_id):
    if _es_personal(request):
        return
    firma = request.POST.get("firma") or request.GET.get("firma")
    try:
        datos = signing.loads(firma or "", salt=SALT, max_age=3600)
        if datos != {"intento": intento_id}:
            raise Http404
    except signing.BadSignature:
        raise Http404 from None


def _privado(response):
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@never_cache
@staff_member_required
@require_POST
def iniciar(request, cuenta_id):
    messages.info(request, 'El pago ahora se realiza desde el carrito del cliente, antes de preparar el pedido.')
    return redirect('pedidos:caja')


@never_cache
@require_POST
def iniciar_cliente(request, codigo):
    mesa = get_object_or_404(Mesa, codigo=codigo, activa=True)
    return_url = getattr(settings, 'WEBPAY_RETURN_URL', '') or request.build_absolute_uri(reverse('pedidos:webpay_retorno'))
    parsed = urlsplit(return_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return HttpResponseBadRequest('Configura una URL de retorno válida.')
    try:
        intento, nuevo = crear_intento_cliente(request, codigo, return_url)
    except ErrorPago as exc:
        messages.error(request, str(exc))
        return redirect('carta:por_mesa', codigo=mesa.codigo)
    if nuevo:
        return _privado(render(request, 'pedidos/webpay_salida.html', {
            'intento': intento, 'resultado_url': _url_resultado(intento.pk), 'firma': _firma(intento.pk)}))
    return _privado(redirect(_url_resultado(intento.pk)))


@never_cache
@csrf_exempt
@require_http_methods(["GET", "POST"])
def retorno(request):
    # Única excepción CSRF. No basta lo enviado por el navegador para registrar un pago.
    datos = request.POST if request.method == "POST" else request.GET
    normal, abortado = datos.get("token_ws"), datos.get("TBK_TOKEN")
    if normal and abortado and normal != abortado:
        return HttpResponseBadRequest("Retorno no válido.")
    token = normal or abortado
    if token:
        if len(token) != 64:
            raise Http404
        intento = get_object_or_404(IntentoWebpay, token=token)
    else:
        orden, sesion = datos.get("TBK_ORDEN_COMPRA"), datos.get("TBK_ID_SESION")
        try:
            sesion = UUID(sesion or "")
        except (ValueError, TypeError, AttributeError):
            raise Http404 from None
        intento = get_object_or_404(IntentoWebpay, orden_compra=orden, session_id=sesion)
    # Si el retorno incluye referencias adicionales, también deben coincidir.
    if datos.get("TBK_ORDEN_COMPRA") and datos["TBK_ORDEN_COMPRA"] != intento.orden_compra:
        raise Http404
    if datos.get("TBK_ID_SESION") and datos["TBK_ID_SESION"] != str(intento.session_id):
        raise Http404
    # Anulación, timeout o retorno de error: consultar y abandonar, nunca confirmar.
    resolver_intento(intento.pk, confirmar=bool(normal and not abortado),
        cancelar=bool(abortado or not token))
    return _privado(redirect(_url_resultado(intento.pk)))


@never_cache
@require_GET
def resultado(request, intento_id):
    _autorizar_resultado(request, intento_id)
    intento = get_object_or_404(IntentoWebpay.objects.select_related("cuenta__mesa", "pedido"), pk=intento_id)
    pago = Pago.objects.filter(intento_webpay=intento).first()
    if pago and intento.pedido_id:
        sincronizar_carrito(request, intento.cuenta.mesa)
    return _privado(render(request, "pedidos/webpay_resultado.html", {
        "intento": intento, "pago": pago, "firma": _firma(intento.pk),
        "personal": _es_personal(request),
        "pendiente": intento.estado in ESTADOS_ACTIVOS,
        "puede_reintentar": bool(not pago and intento.pedido_id
            and intento.pedido.estado == Pedido.Estado.SIN_PAGAR
            and intento.cuenta.estado == Cuenta.Estado.ABIERTA),
        "enviado_cocina": bool(pago and intento.pedido_id and intento.pedido.estado in (Pedido.Estado.PENDIENTE, Pedido.Estado.EN_PREPARACION, Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO)),
    }))


@never_cache
@require_POST
def verificar(request, intento_id):
    _autorizar_resultado(request, intento_id)
    get_object_or_404(IntentoWebpay, pk=intento_id)
    resolver_intento(intento_id)  # Confirmación solo si antes hubo un retorno normal.
    return redirect(_url_resultado(intento_id))


@never_cache
@require_POST
def reintentar(request, intento_id):
    _autorizar_resultado(request, intento_id)
    get_object_or_404(IntentoWebpay, pk=intento_id)
    return_url = getattr(settings, 'WEBPAY_RETURN_URL', '') or request.build_absolute_uri(reverse('pedidos:webpay_retorno'))
    parsed = urlsplit(return_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return HttpResponseBadRequest('Configura una URL de retorno válida.')
    try:
        intento, nuevo = reintentar_pago(intento_id, request.user, return_url)
    except ErrorPago as exc:
        messages.warning(request, str(exc))
        return _privado(redirect(_url_resultado(intento_id)))
    if (intento.estado == IntentoWebpay.Estado.INICIADO and not intento.formulario_abierto
            and not intento.cancelacion_solicitada):
        return _privado(render(request, 'pedidos/webpay_salida.html', {
            'intento':intento, 'resultado_url':_url_resultado(intento.pk), 'firma':_firma(intento.pk)}))
    return _privado(redirect(_url_resultado(intento.pk)))


@never_cache
@require_POST
def cancelar(request, intento_id):
    _autorizar_resultado(request, intento_id)
    get_object_or_404(IntentoWebpay, pk=intento_id)
    resolver_intento(intento_id, cancelar=True)
    return _privado(redirect(_url_resultado(intento_id)))


@never_cache
@require_POST
def abrir(request, intento_id):
    _autorizar_resultado(request, intento_id)
    get_object_or_404(IntentoWebpay, pk=intento_id)
    intento, permitido = consumir_formulario(intento_id)
    if not permitido:
        messages.info(request, 'Este enlace ya se abrió o no está vigente. Usa Reintentar pago para generar uno nuevo.')
        return _privado(redirect(_url_resultado(intento.pk)))
    return _privado(render(request, 'pedidos/webpay_redirigir.html', {
        'intento':intento, 'resultado_url':_url_resultado(intento.pk)}))
