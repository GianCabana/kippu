"""Pruebas de lo que ve cada uno en el resultado del pago."""

from django.test import TestCase
from django.urls import reverse

from . import test_webpay_demo as base
from .vistas_webpay import _url_resultado


class ResultadoPagoTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def test_el_comensal_vuelve_a_la_carta_y_nunca_ve_la_caja(self):
        intento = self.crear()
        self.aprobar(intento)

        pagina = self.client.get(_url_resultado(intento.pk))

        self.assertContains(pagina, "Pago autorizado")
        self.assertContains(pagina, "Volver a la carta")
        self.assertContains(pagina, "Ver mis pedidos")
        self.assertNotContains(pagina, "Volver a Caja")
        self.assertNotContains(pagina, reverse("pedidos:caja"))

    def test_el_personal_vuelve_a_caja(self):
        intento = self.crear()

        pagina = self.operador.get(_url_resultado(intento.pk))

        self.assertContains(pagina, "Volver a Caja")
        self.assertNotContains(pagina, "Volver a la carta")
