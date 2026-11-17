"""Detalle del producto en la carta: miniatura y ventana con foto y descripción (decisión 34)."""
import re

from django.test import TestCase
from django.urls import reverse

from carta.models import Categoria, GrupoOpcion, OpcionProducto, Producto
from mesas.models import Local, Mesa


class DetalleProductoTests(TestCase):
    def setUp(self):
        self.local = Local.objects.create(nombre="La Casa de Prueba", slug="la-casa-de-prueba")
        self.mesa = Mesa.objects.create(local=self.local, numero=7)
        categoria = Categoria.objects.create(local=self.local, nombre="Entradas y ceviches")
        self.ceviche = Producto.objects.create(
            categoria=categoria,
            nombre="Ceviche clásico",
            precio=10900,
            descripcion="Pescado <b>blanco</b> marinado en limón.",
            imagen="productos/la-casa-de-prueba/ceviche-clasico.webp",
        )
        tamano = GrupoOpcion.objects.create(producto=self.ceviche, nombre="Tamaño", requerido=True)
        self.compartir = OpcionProducto.objects.create(grupo=tamano, nombre="Para compartir", precio_extra=5000)
        self.tiradito = Producto.objects.create(categoria=categoria, nombre="Tiradito de corvina", precio=11500)
        self.pisco = Producto.objects.create(
            categoria=categoria, nombre="Pisco sour", precio=6500, requiere_mayoria_edad=True
        )

    def carta(self):
        return self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo])).content.decode()

    def articulo(self, html, producto):
        patron = rf'<article class="producto"[^>]*data-producto="{producto.pk}"[^>]*>(.*?)</article>'
        encontrado = re.search(patron, html, re.DOTALL)
        self.assertIsNotNone(encontrado, f"falta la tarjeta de {producto.nombre}")
        return encontrado.group(1)

    def ventana(self, html, producto):
        patron = rf'<dialog class="detalle[^"]*"[^>]*id="detalle-{producto.pk}"[^>]*>(.*?)</dialog>'
        encontrado = re.search(patron, html, re.DOTALL)
        self.assertIsNotNone(encontrado, f"falta la ventana de {producto.nombre}")
        return encontrado.group(1)

    def lista(self, html, producto):
        """La tarjeta sin su ventana: lo que se ve en la carta."""
        return re.sub(r"<dialog.*?</dialog>", "", self.articulo(html, producto), flags=re.DOTALL)

    def url_agregar(self, producto):
        return reverse("pedidos:agregar", kwargs={"codigo": self.mesa.codigo, "producto_id": producto.pk})

    def test_la_carta_muestra_la_miniatura_o_sin_foto(self):
        html = self.carta()

        ceviche = self.lista(html, self.ceviche)
        self.assertIn('class="producto__mini"', ceviche)
        self.assertRegex(
            ceviche, r'<img src="/media/productos/la-casa-de-prueba/ceviche-clasico\.webp" alt="" loading="lazy"'
        )
        tiradito = self.lista(html, self.tiradito)
        self.assertIn("producto__mini--vacia", tiradito)
        self.assertIn("Sin foto", tiradito)
        self.assertNotIn("<img", tiradito)

    def test_con_opciones_aparece_junto_al_precio_solo_si_tiene_opciones(self):
        html = self.carta()

        self.assertIn("Con opciones", self.lista(html, self.ceviche))
        self.assertNotIn("Con opciones", self.lista(html, self.tiradito))

    def test_la_tarjeta_abre_su_ventana_con_un_boton(self):
        html = self.carta()

        self.assertRegex(
            self.lista(html, self.ceviche),
            rf'<button class="producto__abrir" type="button" data-abrir-detalle="detalle-{self.ceviche.pk}"',
        )

    def test_la_ventana_trae_foto_descripcion_escapada_opciones_y_formulario(self):
        ventana = self.ventana(self.carta(), self.ceviche)

        self.assertIn('<button class="detalle__asa" type="button" aria-label="Cerrar detalle"', ventana)
        self.assertIn('src="/media/productos/la-casa-de-prueba/ceviche-clasico.webp"', ventana)
        self.assertIn("Pescado &lt;b&gt;blanco&lt;/b&gt; marinado en limón.", ventana)
        self.assertNotIn("<b>blanco</b>", ventana)
        self.assertIn(f'name="opcion_grupo_{self.compartir.grupo_id}" value="{self.compartir.pk}"', ventana)
        url = self.url_agregar(self.ceviche)
        self.assertIn(f'action="{url}" data-carrito-form hx-post="{url}"', ventana)
        self.assertIn(f'id="agregar-{self.ceviche.pk}" type="submit"', ventana)

    def test_el_mas_de_un_producto_con_opciones_abre_la_ventana(self):
        lista = self.lista(self.carta(), self.ceviche)

        self.assertRegex(lista, rf'<button class="boton-agregar" type="button" data-abrir-detalle="detalle-{self.ceviche.pk}"')
        self.assertNotIn("<form", lista)

    def test_el_mas_de_un_producto_sin_opciones_sigue_agregando_directo(self):
        html = self.carta()

        lista = self.lista(html, self.tiradito)
        url = self.url_agregar(self.tiradito)
        self.assertIn(f'<form class="producto__accion" id="form-producto-{self.tiradito.pk}"', lista)
        self.assertIn(f'hx-post="{url}"', lista)
        self.assertIn(f'id="agregar-{self.tiradito.pk}" type="submit"', lista)
        ventana = self.ventana(html, self.tiradito)
        self.assertIn(f'hx-post="{url}"', ventana)
        self.assertIn(f'id="agregar-detalle-{self.tiradito.pk}" type="submit"', ventana)

    def test_el_aviso_de_mayores_de_18_esta_en_la_ventana(self):
        self.assertIn("Venta exclusiva para mayores de 18 años.", self.ventana(self.carta(), self.pisco))

    def test_con_pedidos_cerrados_la_ventana_se_abre_sin_opciones_ni_formulario(self):
        Local.objects.filter(pk=self.local.pk).update(recibe_pedidos=False)

        html = self.carta()

        ventana = self.ventana(html, self.ceviche)
        self.assertIn("Pedidos cerrados por ahora", ventana)
        self.assertIn("Pescado &lt;b&gt;blanco&lt;/b&gt; marinado en limón.", ventana)
        self.assertNotIn("opcion_grupo_", ventana)
        self.assertNotIn("<form", ventana)
        lista = self.lista(html, self.ceviche)
        self.assertIn(f'data-abrir-detalle="detalle-{self.ceviche.pk}"', lista)
        self.assertNotIn("boton-agregar", lista)
        self.assertNotIn("Con opciones", lista)
