from types import SimpleNamespace
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse
from carta.models import Categoria, Producto
from mesas.models import Mesa


class CarritoHtmxTests(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=991)
        categoria = Categoria.objects.create(nombre='Pruebas')
        self.producto = Producto.objects.create(nombre='Prueba carrito', categoria=categoria, precio=2500)
        claves = {'codigo': self.mesa.codigo, 'producto_id': self.producto.pk}
        self.url = reverse('pedidos:agregar', kwargs=claves)
        self.quitar = reverse('pedidos:quitar', kwargs=claves)
        self.carta = reverse('carta:por_mesa', kwargs={'codigo': self.mesa.codigo})

    def test_fragmento_suma_resta_y_vacia(self):
        for cantidad in (1, 2):
            respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
            self.assertContains(respuesta, f'data-cantidad="{cantidad}"')
            self.assertNotContains(respuesta, '<html')
            self.assertIn('no-store', respuesta['Cache-Control'])
        for cantidad in (1, 0):
            respuesta = self.client.post(self.quitar, HTTP_HX_REQUEST='true')
            self.assertContains(respuesta, f'data-cantidad="{cantidad}"')
        self.assertContains(respuesta, 'Tu carrito está vacío')

    def test_limite_y_redireccion_sin_javascript(self):
        for _ in range(21):
            self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(self.client.session[f'carrito_{self.mesa.codigo}'][str(self.producto.pk)], 20)
        self.assertRedirects(self.client.post(self.quitar), self.carta)

    def test_csrf_y_get_no_modifican_carrito(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post(self.url, HTTP_HX_REQUEST='true').status_code, 403)
        self.assertEqual(cliente.get(self.url).status_code, 405)
        self.assertNotIn(f'carrito_{self.mesa.codigo}', cliente.session)

    @patch('pedidos.views.intento_activo', return_value=SimpleNamespace(pk=123))
    def test_pago_activo_navega_y_no_modifica_carrito(self, activo):
        respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta['HX-Redirect'])
        self.assertNotIn(f'carrito_{self.mesa.codigo}', self.client.session)

    def test_render_carta_y_pago_normal(self):
        self.client.post(self.url)
        respuesta = self.client.get(self.carta)
        self.assertContains(respuesta, 'x-data="cartaKippu"')
        self.assertContains(respuesta, 'id="carrito-datos"')
        self.assertContains(respuesta, 'hx-boost="false"')
        self.assertContains(respuesta, 'data-cantidad="1"')
