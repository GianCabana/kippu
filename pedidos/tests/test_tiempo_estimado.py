"""Fase 3: tiempo estimado según la cola de cocina del local y aviso de alta demanda."""
from datetime import timedelta

from django.urls import reverse

from .. import espera
from ..models import Pedido
from ..vistas_webpay import _url_resultado
from .test_pago_presencial import PagoPresencialBase
from . import test_webpay_demo as base


class TiempoEstimadoTests(PagoPresencialBase):
    aprobar = base.PagoPrevioTests.aprobar

    def pagado(self):
        """Un pedido pagado en caja: queda pendiente en cocina."""
        self.llenar(self.client)
        pedido = self.pedido()
        self.cobrar(pedido)
        pedido.refresh_from_db()
        return pedido

    def carta(self):
        self.llenar(self.client)
        return self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo])).content.decode()

    def test_sin_cola_usa_la_base(self):
        e = espera.espera_actual(self.mesa.local)

        self.assertEqual((e["cola"], e["minimo"], e["maximo"]), (0, espera.MINUTOS_BASE, espera.MINUTOS_BASE + espera.MARGEN_MINUTOS))
        self.assertFalse(e["alta_demanda"])

    def test_cada_pedido_en_cocina_suma_minutos(self):
        self.pagado()
        self.pagado()

        e = espera.espera_actual(self.mesa.local)

        self.assertEqual(e["cola"], 2)
        self.assertEqual(e["minimo"], espera.MINUTOS_BASE + 2 * espera.MINUTOS_POR_PEDIDO)

    def test_listos_y_sin_pagar_no_cuentan(self):
        listo = self.pagado()
        Pedido.objects.filter(pk=listo.pk).update(estado=Pedido.Estado.LISTO)
        self.llenar(self.client)
        self.pedido()  # por cobrar: todavía no está en cocina

        self.assertEqual(espera.espera_actual(self.mesa.local)["cola"], 0)

    def test_el_pedido_solo_cuenta_los_que_pagaron_antes(self):
        primero = self.pagado()
        segundo = self.pagado()

        e1 = espera.espera_del_pedido(primero)
        e2 = espera.espera_del_pedido(segundo)

        self.assertEqual(e1["cola"], 0)
        self.assertEqual(e2["cola"], 1)
        self.assertEqual(e1["desde"], primero.pago.creado + timedelta(minutes=espera.MINUTOS_BASE))

    def test_sin_espera_si_ya_salio_de_cocina(self):
        pedido = self.pagado()
        Pedido.objects.filter(pk=pedido.pk).update(estado=Pedido.Estado.LISTO)
        pedido.refresh_from_db()

        self.assertIsNone(espera.espera_del_pedido(pedido))
        self.assertIsNone(espera.espera_del_pedido(None))

    def test_mis_pedidos_muestra_la_hora_estimada(self):
        self.pagado()

        html = self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo])).content.decode()

        self.assertIn("Listo aprox. entre las", html)

    def test_comprobante_webpay_muestra_la_hora_estimada(self):
        self.llenar(self.client)
        intento = self.crear()
        self.aprobar(intento)

        html = self.client.get(_url_resultado(intento.pk)).content.decode()

        self.assertIn("Listo aprox. entre las", html)

    def test_carrito_sin_aviso_con_poca_cola(self):
        self.pagado()

        self.assertNotIn("Hay muchos pedidos en cocina", self.carta())

    def test_carrito_avisa_cuando_hay_alta_demanda(self):
        for _ in range(espera.UMBRAL_ALTA_DEMANDA):
            self.pagado()

        html = self.carta()

        self.assertIn("Hay muchos pedidos en cocina", html)
        minimo = espera.MINUTOS_BASE + espera.UMBRAL_ALTA_DEMANDA * espera.MINUTOS_POR_PEDIDO
        self.assertIn(f"{minimo}–{minimo + espera.MARGEN_MINUTOS} minutos", html)
