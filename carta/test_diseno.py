import re

from django.contrib.auth import get_user_model
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from carta.models import Categoria, GrupoOpcion, OpcionProducto, Producto
from mesas.models import Local, Mesa

ARCHIVOS_ESTATICOS = [
    "css/kippu.css",
    "muestrario.html",
    "fuentes/fraunces-600.woff2",
    "fuentes/work-sans-400.woff2",
    "fuentes/work-sans-500.woff2",
    "fuentes/work-sans-600.woff2",
    "fuentes/ibm-plex-mono-400.woff2",
    "fuentes/ibm-plex-mono-500.woff2",
    "fuentes/noto-serif-jp-200-ken.woff2",
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
        html = render_to_string("base.html")

        self.assertIn('<html lang="es-CL">', html)
        self.assertIn('href="/static/css/kippu.css"', html)
        self.assertIn('<span class="logo" aria-hidden="true">券</span>', html)

    def test_muestra_mensajes_con_su_nivel(self):
        mensajes = [
            Message(constants.SUCCESS, "Agregaste Ceviche clásico."),
            Message(constants.WARNING, "Puedes agregar hasta 20 unidades."),
        ]

        html = render_to_string("base.html", {"messages": mensajes})

        self.assertIn('class="mensaje mensaje--success">Agregaste Ceviche clásico.', html)
        self.assertIn('class="mensaje mensaje--warning">Puedes agregar hasta 20 unidades.', html)

    def test_sin_mensajes_no_dibuja_la_lista(self):
        html = render_to_string("base.html")

        self.assertNotIn('class="mensajes"', html)


class ArchivosDelSistemaDeDisenoTests(SimpleTestCase):
    def test_django_encuentra_todos_los_estaticos(self):
        for ruta in ARCHIVOS_ESTATICOS:
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(finders.find(ruta))

    def test_paleta_coincide_con_el_sistema_de_diseno(self):
        with open(finders.find("css/kippu.css"), encoding="utf-8") as archivo:
            css = archivo.read()

        for variable, valor in PALETA.items():
            with self.subTest(variable=variable):
                declarado = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-fA-F]{{6}});", css)
                self.assertIsNotNone(declarado, f"{variable} no está definida")
                self.assertEqual(declarado.group(1).lower(), valor)

    def test_el_kanji_del_logo_usa_peso_200(self):
        with open(finders.find("css/kippu.css"), encoding="utf-8") as archivo:
            css = archivo.read()

        regla_logo = re.search(r"\.logo \{(.*?)\}", css, re.DOTALL).group(1)
        self.assertIn("font-weight: 200;", regla_logo)

    def test_la_etiqueta_usa_texto_2_por_contraste(self):
        with open(finders.find("css/kippu.css"), encoding="utf-8") as archivo:
            css = archivo.read()

        regla_etiqueta = re.search(r"^\.etiqueta \{(.*?)\}", css, re.DOTALL | re.MULTILINE).group(1)
        self.assertIn("color: var(--texto-2);", regla_etiqueta, "--texto-3 queda bajo AA en texto chico")


class CartaConDisenoKippuTests(TestCase):
    def setUp(self):
        local = Local.objects.create(nombre="La Casa de Prueba", slug="la-casa-de-prueba")
        self.mesa = Mesa.objects.create(local=local, numero=4)
        categoria = Categoria.objects.create(nombre="Barra", local=local)
        self.producto = Producto.objects.create(
            nombre="Pisco sour", categoria=categoria, precio=6500, requiere_mayoria_edad=True
        )

    def test_las_hojas_de_pantalla_usan_solo_las_variables_de_kippu(self):
        for ruta in ("carta/carta.css", "pedidos/webpay.css", "pedidos/panel.css"):
            with self.subTest(hoja=ruta), open(finders.find(ruta), encoding="utf-8") as archivo:
                css = re.sub(r"/\*.*?\*/", "", archivo.read(), flags=re.DOTALL)

                self.assertFalse(":root" in css, f"{ruta} redefine :root")
                self.assertIsNone(re.search(r"--[\w-]+\s*:", css), f"{ruta} define variables propias")
                self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", css), f"{ruta} tiene colores escritos a mano")

    def test_carta_muestra_el_local_sin_estilos_en_linea(self):
        respuesta = self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]))
        html = re.sub(r"<noscript>.*?</noscript>", "", respuesta.content.decode(), flags=re.DOTALL)

        self.assertContains(respuesta, '<h1 id="titulo-carta">La Casa de Prueba</h1>')
        self.assertContains(respuesta, 'class="insignia-18"')
        self.assertNotIn("badge-18", html)
        self.assertEqual(html.count("<style"), 1, "solo debe quedar el [x-cloak] de base.html")

    def test_ningun_monto_reactivo_queda_fijo_con_data_pesos(self):
        html = self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo])).content.decode()

        # formatear() reescribe los data-pesos con el valor de la carga y pisaría el x-text.
        for etiqueta in re.findall(r"<[^>]*\bx-text=[^>]*>", html):
            with self.subTest(etiqueta=etiqueta):
                self.assertNotIn("data-pesos", etiqueta)

    def test_fragmento_del_carrito_sin_estilos_en_linea(self):
        agregar = reverse(
            "pedidos:agregar", kwargs={"codigo": self.mesa.codigo, "producto_id": self.producto.pk}
        )

        respuesta = self.client.post(agregar, HTTP_HX_REQUEST="true")

        self.assertContains(respuesta, 'data-cantidad="1"')
        self.assertContains(respuesta, 'name="confirma_mayoria_edad"')
        self.assertNotContains(respuesta, "<style")
        self.assertNotContains(respuesta, "badge-18")

    def test_las_opciones_se_despliegan_al_tocar_agregar(self):
        chicha = Producto.objects.create(nombre="Chicha morada", categoria=self.producto.categoria, precio=3200)
        tamano = GrupoOpcion.objects.create(producto=chicha, nombre="Tamaño")
        OpcionProducto.objects.create(grupo=tamano, nombre="Jarra", precio_extra=4500)

        html = self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo])).content.decode()
        panel = re.search(r'<details class="producto__opciones">(.*?)</details>', html, re.DOTALL)

        self.assertIsNotNone(panel, "las opciones deben ir dentro de un <details> cerrado")
        self.assertIn('name="opcion_grupo_', panel.group(1))
        self.assertIn(f'id="agregar-{chicha.pk}"', panel.group(1))
        self.assertIn(f'<form class="producto__accion" id="form-producto-{self.producto.pk}"', html)

    def test_la_carta_entrega_los_precios_para_mostrar_el_precio_con_opciones(self):
        chicha = Producto.objects.create(nombre="Chicha morada", categoria=self.producto.categoria, precio=3200)
        tamano = GrupoOpcion.objects.create(producto=chicha, nombre="Tamaño")
        jarra = OpcionProducto.objects.create(grupo=tamano, nombre="Jarra", precio_extra=4500)
        vaso = OpcionProducto.objects.create(grupo=tamano, nombre="Vaso")

        html = self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo])).content.decode()

        self.assertEqual(html.count('data-precio-base="3200"'), 2, "precio de la tarjeta y del botón Agregar")
        self.assertIn(f'value="{jarra.pk}" data-precio-extra="4500"', html)
        self.assertIn(f'value="{vaso.pk}" data-precio-extra="0"', html)


class PanelConDisenoKippuTests(TestCase):
    def setUp(self):
        personal = get_user_model().objects.create_user(username="panel_diseno", password="Pruebas123!", is_staff=True)
        self.client.force_login(personal)

    def test_cocina_y_entregas_usan_la_barra_y_la_hoja_del_panel(self):
        for nombre, lista in (("cocina", "kippu-cocina"), ("entregas", "kippu-entregas")):
            with self.subTest(pantalla=nombre):
                respuesta = self.client.get(reverse(f"pedidos:{nombre}"))
                html = re.sub(r"<noscript>.*?</noscript>", "", respuesta.content.decode(), flags=re.DOTALL)

                self.assertContains(respuesta, 'href="/static/css/kippu.css"')
                self.assertContains(respuesta, 'href="/static/pedidos/panel.css"')
                self.assertContains(respuesta, 'class="panel-barra"')
                self.assertContains(respuesta, f'id="lista-{nombre}" data-panel="{lista}"')
                self.assertEqual(html.count("<style"), 1, "solo debe quedar el [x-cloak] de base.html")
