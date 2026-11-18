"""IVA incluido en los precios de la carta (Chile, 19 %).

Kippu no emite boleta (D-04): el comprobante solo desglosa el IVA que ya trae el precio (decisión 56).
La propina es voluntaria y no está afecta a IVA, por eso el desglose se hace solo sobre el consumo.
"""
from decimal import ROUND_HALF_UP, Decimal

TASA_IVA = Decimal("0.19")
PESO = Decimal("1")


def desglose_iva(monto):
    """Separa neto e IVA de un monto con IVA incluido, en pesos enteros: neto + iva == monto."""
    total = Decimal(monto or 0).quantize(PESO, rounding=ROUND_HALF_UP)
    neto = (total / (1 + TASA_IVA)).quantize(PESO, rounding=ROUND_HALF_UP)
    return {"total": total, "neto": neto, "iva": total - neto}
