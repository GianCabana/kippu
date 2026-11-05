"""Imagen opcional del producto y su respaldo (decisiones 34 y 45)."""
import io
import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import modelform_factory
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from PIL import Image

from carta.models import Categoria, Producto
from mesas.models import Local


def imagen_en_memoria(formato="WEBP", tamano=(8, 6), ruido=False):
    if ruido:
        imagen = Image.frombytes("RGB", tamano, os.urandom(tamano[0] * tamano[1] * 3))
    else:
        imagen = Image.new("RGB", tamano, (200, 120, 60))
    salida = io.BytesIO()
    imagen.save(salida, formato)
    return salida.getvalue()


class ImagenProductoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=self.media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.local = Local.objects.create(nombre="La Casa de Prueba", slug="la-casa-de-prueba")
        self.categoria = Categoria.objects.create(local=self.local, nombre="Fondos")
        self.Formulario = modelform_factory(Producto, fields=["categoria", "nombre", "precio", "imagen"])

    def formulario(self, nombre, contenido, tipo):
        datos = {"categoria": self.categoria.pk, "nombre": "Lomo saltado", "precio": 13900}
        return self.Formulario(datos, {"imagen": SimpleUploadedFile(nombre, contenido, content_type=tipo)})

    def test_la_imagen_es_opcional(self):
        formulario = self.Formulario({"categoria": self.categoria.pk, "nombre": "Cau cau", "precio": 11200})

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.save().imagen.name, "")

    def test_acepta_webp_y_lo_guarda_en_la_carpeta_del_local(self):
        formulario = self.formulario("lomo.webp", imagen_en_memoria(), "image/webp")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        producto = formulario.save()
        self.assertTrue(producto.imagen.name.startswith("productos/la-casa-de-prueba/"))

    def test_rechaza_gif(self):
        formulario = self.formulario("lomo.gif", imagen_en_memoria("GIF"), "image/gif")

        self.assertFalse(formulario.is_valid())
        self.assertIn("imagen", formulario.errors)

    def test_rechaza_un_archivo_que_no_es_imagen_aunque_diga_png(self):
        formulario = self.formulario("lomo.png", b"esto no es una imagen", "image/png")

        self.assertFalse(formulario.is_valid())
        self.assertIn("imagen", formulario.errors)

    def test_rechaza_imagenes_de_mas_de_2_mb(self):
        pesada = imagen_en_memoria("PNG", tamano=(1000, 1000), ruido=True)
        self.assertGreater(len(pesada), 2 * 1024 * 1024)

        formulario = self.formulario("lomo.png", pesada, "image/png")

        self.assertFalse(formulario.is_valid())
        self.assertIn("2 MB", str(formulario.errors["imagen"]))


class RespaldoImagenTests(TestCase):
    def setUp(self):
        local = Local.objects.create(nombre="La Casa de Prueba", slug="la-casa-de-prueba")
        categoria = Categoria.objects.create(local=local, nombre="Fondos")
        self.producto = Producto.objects.create(categoria=categoria, nombre="Ají <de> gallina", precio=11500)

    def dibujar(self):
        return render_to_string("carta/fragmentos/imagen_producto.html", {"producto": self.producto})

    def test_sin_imagen_muestra_el_respaldo_con_el_nombre_escapado(self):
        html = self.dibujar()

        self.assertIn("foto-producto--respaldo", html)
        self.assertIn("Ají &lt;de&gt; gallina", html)
        self.assertIn("Imagen no disponible", html)
        self.assertNotIn("<img", html)

    def test_con_imagen_muestra_la_foto_y_cambia_al_respaldo_si_no_carga(self):
        self.producto.imagen.name = "productos/la-casa-de-prueba/aji-de-gallina.webp"

        html = self.dibujar()

        self.assertIn('src="/media/productos/la-casa-de-prueba/aji-de-gallina.webp"', html)
        self.assertIn('alt="Ají &lt;de&gt; gallina"', html)
        self.assertIn("onerror=", html)
        self.assertIn("foto-producto__respaldo", html)
        self.assertNotIn('class="foto-producto foto-producto--respaldo"', html)
