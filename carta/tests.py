from django.test import TestCase
from django.urls import reverse

from carta.models import Categoria, Producto
from mesas.models import Local, Mesa


class PaginaSinQrTests(TestCase):
    def setUp(self):
        local = Local.objects.create(nombre="La Casa de Prueba", slug="la-casa-de-prueba")
        self.mesa = Mesa.objects.create(local=local, numero=4)
        categoria = Categoria.objects.create(nombre="Barra", local=local)
        Producto.objects.create(nombre="Pisco sour", categoria=categoria, precio=6500)

    def test_sin_mesa_explica_como_usar_la_camara(self):
        respuesta = self.client.get(reverse("carta:lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Abre la cámara de tu teléfono")
        self.assertContains(respuesta, 'class="sin-qr__icono"')

    def test_sin_mesa_no_dice_que_no_hay_productos(self):
        respuesta = self.client.get(reverse("carta:lista"))

        self.assertNotContains(respuesta, "no hay productos disponibles")
        self.assertNotContains(respuesta, 'id="buscar"')

    def test_sin_mesa_no_ofrece_escribir_la_mesa(self):
        respuesta = self.client.get(reverse("carta:lista"))

        self.assertNotContains(respuesta, "<input")

    def test_con_mesa_sigue_mostrando_la_carta(self):
        respuesta = self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]))

        self.assertContains(respuesta, "Pisco sour")
        self.assertContains(respuesta, 'id="buscar"')
        self.assertNotContains(respuesta, "Abre la cámara de tu teléfono")
