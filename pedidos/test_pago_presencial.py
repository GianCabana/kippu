"""Pago presencial en caja (D-07, decisión 43): el pedido espera en por_cobrar y solo entra a cocina cuando el personal cobra."""
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from mesas.models import Local
from . import test_webpay_demo as base
from .cierre import cerrar_si_inactiva, revisar_cierre
from .models import Cuenta, IntentoWebpay, Pago, Pedido
from .pagos import resolver_intento

POR_COBRAR = Pedido.Estado.POR_COBRAR


class PagoPresencialBase(TestCase):
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta

    def setUp(self):
        base.PagoPrevioTests.setUp(self)

    def pedir(self, client=None, **datos):
        datos.setdefault("propina", "10")
        return (client or self.client).post(reverse("pedidos:pagar_en_caja", args=[self.mesa.codigo]), datos)

    def pedido(self, client=None, **datos):
        self.pedir(client, **datos)
        return Pedido.objects.filter(estado=POR_COBRAR).latest("pk")

    def cobrar(self, pedido, metodo="efectivo", client=None):
        return (client or self.operador).post(reverse("pedidos:cobrar_presencial", args=[pedido.pk]), {"metodo": metodo})

    def cancelar_en_caja(self, pedido, client=None):
        return (client or self.operador).post(reverse("pedidos:cancelar_presencial", args=[pedido.pk]))

    def cancelar_cliente(self, pedido, client=None):
        return (client or self.client).post(
            reverse("pedidos:cancelar_por_cobrar", args=[self.mesa.codigo, pedido.pk]))

    def envejecer(self, pedido, minutos):
        Pedido.objects.filter(pk=pedido.pk).update(creado=timezone.now() - timedelta(minutes=minutos))

    def estado(self, pedido):
        pedido.refresh_from_db()
        return pedido.estado

    def en_panel(self, pedido, ruta):
        return pedido in list(self.operador.get(reverse(ruta)).context["pedidos"])


class CrearPorCobrarTests(PagoPresencialBase):
    def test_crea_por_cobrar_con_total_del_servidor(self):
        respuesta = self.pedir(precio="1", total="1", monto="1")

        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado, POR_COBRAR)
        self.assertEqual(pedido.propina, Decimal("700"))
        self.assertEqual(pedido.total_con_propina, Decimal("7700"))
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(IntentoWebpay.objects.exists())
        self.assertRedirects(respuesta, reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

    def test_vacia_el_carrito(self):
        self.pedir()

        self.assertEqual(self.client.session.get(self.carrito, {}), {})

    def test_guarda_el_nombre_limpio(self):
        pedido = self.pedido(nombre="Ana<b>2</b>")

        self.assertEqual(pedido.nombre, "Ana b b")

    def test_no_aparece_en_cocina_ni_entregas(self):
        pedido = self.pedido()

        self.assertFalse(self.en_panel(pedido, "pedidos:cocina"))
        self.assertFalse(self.en_panel(pedido, "pedidos:entregas"))

    def test_carrito_vacio_se_rechaza(self):
        self.llenar(self.client, 0)
        session = self.client.session
        session[self.carrito] = {}
        session.save()

        self.pedir()

        self.assertFalse(Pedido.objects.exists())

    def test_sin_declaracion_18_se_rechaza(self):
        self.producto.requiere_mayoria_edad = True
        self.producto.save(update_fields=["requiere_mayoria_edad"])

        self.pedir()
        self.assertFalse(Pedido.objects.exists())

        pedido = self.pedido(confirma_mayoria_edad="si")
        self.assertTrue(pedido.mayoria_edad_confirmada)

    def test_propina_inventada_se_rechaza(self):
        self.pedir(propina="25")

        self.assertFalse(Pedido.objects.exists())

    def test_servicio_cerrado_se_rechaza(self):
        Local.objects.filter(pk=self.mesa.local_id).update(recibe_pedidos=False)

        self.pedir()

        self.assertFalse(Pedido.objects.exists())

    def test_segundo_por_cobrar_del_mismo_navegador_se_rechaza(self):
        self.pedir()
        self.llenar(self.client)

        respuesta = self.pedir()

        self.assertEqual(Pedido.objects.filter(estado=POR_COBRAR).count(), 1)
        self.assertRedirects(respuesta, reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))
        self.assertEqual(self.client.session[self.carrito], {str(self.producto.pk): 2})

    def test_otro_navegador_en_la_misma_mesa_si_puede(self):
        self.pedir()
        otro = Client()
        self.llenar(otro)

        self.pedir(otro)

        self.assertEqual(Pedido.objects.filter(estado=POR_COBRAR).count(), 2)

    def test_con_webpay_en_curso_no_se_crea(self):
        self.crear()

        self.pedir()

        self.assertFalse(Pedido.objects.filter(estado=POR_COBRAR).exists())

    def test_reusa_el_borrador_de_un_webpay_rechazado(self):
        intento = self.crear()
        self.sdk.status.return_value = self.respuesta(intento, "FAILED", -1)
        resolver_intento(intento.pk)

        self.pedir()

        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Pedido.objects.get().estado, POR_COBRAR)

    def test_webpay_sigue_funcionando_con_un_por_cobrar_abierto(self):
        self.pedir()
        self.llenar(self.client)

        intento = self.crear()

        self.assertEqual(intento.pedido.estado, Pedido.Estado.SIN_PAGAR)
        self.assertEqual(Pedido.objects.filter(estado=POR_COBRAR).count(), 1)


class CobrarEnCajaTests(PagoPresencialBase):
    def test_cobrar_crea_un_pago_y_manda_a_cocina(self):
        pedido = self.pedido()

        self.cobrar(pedido, "debito")

        pago = Pago.objects.get()
        self.assertEqual(pago.pedido, pedido)
        self.assertEqual(pago.metodo, Pago.Metodo.DEBITO)
        self.assertEqual(pago.registrado_por, self.staff)
        self.assertEqual(pago.monto, Decimal("7700"))
        self.assertEqual(self.estado(pedido), Pedido.Estado.PENDIENTE)
        self.assertTrue(self.en_panel(pedido, "pedidos:cocina"))

    def test_doble_envio_crea_un_solo_pago(self):
        pedido = self.pedido()

        self.cobrar(pedido)
        self.cobrar(pedido, "credito")

        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Pago.objects.get().metodo, Pago.Metodo.EFECTIVO)

    def test_metodos_no_permitidos_se_rechazan(self):
        pedido = self.pedido()

        for metodo in ("transferencia", "webpay", "bitcoin", ""):
            self.cobrar(pedido, metodo)

        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.estado(pedido), POR_COBRAR)

    def test_sin_sesion_de_personal_va_al_login(self):
        pedido = self.pedido()

        respuesta = self.cobrar(pedido, client=Client())

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta["Location"])
        self.assertFalse(Pago.objects.exists())

    def test_cobrar_por_get_no_se_permite(self):
        pedido = self.pedido()

        respuesta = self.operador.get(reverse("pedidos:cobrar_presencial", args=[pedido.pk]))

        self.assertEqual(respuesta.status_code, 405)

    def test_caja_muestra_el_pedido_con_su_total(self):
        pedido = self.pedido(nombre="Ana")

        respuesta = self.operador.get(reverse("pedidos:caja"))

        self.assertContains(respuesta, "Por cobrar")
        self.assertContains(respuesta, f"Pedido #{pedido.pk}")
        self.assertContains(respuesta, "$7.700")
        self.assertContains(respuesta, "Ana")
        self.assertContains(respuesta, reverse("pedidos:cobrar_presencial", args=[pedido.pk]))

    def test_cobrar_con_el_servicio_cerrado_se_permite(self):
        pedido = self.pedido()
        Local.objects.filter(pk=self.mesa.local_id).update(recibe_pedidos=False)

        self.cobrar(pedido)

        self.assertEqual(self.estado(pedido), Pedido.Estado.PENDIENTE)


class CancelarPorCobrarTests(PagoPresencialBase):
    def test_cancelar_desde_caja(self):
        pedido = self.pedido()

        self.cancelar_en_caja(pedido)

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_cobrar_un_cancelado_se_rechaza(self):
        pedido = self.pedido()
        self.cancelar_en_caja(pedido)

        self.cobrar(pedido)

        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_caja_no_cancela_un_pedido_ya_cobrado(self):
        pedido = self.pedido()
        self.cobrar(pedido)

        self.cancelar_en_caja(pedido)

        self.assertEqual(self.estado(pedido), Pedido.Estado.PENDIENTE)

    def test_el_cliente_cancela_el_suyo(self):
        pedido = self.pedido()

        self.cancelar_cliente(pedido)

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_otro_navegador_no_puede_cancelarlo(self):
        pedido = self.pedido()
        otro = Client()
        self.llenar(otro)

        respuesta = self.cancelar_cliente(pedido, otro)

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.estado(pedido), POR_COBRAR)

    def test_el_cliente_no_cancela_uno_ya_cobrado(self):
        pedido = self.pedido()
        self.cobrar(pedido)

        self.cancelar_cliente(pedido)

        self.assertEqual(self.estado(pedido), Pedido.Estado.PENDIENTE)

    def test_cancelado_permite_pedir_otro(self):
        pedido = self.pedido()
        self.cancelar_cliente(pedido)
        self.llenar(self.client)

        self.pedir()

        self.assertEqual(Pedido.objects.filter(estado=POR_COBRAR).count(), 1)


class VencimientoTests(PagoPresencialBase):
    def test_a_los_29_minutos_sigue(self):
        pedido = self.pedido()
        self.envejecer(pedido, 29)

        self.operador.get(reverse("pedidos:caja"))

        self.assertEqual(self.estado(pedido), POR_COBRAR)

    def test_a_los_31_minutos_vence_al_abrir_caja(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)

        self.operador.get(reverse("pedidos:caja"))

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_a_los_31_minutos_vence_al_abrir_la_carta(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)

        self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]))

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_a_los_31_minutos_vence_al_abrir_mis_pedidos(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)

        self.client.get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_cobrar_un_vencido_se_rechaza(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)

        self.cobrar(pedido)

        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)

    def test_vencido_no_impide_pedir_otro(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)
        self.llenar(self.client)

        self.pedir()

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)
        self.assertEqual(Pedido.objects.filter(estado=POR_COBRAR).count(), 1)


class CierreConPorCobrarTests(PagoPresencialBase):
    def cerrar_mesa(self, cuenta):
        return self.operador.post(reverse("pedidos:cerrar_mesa", args=[cuenta.pk]))

    def test_por_cobrar_vigente_impide_cerrar(self):
        pedido = self.pedido()

        revision = revisar_cierre(pedido.cuenta)
        self.cerrar_mesa(pedido.cuenta)

        self.assertFalse(revision["puede_cerrar"])
        self.assertIn("por pagar en caja", revision["motivo"])
        self.assertEqual(Cuenta.objects.get().estado, Cuenta.Estado.ABIERTA)

    def test_cobrado_y_entregado_permite_cerrar(self):
        pedido = self.pedido()
        self.cobrar(pedido)
        Pedido.objects.filter(pk=pedido.pk).update(estado=Pedido.Estado.ENTREGADO)

        self.cerrar_mesa(pedido.cuenta)

        self.assertEqual(Cuenta.objects.get().estado, Cuenta.Estado.CERRADA)

    def test_cerrar_mesa_cancela_antes_el_vencido(self):
        pedido = self.pedido()
        self.envejecer(pedido, 31)

        self.cerrar_mesa(pedido.cuenta)

        self.assertEqual(self.estado(pedido), Pedido.Estado.CANCELADO)
        self.assertEqual(Cuenta.objects.get().estado, Cuenta.Estado.CERRADA)

    def test_cierre_perezoso_no_cierra_con_por_cobrar_vigente(self):
        pedido = self.pedido()
        Cuenta.objects.filter(pk=pedido.cuenta_id).update(creada=timezone.now() - timedelta(hours=3))
        self.envejecer(pedido, 10)

        self.assertIsNone(cerrar_si_inactiva(self.mesa, ahora=timezone.now() + timedelta(hours=2)))

        self.assertEqual(Cuenta.objects.get().estado, Cuenta.Estado.ABIERTA)
        self.assertEqual(self.estado(pedido), POR_COBRAR)


class MisPedidosPorCobrarTests(PagoPresencialBase):
    def mis_pedidos(self, client=None):
        return (client or self.client).get(reverse("pedidos:mis_pedidos", args=[self.mesa.codigo]))

    def fragmento(self, client=None):
        return (client or self.client).get(reverse("pedidos:mis_pedidos_estado", args=[self.mesa.codigo]))

    def test_ticket_por_pagar_en_caja(self):
        pedido = self.pedido()

        respuesta = self.mis_pedidos()

        self.assertContains(respuesta, "Por pagar en caja")
        self.assertContains(respuesta, f"#{pedido.pk}")
        self.assertContains(respuesta, "$7.700")
        self.assertContains(respuesta, reverse("pedidos:cancelar_por_cobrar", args=[self.mesa.codigo, pedido.pk]))
        self.assertNotContains(respuesta, "<b>Pagado</b>", html=False)

    def test_fragmento_sigue_consultando_mientras_espera_caja(self):
        self.pedido()

        respuesta = self.fragmento()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Por pagar en caja")

    def test_fragmento_muestra_en_cola_al_cobrar(self):
        pedido = self.pedido()
        self.cobrar(pedido)

        respuesta = self.fragmento()

        self.assertContains(respuesta, "en cola")
        self.assertNotContains(respuesta, "Por pagar en caja")

    def test_otro_navegador_no_ve_el_ticket(self):
        pedido = self.pedido()
        otro = Client()
        self.llenar(otro)

        self.assertNotContains(self.mis_pedidos(otro), f"#{pedido.pk}")
        self.assertNotContains(self.fragmento(otro), f"sello-{pedido.pk}", status_code=286)

    def test_carrito_ofrece_pagar_en_caja(self):
        respuesta = self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]), HTTP_HX_REQUEST="true")

        self.assertContains(respuesta, "Pagar en caja")
        self.assertContains(respuesta, reverse("pedidos:pagar_en_caja", args=[self.mesa.codigo]))
