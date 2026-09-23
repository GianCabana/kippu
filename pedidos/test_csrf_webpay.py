"""El formulario de verificación conserva CSRF y solo acepta su propio origen."""
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from mesas.models import Mesa
from .models import Cuenta, IntentoWebpay
from .vistas_webpay import _url_resultado


class CsrfWebpayTests(TestCase):
    def setUp(self):
        mesa=Mesa.objects.create(numero=903,activa=True)
        cuenta=Cuenta.objects.create(mesa=mesa)
        self.intento=IntentoWebpay.objects.create(cuenta=cuenta,monto=3500,
            estado='iniciado',token='c'*64)
        self.client=Client(enforce_csrf_checks=True)
        self.resultado=self.client.get(_url_resultado(self.intento.pk))
        self.url=reverse('pedidos:webpay_verificar',args=[self.intento.pk])
        self.datos={'firma':self.resultado.context['firma'],
            'csrfmiddlewaretoken':self.client.cookies['csrftoken'].value}

    def test_politica_y_formulario(self):
        self.assertEqual(self.resultado['Referrer-Policy'],'same-origin')
        self.assertContains(self.resultado,'<meta name="referrer" content="same-origin">')
        self.assertContains(self.resultado,'name="csrfmiddlewaretoken"')
        self.assertNotContains(self.resultado,'no-referrer')

    def test_post_del_mismo_origen_consulta_el_intento(self):
        with patch('pedidos.vistas_webpay.resolver_intento') as resolver:
            r=self.client.post(self.url,self.datos,HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,302)
        resolver.assert_called_once_with(self.intento.pk)

    def test_origin_null_o_ajeno_sigue_rechazado(self):
        for origin in ('null','https://ajeno.invalid'):
            with patch('pedidos.vistas_webpay.resolver_intento') as resolver:
                r=self.client.post(self.url,self.datos,HTTP_ORIGIN=origin)
                self.assertEqual(r.status_code,403)
                resolver.assert_not_called()

    def test_sin_token_csrf_no_consulta(self):
        with patch('pedidos.vistas_webpay.resolver_intento') as resolver:
            r=self.client.post(self.url,{'firma':self.datos['firma']},HTTP_ORIGIN='http://testserver')
        self.assertEqual(r.status_code,403)
        resolver.assert_not_called()
