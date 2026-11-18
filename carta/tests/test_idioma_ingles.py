"""Fase 3: la carta y las páginas del cliente en inglés según el idioma del teléfono."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from carta.management.commands.compilar_traducciones import compilar, leer_po
from carta.models import Categoria, GrupoOpcion, OpcionProducto, Producto
from carta.traducciones import textos_marcados
from config.idioma import es_pagina_del_cliente
from mesas.models import Local, Mesa

INGLES = {"HTTP_ACCEPT_LANGUAGE": "en-US,en;q=0.9"}
ESPANOL = {"HTTP_ACCEPT_LANGUAGE": "es-ES,es;q=0.9"}
PO = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"


class PaginasEnInglesTests(TestCase):
    def setUp(self):
        self.local = Local.objects.create(nombre="Local idioma", slug="local-idioma")
        self.mesa = Mesa.objects.create(local=self.local, numero=4, activa=True)
        fondos = Categoria.objects.create(local=self.local, nombre="Fondos", nombre_en="Main courses")
        self.lomo = Producto.objects.create(
            categoria=fondos, nombre="Lomo saltado", nombre_en="Stir-fried beef", precio=13900,
            descripcion="Tiras de lomo salteadas.", descripcion_en="Strips of beef, stir-fried.",
        )
        self.cau = Producto.objects.create(categoria=fondos, nombre="Cau cau", precio=11200, descripcion="Guiso.")
        grupo = GrupoOpcion.objects.create(producto=self.lomo, nombre="Acompañamiento", nombre_en="Side", requerido=True)
        OpcionProducto.objects.create(grupo=grupo, nombre="Arroz blanco", nombre_en="White rice")

    def carta(self, **cabeceras):
        return self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]), **cabeceras)

    def test_telefono_en_ingles_ve_la_carta_en_ingles(self):
        respuesta = self.carta(**INGLES)

        self.assertContains(respuesta, '<html lang="en">')
        self.assertContains(respuesta, "Welcome to")
        self.assertContains(respuesta, "Table 4")
        self.assertContains(respuesta, "View my cart")
        self.assertContains(respuesta, "Main courses")
        self.assertContains(respuesta, "Stir-fried beef")
        self.assertContains(respuesta, "Strips of beef, stir-fried.")
        self.assertContains(respuesta, "White rice")
        self.assertNotContains(respuesta, "Bienvenido a")

    def test_sin_texto_en_ingles_muestra_el_espanol(self):
        respuesta = self.carta(**INGLES)

        self.assertContains(respuesta, "Cau cau")
        self.assertContains(respuesta, "Guiso.")

    def test_telefono_en_espanol_o_sin_idioma_ve_espanol(self):
        for cabeceras in (ESPANOL, {}):
            with self.subTest(cabeceras=cabeceras):
                respuesta = self.carta(**cabeceras)
                self.assertContains(respuesta, '<html lang="es-CL">')
                self.assertContains(respuesta, "Bienvenido a")
                self.assertContains(respuesta, ">Lomo saltado</button>")
                # El nombre en inglés solo va en data-busqueda (se busca en los dos idiomas), no a la vista.
                self.assertNotContains(respuesta, ">Stir-fried beef</button>")

    def test_la_respuesta_varia_segun_el_idioma(self):
        respuesta = self.carta(**INGLES)

        self.assertIn("Accept-Language", respuesta["Vary"])
        self.assertEqual(respuesta["Content-Language"], "en")

    def test_los_mensajes_del_carrito_salen_en_ingles(self):
        respuesta = self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.cau.pk]),
            HTTP_HX_REQUEST="true", **INGLES,
        )

        self.assertContains(respuesta, "You added Cau cau.")
        self.assertContains(respuesta, "Your order")

    def test_mis_pedidos_en_ingles(self):
        respuesta = self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]), **INGLES)

        self.assertContains(respuesta, "MY ORDERS")
        self.assertContains(respuesta, "You have no orders yet on this visit.")

    def test_el_admin_sigue_en_espanol(self):
        respuesta = self.client.get(reverse("admin:login"), **INGLES)

        self.assertContains(respuesta, '<html lang="es-CL">')
        self.assertContains(respuesta, "Panel del personal")
        self.assertNotIn("Content-Language", respuesta)

    def test_el_idioma_no_queda_activo_despues_de_la_peticion(self):
        self.carta(**INGLES)

        self.assertEqual(translation.get_language(), settings.LANGUAGE_CODE)


class RutasDelClienteTests(SimpleTestCase):
    def test_paginas_del_cliente(self):
        for ruta in ("/", "/mesa/abc/", "/pedidos/mesa/abc/mis-pedidos/", "/pedidos/webpay/resultado/1/"):
            with self.subTest(ruta=ruta):
                self.assertTrue(es_pagina_del_cliente(ruta))

    def test_paginas_del_personal(self):
        for ruta in ("/admin/", "/pedidos/cocina/", "/pedidos/entregas/", "/pedidos/caja/", "/pedidos/caja/recuento/"):
            with self.subTest(ruta=ruta):
                self.assertFalse(es_pagina_del_cliente(ruta))


class CatalogoDeTraduccionesTests(SimpleTestCase):
    def entradas(self):
        return {(msgid, plural): (msgstr, fuzzy) for msgid, plural, msgstr, fuzzy in leer_po(PO.read_text(encoding="utf-8")) if msgid}

    def test_cada_texto_marcado_tiene_traduccion(self):
        entradas = self.entradas()
        faltan = [t for t in textos_marcados() if t not in entradas or entradas[t][1] or not all(entradas[t][0])]

        self.assertEqual(faltan, [], "Agrega estos textos a locale/en/LC_MESSAGES/django.po")

    def test_las_traducciones_conservan_las_variables(self):
        for (msgid, _plural), (msgstr, _fuzzy) in self.entradas().items():
            variables = {parte.split(")s")[0] for parte in msgid.split("%(")[1:]}
            for traduccion in msgstr:
                with self.subTest(msgid=msgid):
                    self.assertEqual({p.split(")s")[0] for p in traduccion.split("%(")[1:]}, variables)

    def test_el_mo_esta_al_dia_con_el_po(self):
        mo = PO.with_suffix(".mo")

        self.assertEqual(mo.read_bytes(), compilar(PO), "Corre: python manage.py compilar_traducciones")
