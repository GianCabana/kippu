"""Nombre opcional del pedido (decisión 39): carrito, sesión, cocina, entregas y Mis pedidos."""

from django.test import Client, TestCase
from django.urls import reverse

from . import test_webpay_demo as base
from .models import Pedido
from .pagos import limpiar_nombre, resolver_intento


class NombrePedidoTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def iniciar(self, nombre=None, client=None):
        datos = {"propina": "0"}
        if nombre is not None:
            datos["nombre"] = nombre
        return (client or self.client).post(
            reverse("pedidos:webpay_cliente", args=[self.mesa.codigo]), datos
        )

    def crear(self, nombre=None):
        salida = self.iniciar(nombre)
        self.assertEqual(salida.status_code, 200)
        return salida.context["intento"]

    def carta(self, client=None):
        return (client or self.client).get(reverse("carta:por_mesa", args=[self.mesa.codigo]))

    def test_sin_nombre_el_pedido_se_crea_igual(self):
        intento = self.crear()

        self.assertEqual(intento.pedido.nombre, "")

    def test_carrito_pide_el_nombre_como_opcional(self):
        respuesta = self.carta()

        self.assertContains(respuesta, "¿Para quién es?")
        self.assertContains(respuesta, 'name="nombre"')
        self.assertContains(respuesta, 'maxlength="30"')
        self.assertNotContains(respuesta, 'name="nombre" required')

    def test_servidor_limpia_espacios_y_recorta_a_30(self):
        intento = self.crear("   Ana \n  María   " + "x" * 40)

        self.assertEqual(intento.pedido.nombre, ("Ana María " + "x" * 40)[:30])
        self.assertEqual(len(intento.pedido.nombre), 30)

    def test_quita_numeros_emojis_y_simbolos(self):
        intento = self.crear("Ana💀123 <Pérez>!")

        self.assertEqual(intento.pedido.nombre, "Ana Pérez")

    def test_mantiene_tildes_enie_guion_apostrofe_y_punto(self):
        for nombre in ("María-José", "O'Higgins", "O’Higgins", "Sr. Müller", "Begoña Núñez"):
            with self.subTest(nombre=nombre):
                self.assertEqual(limpiar_nombre(nombre), nombre)

    def test_quita_caracteres_invisibles_sin_partir_el_nombre(self):
        self.assertEqual(limpiar_nombre("A​na‮"), "Ana")
        self.assertEqual(limpiar_nombre("Ana\nMaría"), "Ana María")

    def test_tilde_descompuesta_se_conserva(self):
        self.assertEqual(limpiar_nombre("José"), "José")

    def test_sin_letras_queda_vacio(self):
        for nombre in ("123", "💀💀", "- . '", "<>"):
            with self.subTest(nombre=nombre):
                self.assertEqual(limpiar_nombre(nombre), "")

    def test_carrito_avisa_en_el_navegador_que_solo_van_letras(self):
        respuesta = self.carta()

        self.assertContains(respuesta, 'pattern="')
        self.assertContains(respuesta, "Solo letras")

    def test_nombre_con_html_se_muestra_escapado_en_cocina_y_entregas(self):
        # Por el carrito no entra HTML; esto cubre un nombre que llegue por otro camino (admin).
        intento = self.crear("Ana")
        self.aprobar(intento)
        Pedido.objects.filter(pk=intento.pedido_id).update(nombre="<b>Ana</b>")

        cocina = self.operador.get(reverse("pedidos:cocina"))
        self.assertContains(cocina, "&lt;b&gt;Ana&lt;/b&gt;")
        self.assertNotContains(cocina, "<b>Ana</b>")

        Pedido.objects.filter(pk=intento.pedido_id).update(estado=Pedido.Estado.LISTO)
        entregas = self.operador.get(reverse("pedidos:entregas"))
        self.assertContains(entregas, "&lt;b&gt;Ana&lt;/b&gt;")
        self.assertNotContains(entregas, "<b>Ana</b>")

    def test_nombre_aparece_en_mis_pedidos(self):
        intento = self.crear("Ana")
        self.aprobar(intento)

        respuesta = self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

        self.assertContains(respuesta, 'class="tk__nombre"')
        self.assertContains(respuesta, "Ana")

    def test_sin_nombre_no_se_muestra_nada(self):
        intento = self.crear()
        self.aprobar(intento)

        cocina = self.operador.get(reverse("pedidos:cocina"))
        mis_pedidos = self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

        self.assertNotContains(cocina, "comanda__nombre")
        self.assertNotContains(mis_pedidos, "tk__nombre")
        self.assertNotContains(mis_pedidos, "Sin nombre")

    def test_segundo_pedido_de_la_sesion_trae_el_nombre_precargado(self):
        intento = self.crear("Ana")
        self.aprobar(intento)
        self.carta()
        self.llenar(self.client)

        respuesta = self.carta()

        self.assertContains(respuesta, 'value="Ana"')

    def test_otra_sesion_no_ve_el_nombre(self):
        intento = self.crear("Ana")
        self.aprobar(intento)
        otro = Client()
        self.llenar(otro)

        respuesta = self.carta(otro)

        self.assertContains(respuesta, 'name="nombre"')
        self.assertNotContains(respuesta, 'value="Ana"')

    def test_borrar_el_nombre_deja_de_precargarlo(self):
        self.aprobar(self.crear("Ana"))
        self.carta()
        self.llenar(self.client)

        self.aprobar(self.crear(""))
        self.carta()
        self.llenar(self.client)

        respuesta = self.carta()

        self.assertContains(respuesta, 'name="nombre"')
        self.assertNotContains(respuesta, 'value="Ana"')

    def test_reintento_desde_el_carrito_guarda_el_nombre_nuevo(self):
        primero = self.crear("Ana")
        self.sdk.status.return_value = self.respuesta(primero, "FAILED", -1)
        resolver_intento(primero.pk, confirmar=True)

        segundo = self.crear("Beto")

        self.assertEqual(segundo.pedido_id, primero.pedido_id)
        segundo.pedido.refresh_from_db()
        self.assertEqual(segundo.pedido.nombre, "Beto")

    def test_nombre_queda_en_la_sesion_aunque_el_pago_falle(self):
        self.producto.requiere_mayoria_edad = True
        self.producto.save(update_fields=["requiere_mayoria_edad"])

        respuesta = self.iniciar("Ana")

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Pedido.objects.exists())
        self.assertContains(self.carta(), 'value="Ana"')
