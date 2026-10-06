"""Regreso desde Webpay sin datos de Transbank ("Intentar nuevamente" tras un rechazo)."""

import hashlib

from django.test import Client, TestCase
from django.urls import reverse

from . import test_webpay_demo as base
from .models import IntentoWebpay, Pedido
from .vistas_webpay import _url_resultado


class RetornoSinDatosTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear

    def retorno(self, client=None):
        return (client or self.client).get(reverse("pedidos:webpay_retorno"))

    def test_sin_sesion_muestra_la_pagina_de_kippu(self):
        respuesta = self.retorno(Client())

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "pedidos/webpay_retorno_sin_datos.html")
        self.assertContains(respuesta, "No pudimos completar el regreso desde Webpay")
        self.assertContains(respuesta, reverse("carta:lista"))
        self.assertNotContains(respuesta, "URLconf")
        self.assertFalse(IntentoWebpay.objects.exists())

    def test_con_intento_en_la_sesion_lleva_a_su_resultado_sin_resolverlo(self):
        intento = self.crear()
        estado = intento.estado

        respuesta = self.retorno()

        self.assertRedirects(respuesta, _url_resultado(intento.pk), fetch_redirect_response=False)
        intento.refresh_from_db()
        self.assertEqual(intento.estado, estado)
        self.sdk.status.assert_not_called()
        self.sdk.commit.assert_not_called()

    def test_otra_sesion_no_llega_al_intento_ajeno(self):
        intento = self.crear()

        respuesta = self.retorno(Client())

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, _url_resultado(intento.pk).split("?")[0])

    def test_sin_intento_pero_con_pedido_ofrece_mis_pedidos_de_su_mesa(self):
        clave = hashlib.sha256(self.client.session.session_key.encode()).hexdigest()
        Pedido.objects.create(mesa=self.mesa, cliente_clave=clave)

        respuesta = self.retorno()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))
        self.assertContains(respuesta, reverse("carta:por_mesa", args=[self.mesa.codigo]))
