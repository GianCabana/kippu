"""Fila 55: el nombre opcional del pedido sale en el comprobante de Webpay y en el aviso de pago en caja."""
from django.test import TestCase
from django.urls import reverse

from . import test_nombre_pedido as nombres
from . import test_webpay_demo as base
from .models import Pedido
from .vistas_webpay import _url_resultado


class NombreEnComprobanteTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar
    iniciar = nombres.NombrePedidoTests.iniciar
    crear = nombres.NombrePedidoTests.crear

    def comprobante(self, nombre):
        intento = self.crear(nombre)
        self.aprobar(intento)
        return self.client.get(_url_resultado(intento.pk))

    def por_cobrar(self, nombre):
        datos = {"propina": "0", "nombre": nombre}
        self.client.post(reverse("pedidos:pagar_en_caja", args=[self.mesa.codigo]), datos)
        pedido = Pedido.objects.get(estado=Pedido.Estado.POR_COBRAR)
        return pedido, self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

    def test_comprobante_webpay_muestra_el_nombre(self):
        respuesta = self.comprobante("Ana")

        self.assertContains(respuesta, 'Pago autorizado')
        self.assertContains(respuesta, '<p class="tk__nombre">Para <strong>Ana</strong></p>', html=True)

    def test_comprobante_webpay_sin_nombre_no_muestra_nada(self):
        respuesta = self.comprobante("")

        self.assertContains(respuesta, 'Pago autorizado')
        self.assertNotContains(respuesta, "tk__nombre")

    def test_comprobante_escapa_el_nombre(self):
        intento = self.crear("Ana")
        self.aprobar(intento)
        Pedido.objects.filter(pk=intento.pedido_id).update(nombre="<b>Ana</b>")

        respuesta = self.client.get(_url_resultado(intento.pk))

        self.assertContains(respuesta, "&lt;b&gt;Ana&lt;/b&gt;")
        self.assertNotContains(respuesta, "<b>Ana</b>")

    def test_aviso_de_caja_muestra_el_nombre(self):
        pedido, respuesta = self.por_cobrar("Ana")

        self.assertContains(
            respuesta,
            f"Pregunta por el <strong>pedido #{pedido.pk}</strong>, a nombre de <strong>Ana</strong>.",
        )

    def test_aviso_de_caja_sin_nombre_queda_como_antes(self):
        pedido, respuesta = self.por_cobrar("")

        self.assertContains(respuesta, f"Pregunta por el <strong>pedido #{pedido.pk}</strong>. Tu pedido")
        self.assertNotContains(respuesta, "a nombre de")
