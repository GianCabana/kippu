"""Fase 3: el comprobante desglosa el IVA incluido del consumo (no de la propina), en pesos enteros."""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..impuestos import desglose_iva
from ..models import Pedido
from . import test_webpay_demo as base
from .test_pago_presencial import PagoPresencialBase
from ..vistas_webpay import _url_resultado


class DesgloseIvaTests(SimpleTestCase):
    def test_neto_mas_iva_es_el_total(self):
        for monto in (1, 19, 119, 2200, 5900, 13900, 15290, 123457):
            with self.subTest(monto=monto):
                d = desglose_iva(Decimal(monto))
                self.assertEqual(d["neto"] + d["iva"], Decimal(monto))
                self.assertEqual(d["neto"], d["neto"].to_integral_value())

    def test_valores_conocidos(self):
        self.assertEqual(desglose_iva(Decimal("11900")), {"total": Decimal("11900"), "neto": Decimal("10000"), "iva": Decimal("1900")})
        self.assertEqual(desglose_iva(Decimal("5900"))["neto"], Decimal("4958"))
        self.assertEqual(desglose_iva(Decimal("5900"))["iva"], Decimal("942"))

    def test_cero_y_vacio(self):
        self.assertEqual(desglose_iva(None)["iva"], Decimal("0"))
        self.assertEqual(desglose_iva(Decimal("0"))["neto"], Decimal("0"))


class IvaEnComprobanteWebpayTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def comprobante(self, propina):
        salida = self.client.post(reverse("pedidos:webpay_cliente", args=[self.mesa.codigo]), {"propina": propina})
        intento = salida.context["intento"]
        self.aprobar(intento)
        return self.client.get(_url_resultado(intento.pk)).content.decode()

    def test_desglosa_el_consumo_sin_propina(self):
        # 2 × $3.500 = $7.000 → neto $5.882 + IVA $1.118
        html = self.comprobante("0")

        self.assertIn("IVA (19 %) incluido", html)
        self.assertIn("$5.882", html)
        self.assertIn("$1.118", html)

    def test_la_propina_no_lleva_iva(self):
        html = self.comprobante("10")

        self.assertIn("$1.118", html)
        self.assertIn("la propina no está afecta a IVA", html)


class IvaEnMisPedidosTests(PagoPresencialBase):
    def test_pago_en_caja_muestra_el_iva(self):
        pedido = self.pedido(propina="0")
        self.cobrar(pedido)

        html = self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo])).content.decode()

        self.assertIn("IVA (19 %) incluido", html)
        self.assertIn("$5.882", html)
        self.assertIn("$1.118", html)
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, Pedido.Estado.PENDIENTE)
