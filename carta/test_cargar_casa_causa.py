"""Comando de siembra cargar_casa_causa (decisión 15): idempotente, con imágenes de semilla."""
import io
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from carta.models import Categoria, Producto
from mesas.models import Local, Mesa


def conteos(slug):
    local = Local.objects.get(slug=slug)
    return (
        local.mesas.count(),
        local.categorias.count(),
        Producto.objects.filter(categoria__local=local).count(),
    )


class CargarCasaCausaTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.semillas = Path(tempfile.mkdtemp())
        for carpeta in (self.media, self.semillas):
            self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=self.media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        semillas = patch("carta.management.commands.cargar_casa_causa.DIRECTORIO_SEMILLAS", self.semillas)
        semillas.start()
        self.addCleanup(semillas.stop)

    def semilla(self, local, archivo):
        carpeta = self.semillas / local
        carpeta.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 6), (200, 120, 60)).save(carpeta / archivo, "WEBP")

    def cargar(self):
        salida = io.StringIO()
        call_command("cargar_casa_causa", stdout=salida)
        return salida.getvalue()

    def archivos_en_media(self):
        return sorted(str(ruta.relative_to(self.media)) for ruta in Path(self.media).rglob("*") if ruta.is_file())

    def test_correrlo_dos_veces_no_duplica_nada(self):
        self.cargar()
        primera = (conteos("la-casa-causa"), conteos("local-de-prueba-2"), Local.objects.count())

        self.cargar()

        self.assertEqual(primera[0], (16, 5, 35))
        self.assertEqual(primera[1], (2, 1, 2))
        self.assertEqual((conteos("la-casa-causa"), conteos("local-de-prueba-2"), Local.objects.count()), primera)

    def test_copia_la_semilla_a_la_carpeta_del_local_sin_duplicarla(self):
        self.semilla("la-casa-causa", "lomo-saltado.webp")

        self.cargar()
        self.cargar()

        lomo = Producto.objects.get(nombre="Lomo saltado", categoria__local__slug="la-casa-causa")
        self.assertTrue(lomo.imagen.name.startswith("productos/la-casa-causa/lomo-saltado"))
        self.assertEqual(self.archivos_en_media(), [lomo.imagen.name.replace("/", os.sep)])

    def test_producto_sin_semilla_queda_sin_imagen(self):
        self.semilla("la-casa-causa", "lomo-saltado.webp")

        salida = self.cargar()

        cau_cau = Producto.objects.get(nombre="Cau cau")
        self.assertEqual(cau_cau.imagen.name, "")
        self.assertIn("+18, 1 con imagen", salida)

    def test_no_pisa_una_imagen_ya_asignada(self):
        self.cargar()
        lomo = Producto.objects.get(nombre="Lomo saltado")
        (Path(self.media) / "propia.webp").write_bytes(b"foto del restaurante")
        Producto.objects.filter(pk=lomo.pk).update(imagen="propia.webp")
        self.semilla("la-casa-causa", "lomo-saltado.webp")

        self.cargar()

        lomo.refresh_from_db()
        self.assertEqual(lomo.imagen.name, "propia.webp")

    def test_vuelve_a_copiar_si_el_archivo_ya_no_esta(self):
        self.semilla("la-casa-causa", "lomo-saltado.webp")
        self.cargar()
        lomo = Producto.objects.get(nombre="Lomo saltado")
        os.remove(lomo.imagen.path)

        self.cargar()

        lomo.refresh_from_db()
        self.assertTrue(os.path.exists(lomo.imagen.path))

    def test_desactiva_kippu_principal_si_esta_vacio(self):
        salida = self.cargar()

        self.assertFalse(Local.objects.get(slug="kippu-principal").activo)
        self.assertIn("Kippu Principal", salida)

    def test_no_desactiva_kippu_principal_si_tiene_mesas(self):
        principal = Local.objects.get(slug="kippu-principal")
        Mesa.objects.create(local=principal, numero=1)

        salida = self.cargar()

        self.assertTrue(Local.objects.get(slug="kippu-principal").activo)
        self.assertIn("no se desactiva", salida)

    def test_no_pisa_cambios_hechos_en_el_admin(self):
        self.cargar()
        Producto.objects.filter(nombre="Cau cau").update(precio=9990, disponible=False)
        Categoria.objects.filter(nombre="Postres").update(activa=False)

        self.cargar()

        cau_cau = Producto.objects.get(nombre="Cau cau")
        self.assertEqual((cau_cau.precio, cau_cau.disponible), (9990, False))
        self.assertFalse(Categoria.objects.get(nombre="Postres").activa)
