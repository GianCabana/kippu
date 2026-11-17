"""Caja con HTMX (fila 28): se actualizan solo las listas y nunca a mitad de una confirmación."""
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from ..models import Pedido
from .test_pago_presencial import PagoPresencialBase


class CajaHtmxTests(PagoPresencialBase):
    def setUp(self):
        super().setUp()
        self.url_caja = reverse("pedidos:caja")
        self.url_listas = reverse("pedidos:caja_listas")

    def test_la_caja_ya_no_se_recarga_entera(self):
        r = self.operador.get(self.url_caja)
        self.assertContains(r, 'http-equiv="refresh"', count=1)
        self.assertContains(r, '<noscript><meta http-equiv="refresh" content="15"></noscript>', html=False)

    def test_las_listas_se_piden_cada_15_s_y_se_pausan_al_confirmar(self):
        r = self.operador.get(self.url_caja)
        self.assertContains(r, 'id="caja-listas"')
        self.assertContains(r, f'hx-get="{self.url_listas}"')
        self.assertContains(r, "every 15s [!document.hidden && !document.querySelector('#caja-listas .caja-mesa--confirmando')]")
        self.assertContains(r, 'hx-swap="outerHTML"')

    def test_el_fragmento_trae_las_listas_sin_la_pagina(self):
        pedido = self.pedido()
        r = self.operador.get(self.url_listas, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<html")
        self.assertNotContains(r, "<h1>")
        self.assertContains(r, 'id="caja-listas"')
        self.assertContains(r, f"Pedido #{pedido.pk}")
        self.assertContains(r, reverse("pedidos:cobrar_presencial", args=[pedido.pk]))
        self.assertContains(r, "csrfmiddlewaretoken")
        for titulo in ("Por cobrar", "Pedidos por QR", "Mesas con cuenta abierta", "Pagos por verificar",
                       "Últimos pagos", "Últimos cierres"):
            self.assertContains(r, f"<h2>{titulo}</h2>", html=True)

    def test_la_pagina_y_el_fragmento_muestran_lo_mismo(self):
        pedido = self.pedido()
        self.cobrar(pedido)
        pagina = self.operador.get(self.url_caja).content.decode()
        fragmento = self.operador.get(self.url_listas).content.decode()
        self.assertIn(fragmento.split('name="csrfmiddlewaretoken"')[0], pagina)

    def test_el_fragmento_actualiza_la_hora_de_la_barra(self):
        pagina = self.operador.get(self.url_caja)
        self.assertContains(pagina, 'id="panel-hora"', count=1)
        self.assertNotContains(pagina, "hx-swap-oob")
        fragmento = self.operador.get(self.url_listas)
        self.assertContains(fragmento, '<time id="panel-hora" class="cifra" hx-swap-oob="true">')

    def test_el_fragmento_tambien_vence_los_por_cobrar(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)
        r = self.operador.get(self.url_listas)
        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)
        self.assertNotContains(r, f"Pedido #{pedido.pk}")

    def test_sin_sesion_htmx_lleva_al_login_completo(self):
        r = Client().get(self.url_listas, HTTP_HX_REQUEST="true")
        login = f"{reverse('admin:login')}?next={quote(self.url_caja)}"
        self.assertEqual(r["HX-Redirect"], login)
        self.assertEqual(r.content, b"")

    def test_sin_sesion_y_sin_htmx_redirige_al_login(self):
        r = Client().get(self.url_listas)
        self.assertRedirects(r, f"{reverse('admin:login')}?next={quote(self.url_caja)}", fetch_redirect_response=False)

    def test_un_cliente_sin_permiso_no_ve_las_listas(self):
        cliente = Client()
        cliente.force_login(get_user_model().objects.create_user(username="cliente_caja", password="Pruebas123!"))
        r = cliente.get(self.url_listas, HTTP_HX_REQUEST="true")
        self.assertIn("HX-Redirect", r)
        self.assertNotContains(r, "Por cobrar")

    def test_el_fragmento_solo_acepta_get(self):
        self.assertEqual(self.operador.post(self.url_listas).status_code, 405)
