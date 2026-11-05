from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from carta.models import Categoria, Producto
from pedidos.models import Pedido

from .models import Local, Mesa


class LocalesTests(TestCase):
    def setUp(self):
        self.local_a = Local.objects.create(nombre="Local A", slug="local-a")
        self.local_b = Local.objects.create(nombre="Local B", slug="local-b")
        self.mesa_a = Mesa.objects.create(local=self.local_a, numero=1)
        self.mesa_b = Mesa.objects.create(local=self.local_b, numero=1)
        self.categoria_a = Categoria.objects.create(local=self.local_a, nombre="Platos")
        self.categoria_b = Categoria.objects.create(local=self.local_b, nombre="Platos")
        self.producto_a = Producto.objects.create(
            categoria=self.categoria_a,
            nombre="Producto del local A",
            precio=5000,
        )
        self.producto_b = Producto.objects.create(
            categoria=self.categoria_b,
            nombre="Producto del local B",
            precio=6000,
        )

    def test_numeros_y_categorias_se_reutilizan_entre_locales(self):
        self.assertEqual(Mesa.objects.filter(numero=1).count(), 2)
        self.assertEqual(Categoria.objects.filter(nombre="Platos").count(), 2)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(local=self.local_a, numero=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Categoria.objects.create(local=self.local_a, nombre="Platos")

    def test_carta_solo_muestra_productos_de_la_mesa(self):
        url = reverse("carta:por_mesa", kwargs={"codigo": self.mesa_a.codigo})
        respuesta = self.client.get(url)
        self.assertContains(respuesta, self.producto_a.nombre)
        self.assertNotContains(respuesta, self.producto_b.nombre)

    def test_no_se_puede_agregar_producto_de_otro_local(self):
        url = reverse("pedidos:agregar", kwargs={
            "codigo": self.mesa_a.codigo,
            "producto_id": self.producto_b.pk,
        })
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_pago_rechaza_producto_inyectado_de_otro_local(self):
        sesion = self.client.session
        sesion[f"carrito_{self.mesa_a.codigo}"] = {str(self.producto_b.pk): 1}
        sesion.save()
        url = reverse("pedidos:webpay_cliente", kwargs={"codigo": self.mesa_a.codigo})
        respuesta = self.client.post(url)
        self.assertRedirects(
            respuesta,
            reverse("carta:por_mesa", kwargs={"codigo": self.mesa_a.codigo}),
        )
        self.assertFalse(Pedido.objects.filter(mesa=self.mesa_a).exists())

    def test_local_inactivo_bloquea_carta(self):
        self.local_a.activo = False
        self.local_a.save(update_fields=["activo"])
        url = reverse("carta:por_mesa", kwargs={"codigo": self.mesa_a.codigo})
        self.assertEqual(self.client.get(url).status_code, 404)
