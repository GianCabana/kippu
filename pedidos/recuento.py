"""Recuento de caja: lo cobrado en un día (hora de Chile), por local y por método."""
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from .models import Pago, Pedido

METODOS = (Pago.Metodo.EFECTIVO, Pago.Metodo.DEBITO, Pago.Metodo.CREDITO, Pago.Metodo.WEBPAY)


def leer_fecha(texto):
    try:
        return date.fromisoformat(texto or "")
    except ValueError:
        return timezone.localdate()


def rango_del_dia(fecha):
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(fecha, time.min), zona)
    fin = timezone.make_aware(datetime.combine(fecha + timedelta(days=1), time.min), zona)
    return inicio, fin


def cobrado_por(pago):
    if pago.metodo == Pago.Metodo.WEBPAY:
        return "Webpay (cliente)"
    return pago.registrado_por.get_username() if pago.registrado_por else "Sin registro"


def recuento_del_dia(fecha, local):
    inicio, fin = rango_del_dia(fecha)
    pagos = Pago.objects.filter(creado__gte=inicio, creado__lt=fin, cuenta__mesa__local=local)
    sumas = (pagos.values("cuenta__mesa__local__nombre", "metodo")
             .annotate(cantidad=Count("id"), monto=Sum("monto")))
    anulados = (pagos.filter(pedido__estado=Pedido.Estado.CANCELADO)
                .values("cuenta__mesa__local__nombre").annotate(monto=Sum("monto")))
    anulados = {fila["cuenta__mesa__local__nombre"]: fila["monto"] for fila in anulados}
    detalle = (pagos.select_related("cuenta__mesa__local", "pedido", "registrado_por")
               .order_by("creado", "pk"))

    locales = {}
    for fila in sumas:
        nombre = fila["cuenta__mesa__local__nombre"]
        local = locales.setdefault(nombre, {"local": nombre, "por_metodo": {}, "pagos": []})
        local["por_metodo"][fila["metodo"]] = (fila["cantidad"], fila["monto"])
    for pago in detalle:
        pago.cobrado_por = cobrado_por(pago)
        locales[pago.cuenta.mesa.local.nombre]["pagos"].append(pago)

    resumen = []
    for nombre in sorted(locales):
        local = locales[nombre]
        claves = [*METODOS, *(m for m in local["por_metodo"] if m not in METODOS)]
        local["metodos"] = [
            {"clave": clave, "nombre": Pago.Metodo(clave).label,
             "cantidad": local["por_metodo"].get(clave, (0, 0))[0],
             "monto": local["por_metodo"].get(clave, (0, 0))[1]}
            for clave in claves
        ]
        local["total"] = sum(m["monto"] for m in local["metodos"])
        local["cantidad"] = sum(m["cantidad"] for m in local["metodos"])
        local["efectivo"] = local["por_metodo"].get(Pago.Metodo.EFECTIVO, (0, 0))[1]
        local["anulados"] = anulados.get(nombre, 0)
        resumen.append(local)
    return resumen
