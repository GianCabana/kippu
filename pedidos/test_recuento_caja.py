"""Recuento de caja (fila 69): lo cobrado en un día, por local y por método, y quién cobró."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from mesas.models import Local, Mesa, PerfilPersonal

from .models import Cuenta, Pago, Pedido

SANTIAGO = ZoneInfo("America/Santiago")


def a_las(dia, hora, minuto=0):
    return datetime(2026, 11, dia, hora, minuto, tzinfo=SANTIAGO)


class RecuentoCajaTests(TestCase):
    def setUp(self):
        self.local = Local.objects.create(nombre="Local Recuento", slug="local-recuento")
        self.mesa = Mesa.objects.create(local=self.local, numero=31)
        self.cuenta = Cuenta.objects.create(mesa=self.mesa)
        self.cajera = get_user_model().objects.create_user(username="cajera_ana", password="Pruebas123!", is_staff=True)
        PerfilPersonal.objects.create(usuario=self.cajera, local=self.local)
        self.client.force_login(self.cajera)
        self.url = reverse("pedidos:recuento_caja")

    def pagar(self, metodo, monto, cuando, cuenta=None, estado="entregado", usuario=None):
        cuenta = cuenta or self.cuenta
        pedido = Pedido.objects.create(mesa=cuenta.mesa, cuenta=cuenta, estado=estado)
        pago = Pago.objects.create(cuenta=cuenta, pedido=pedido, monto=monto, metodo=metodo,
                                   registrado_por=None if metodo == "webpay" else (usuario or self.cajera))
        Pago.objects.filter(pk=pago.pk).update(creado=cuando)
        return pago

    def recuento(self, fecha="2026-11-16"):
        return self.client.get(self.url, {"fecha": fecha})

    def resumen(self, respuesta, local="Local Recuento"):
        return next(r for r in respuesta.context["locales"] if r["local"] == local)

    def test_suma_por_metodo_solo_el_dia_elegido(self):
        self.pagar("efectivo", 5000, a_las(16, 12))
        self.pagar("efectivo", 3000, a_las(16, 20))
        self.pagar("debito", 7000, a_las(16, 13))
        self.pagar("webpay", 10000, a_las(16, 14))
        self.pagar("efectivo", 99000, a_las(15, 21))

        resumen = self.resumen(self.recuento())

        metodos = {m["clave"]: (m["cantidad"], m["monto"]) for m in resumen["metodos"]}
        self.assertEqual(metodos["efectivo"], (2, 8000))
        self.assertEqual(metodos["debito"], (1, 7000))
        self.assertEqual(metodos["credito"], (0, 0))
        self.assertEqual(metodos["webpay"], (1, 10000))
        self.assertEqual(resumen["total"], 25000)
        self.assertEqual(resumen["efectivo"], 8000)
        self.assertEqual(resumen["cantidad"], 4)

    def test_el_dia_se_corta_a_medianoche_en_hora_de_chile(self):
        self.pagar("efectivo", 1000, a_las(15, 23, 59))
        self.pagar("efectivo", 2000, a_las(16, 0, 0))
        self.pagar("efectivo", 4000, a_las(16, 23, 59))
        self.pagar("efectivo", 8000, a_las(17, 0, 0))

        self.assertEqual(self.resumen(self.recuento())["total"], 6000)

    def test_muestra_quien_cobro(self):
        self.pagar("efectivo", 5000, a_las(16, 12))
        self.pagar("webpay", 7000, a_las(16, 13))

        respuesta = self.recuento()

        self.assertContains(respuesta, "cajera_ana")
        self.assertContains(respuesta, "Webpay (cliente)")

    def test_anulado_con_pago_se_suma_y_se_marca(self):
        self.pagar("efectivo", 5000, a_las(16, 12), estado="cancelado")

        respuesta = self.recuento()

        self.assertEqual(self.resumen(respuesta)["total"], 5000)
        self.assertEqual(self.resumen(respuesta)["anulados"], 5000)
        self.assertContains(respuesta, "Anulado")

    def test_solo_cuenta_el_local_de_quien_mira(self):
        otro = Local.objects.create(nombre="Otro Local", slug="otro-local")
        cuenta_otro = Cuenta.objects.create(mesa=Mesa.objects.create(local=otro, numero=1))
        self.pagar("efectivo", 5000, a_las(16, 12))
        self.pagar("efectivo", 3000, a_las(16, 12), cuenta=cuenta_otro)

        respuesta = self.recuento()

        self.assertEqual(self.resumen(respuesta)["total"], 5000)
        self.assertEqual([r["local"] for r in respuesta.context["locales"]], ["Local Recuento"])
        self.assertNotContains(respuesta, "Otro Local")

    def test_dia_sin_pagos(self):
        respuesta = self.recuento()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["locales"], [])
        self.assertContains(respuesta, "No hay pagos registrados este día.")

    def test_fecha_invalida_muestra_hoy(self):
        for valor in ("hola", "2026-13-40", "", "'; DROP TABLE"):
            with self.subTest(valor=valor):
                respuesta = self.recuento(valor)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context["fecha"], timezone.localdate())

    def test_sin_fecha_muestra_hoy(self):
        self.assertEqual(self.client.get(self.url).context["fecha"], timezone.localdate())

    def test_fecha_elegida_queda_en_el_formulario(self):
        self.assertContains(self.recuento(), 'value="2026-11-16"')
        self.assertEqual(self.recuento().context["fecha"], date(2026, 11, 16))

    def test_sin_sesion_de_personal_va_al_login(self):
        respuesta = Client().get(self.url)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta["Location"])

    def test_caja_enlaza_al_recuento(self):
        self.assertContains(self.client.get(reverse("pedidos:caja")), self.url)

    def test_el_recuento_no_se_recarga_solo(self):
        self.assertNotContains(self.recuento(), 'http-equiv="refresh"')
