from types import SimpleNamespace
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse
from carta.models import Categoria, Producto
from mesas.models import Mesa
from pedidos.carrito import Carrito


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

    def test_tope_oculta_sumar_y_avisa(self):
        sumar = f'id="sumar-{self.producto.pk}"'
        aviso = 'Máximo 20 unidades de este producto.'
        for _ in range(19):
            respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertContains(respuesta, sumar)
        self.assertNotContains(respuesta, aviso)

        respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertNotContains(respuesta, sumar)
        self.assertContains(respuesta, aviso)

        respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertContains(respuesta, 'Puedes agregar hasta 20 unidades de cada producto.')
        self.assertContains(respuesta, 'data-cantidad="20"')

        respuesta = self.client.post(self.quitar, HTTP_HX_REQUEST='true')
        self.assertContains(respuesta, sumar)
        self.assertNotContains(respuesta, aviso)

    def test_tope_es_por_producto(self):
        otro = Producto.objects.create(nombre='Otro producto', categoria=self.producto.categoria, precio=1000)
        for _ in range(20):
            self.client.post(self.url, HTTP_HX_REQUEST='true')
        url_otro = reverse('pedidos:agregar', kwargs={'codigo': self.mesa.codigo, 'producto_id': otro.pk})
        respuesta = self.client.post(url_otro, HTTP_HX_REQUEST='true')
        self.assertContains(respuesta, 'data-cantidad="21"')
        self.assertContains(respuesta, f'id="sumar-{otro.pk}"')
        self.assertNotContains(respuesta, f'id="sumar-{self.producto.pk}"')

    def test_tope_sigue_a_la_constante(self):
        with patch.object(Carrito, 'MAXIMO_POR_PRODUCTO', 3):
            for _ in range(4):
                respuesta = self.client.post(self.url, HTTP_HX_REQUEST='true')
        self.assertContains(respuesta, 'Puedes agregar hasta 3 unidades de cada producto.')
        self.assertContains(respuesta, 'Máximo 3 unidades de este producto.')
        self.assertEqual(self.client.session[f'carrito_{self.mesa.codigo}'][str(self.producto.pk)], 3)

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
