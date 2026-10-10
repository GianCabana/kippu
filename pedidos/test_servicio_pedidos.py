"""Cerrar y abrir el servicio de pedidos por QR (decisión 42)."""
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from mesas.models import Local
from . import test_webpay_demo as base
from .cierre import cerrar_si_inactiva
from .models import Cuenta, IntentoWebpay, Pago, Pedido
from .pagos import ErrorPago, reintentar_pago, resolver_intento

AVISO = "Pedidos cerrados por ahora"


class ServicioPedidosTests(TestCase):
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def setUp(self):
        base.PagoPrevioTests.setUp(self)
        self.local = self.mesa.local

    def cerrar_servicio(self, recibe=False):
        Local.objects.filter(pk=self.local.pk).update(recibe_pedidos=recibe)

    def agregar(self, client=None):
        return (client or self.client).post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]),
            HTTP_HX_REQUEST="true",
        )

    def pagar(self):
        return self.client.post(reverse("pedidos:webpay_cliente", args=[self.mesa.codigo]), {"propina": "0"})

    def carta(self):
        return self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]))

    def cambiar(self, client, accion):
        return client.post(reverse("pedidos:cambiar_servicio", args=[self.local.pk]), {"accion": accion})

    def recibe(self):
        return Local.objects.get(pk=self.local.pk).recibe_pedidos

    def test_servicio_por_defecto_recibe_pedidos(self):
        self.assertTrue(Local.objects.create(nombre="Nuevo", slug="nuevo").recibe_pedidos)

    def test_servicio_cerrado_no_agrega_y_avisa_en_el_carrito(self):
        self.cerrar_servicio()

        respuesta = self.agregar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, AVISO)
        self.assertEqual(self.client.session[self.carrito], {str(self.producto.pk): 2})

    def test_servicio_cerrado_no_empieza_un_pago(self):
        self.cerrar_servicio()

        respuesta = self.pagar()

        self.assertRedirects(respuesta, reverse("carta:por_mesa", args=[self.mesa.codigo]))
        self.assertFalse(Pedido.objects.exists())
        self.assertFalse(IntentoWebpay.objects.exists())
        mensajes = [str(m) for m in respuesta.wsgi_request._messages]
        self.assertTrue(any(AVISO in m for m in mensajes))

    def test_servicio_pago_iniciado_antes_de_cerrar_se_confirma_igual(self):
        intento = self.crear()
        self.cerrar_servicio()

        self.aprobar(intento)

        intento.pedido.refresh_from_db()
        self.assertEqual(intento.pedido.estado, Pedido.Estado.PENDIENTE)
        self.assertTrue(Pago.objects.filter(pedido=intento.pedido).exists())
        cocina = self.operador.get(reverse("pedidos:cocina"))
        self.assertEqual(list(cocina.context["pedidos"]), [intento.pedido])

    def test_servicio_cerrado_doble_clic_devuelve_el_intento_en_curso(self):
        intento = self.crear()
        self.cerrar_servicio()

        respuesta = self.pagar()

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(f"/{intento.pk}/", respuesta.url)
        self.assertEqual(IntentoWebpay.objects.count(), 1)

    def test_servicio_cerrado_no_reintenta_un_pago_rechazado(self):
        intento = self.crear()
        self.sdk.status.return_value = self.respuesta(intento, "FAILED", -1)
        resolver_intento(intento.pk, confirmar=True)
        self.cerrar_servicio()

        with self.assertRaisesMessage(ErrorPago, AVISO):
            reintentar_pago(intento.pk, self.staff, "https://ejemplo.cl/retorno/")
        self.assertEqual(IntentoWebpay.objects.count(), 1)

    def test_servicio_cerrado_la_carta_se_ve_con_aviso_y_sin_botones(self):
        self.cerrar_servicio()

        respuesta = self.carta()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, AVISO)
        self.assertContains(respuesta, self.producto.nombre)
        self.assertNotContains(respuesta, reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]))
        self.assertNotContains(respuesta, "Pagar con Webpay")

    def test_servicio_abierto_la_carta_no_muestra_el_aviso(self):
        self.assertNotContains(self.carta(), AVISO)

    def test_servicio_local_inactivo_sigue_dando_404(self):
        Local.objects.filter(pk=self.local.pk).update(activo=False, recibe_pedidos=False)

        self.assertEqual(self.carta().status_code, 404)

    def test_servicio_solo_el_personal_lo_cambia(self):
        anonimo = Client()

        respuesta = self.cambiar(anonimo, "cerrar")

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("admin:login"), respuesta.url)
        self.assertTrue(self.recibe())

    def test_servicio_cambiar_exige_post(self):
        respuesta = self.operador.get(reverse("pedidos:cambiar_servicio", args=[self.local.pk]))

        self.assertEqual(respuesta.status_code, 405)
        self.assertTrue(self.recibe())

    def test_servicio_personal_cierra_y_abre(self):
        self.assertRedirects(self.cambiar(self.operador, "cerrar"), reverse("pedidos:caja"))
        self.assertFalse(self.recibe())

        self.cambiar(self.operador, "abrir")
        self.assertTrue(self.recibe())

    def test_servicio_cerrar_dos_veces_no_lo_reabre(self):
        self.cambiar(self.operador, "cerrar")
        self.cambiar(self.operador, "cerrar")

        self.assertFalse(self.recibe())

    def test_servicio_accion_invalida_no_cambia_nada(self):
        self.cambiar(self.operador, "alternar")

        self.assertTrue(self.recibe())

    def test_servicio_local_inexistente_da_404(self):
        respuesta = self.operador.post(reverse("pedidos:cambiar_servicio", args=[99999]), {"accion": "cerrar"})

        self.assertEqual(respuesta.status_code, 404)

    def test_servicio_al_reabrir_todo_vuelve_a_funcionar(self):
        self.cerrar_servicio()
        self.cerrar_servicio(recibe=True)

        self.assertContains(self.agregar(), "Agregaste")
        self.assertEqual(self.pagar().status_code, 200)
        self.assertEqual(IntentoWebpay.objects.count(), 1)

    def test_servicio_cerrado_mis_pedidos_sigue_funcionando(self):
        self.aprobar(self.crear())
        self.cerrar_servicio()

        self.assertEqual(self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo])).status_code, 200)
        self.assertEqual(self.client.get(reverse("pedidos:mis_pedidos_estado", args=[self.mesa.codigo])).status_code, 200)

    def test_servicio_cerrado_el_cierre_perezoso_sigue_funcionando(self):
        intento = self.crear()
        self.aprobar(intento)
        Pedido.objects.filter(pk=intento.pedido_id).update(estado=Pedido.Estado.ENTREGADO)
        hace = timezone.now() - timedelta(hours=2)
        Cuenta.objects.filter(pk=intento.cuenta_id).update(creada=hace)
        Pedido.objects.filter(pk=intento.pedido_id).update(creado=hace)
        Pago.objects.all().update(creado=hace)
        IntentoWebpay.objects.all().update(creado=hace, actualizado=hace)
        self.cerrar_servicio()

        self.assertIsNotNone(cerrar_si_inactiva(self.mesa))

    def test_servicio_caja_muestra_el_estado_y_el_boton(self):
        respuesta = self.operador.get(reverse("pedidos:caja"))
        self.assertContains(respuesta, "Recibiendo pedidos")
        self.assertContains(respuesta, "Cerrar pedidos")

        self.cerrar_servicio()
        respuesta = self.operador.get(reverse("pedidos:caja"))
        self.assertContains(respuesta, AVISO.split(" por")[0])
        self.assertContains(respuesta, "Abrir pedidos")
