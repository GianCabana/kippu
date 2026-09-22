import re

from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase

ARCHIVOS_ESTATICOS = [
    "kippu/css/kippu.css",
    "kippu/muestrario.html",
    "kippu/fuentes/fraunces-600.woff2",
    "kippu/fuentes/work-sans-400.woff2",
    "kippu/fuentes/work-sans-500.woff2",
    "kippu/fuentes/work-sans-600.woff2",
    "kippu/fuentes/ibm-plex-mono-400.woff2",
    "kippu/fuentes/ibm-plex-mono-500.woff2",
    "kippu/fuentes/noto-serif-jp-200-ken.woff2",
]

# Valores de sistema-de-diseno-kippu.md, §2.1 y §2.3.
PALETA = {
    "--papel": "#fbf7f0",
    "--superficie": "#f3eadc",
    "--superficie-2": "#e6d8c2",
    "--tinta": "#17140f",
    "--texto": "#3b342b",
    "--texto-2": "#5c5245",
    "--texto-3": "#8a7c69",
    "--linea": "#d8d0c3",
    "--linea-suave": "#e7dece",
    "--aji": "#a83a22",
    "--aji-claro": "#c24a2d",
    "--aji-suave": "#f6e4dd",
    "--semaforo-verde": "#6f8f5a",
    "--semaforo-ambar": "#c9a24a",
    "--semaforo-rojo": "#a83a22",
}


class PlantillaBaseTests(SimpleTestCase):
    def test_incluye_idioma_hoja_de_estilos_y_logo(self):
        html = render_to_string("kippu/base.html")

        self.assertIn('<html lang="es-CL">', html)
        self.assertIn('href="/static/kippu/css/kippu.css"', html)
        self.assertIn('<span class="logo" aria-hidden="true">券</span>', html)

    def test_muestra_mensajes_con_su_nivel(self):
        mensajes = [
            Message(constants.SUCCESS, "Agregaste Ceviche clásico."),
            Message(constants.WARNING, "Puedes agregar hasta 20 unidades."),
        ]

        html = render_to_string("kippu/base.html", {"messages": mensajes})

        self.assertIn('class="mensaje mensaje--success">Agregaste Ceviche clásico.', html)
        self.assertIn('class="mensaje mensaje--warning">Puedes agregar hasta 20 unidades.', html)

    def test_sin_mensajes_no_dibuja_la_lista(self):
        html = render_to_string("kippu/base.html")

        self.assertNotIn('class="mensajes"', html)


class ArchivosDelSistemaDeDisenoTests(SimpleTestCase):
    def test_django_encuentra_todos_los_estaticos(self):
        for ruta in ARCHIVOS_ESTATICOS:
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(finders.find(ruta))

    def test_paleta_coincide_con_el_sistema_de_diseno(self):
        with open(finders.find("kippu/css/kippu.css"), encoding="utf-8") as archivo:
            css = archivo.read()

        for variable, valor in PALETA.items():
            with self.subTest(variable=variable):
                declarado = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-fA-F]{{6}});", css)
                self.assertIsNotNone(declarado, f"{variable} no está definida")
                self.assertEqual(declarado.group(1).lower(), valor)

    def test_el_kanji_del_logo_usa_peso_200(self):
        with open(finders.find("kippu/css/kippu.css"), encoding="utf-8") as archivo:
            css = archivo.read()

        regla_logo = re.search(r"\.logo \{(.*?)\}", css, re.DOTALL).group(1)
        self.assertIn("font-weight: 200;", regla_logo)
