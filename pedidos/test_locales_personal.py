"""D-14 (Varios restaurantes) en el panel: cada persona del personal ve y toca solo su local (regla 5)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from mesas.models import Local, Mesa, PerfilPersonal

from .models import Cuenta, IntentoWebpay, Pago, Pedido


def personal(nombre, local=None, **extra):
    usuario = get_user_model().objects.create_user(username=nombre, password="Pruebas123!", is_staff=True, **extra)
    if local:
        PerfilPersonal.objects.create(usuario=usuario, local=local)
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


class LocalesDelPersonalTests(TestCase):
    def setUp(self):
        self.causa = Local.objects.create(nombre="Causa Uno", slug="causa-uno")
        self.otro = Local.objects.create(nombre="Otro Dos", slug="otro-dos")
        self.mesa_causa = Mesa.objects.create(local=self.causa, numero=1)
        self.mesa_otro = Mesa.objects.create(local=self.otro, numero=1)
        self.cuenta_causa = Cuenta.objects.create(mesa=self.mesa_causa)
        self.cuenta_otro = Cuenta.objects.create(mesa=self.mesa_otro)
        self.ana = personal("ana_causa", self.causa)
        self.beto = personal("beto_otro", self.otro)

    def pedido(self, cuenta, estado, pagado=True):
        pedido = Pedido.objects.create(mesa=cuenta.mesa, cuenta=cuenta, estado=estado)
        if pagado:
            Pago.objects.create(cuenta=cuenta, pedido=pedido, monto=Decimal("5000"), metodo="efectivo")
        return pedido

    def estado(self, pedido):
        pedido.refresh_from_db()
        return pedido.estado

    # Pantallas: solo el local propio

    def test_cocina_solo_muestra_su_local(self):
        propio = self.pedido(self.cuenta_causa, Pedido.Estado.PENDIENTE)
        ajeno = self.pedido(self.cuenta_otro, Pedido.Estado.PENDIENTE)
        pedidos = list(self.ana.get(reverse("pedidos:cocina")).context["pedidos"])
        self.assertEqual(pedidos, [propio])
        self.assertNotIn(ajeno, pedidos)

    def test_entregas_solo_muestra_su_local(self):
        propio = self.pedido(self.cuenta_causa, Pedido.Estado.LISTO)
        self.pedido(self.cuenta_otro, Pedido.Estado.LISTO)
        self.assertEqual(list(self.ana.get(reverse("pedidos:entregas")).context["pedidos"]), [propio])

    def test_caja_solo_muestra_su_local(self):
        por_cobrar = self.pedido(self.cuenta_otro, Pedido.Estado.POR_COBRAR, pagado=False)
        self.pedido(self.cuenta_otro, Pedido.Estado.ENTREGADO)
        r = self.ana.get(reverse("pedidos:caja"))
        self.assertEqual(list(r.context["locales"]), [self.causa])
        self.assertEqual(list(r.context["por_cobrar"]), [])
        self.assertEqual(list(r.context["pagos"]), [])
        self.assertEqual([c.pk for c in r.context["cuentas"]], [self.cuenta_causa.pk])
        self.assertNotContains(r, "Otro Dos")
        self.assertNotContains(r, f"Pedido #{por_cobrar.pk}")

    def test_las_listas_de_caja_solo_muestran_su_local(self):
        self.pedido(self.cuenta_otro, Pedido.Estado.ENTREGADO)
        r = self.ana.get(reverse("pedidos:caja_listas"), HTTP_HX_REQUEST="true")
        self.assertEqual(list(r.context["pagos"]), [])
        self.assertNotContains(r, "Otro Dos")

    def test_pagos_por_verificar_solo_de_su_local(self):
        IntentoWebpay.objects.create(cuenta=self.cuenta_otro, monto=Decimal("5000"),
                                     estado=IntentoWebpay.Estado.POR_VERIFICAR)
        self.assertEqual(list(self.ana.get(reverse("pedidos:caja")).context["pendientes"]), [])

    def test_recuento_solo_suma_su_local(self):
        self.pedido(self.cuenta_causa, Pedido.Estado.ENTREGADO)
        self.pedido(self.cuenta_otro, Pedido.Estado.ENTREGADO)
        locales = self.ana.get(reverse("pedidos:recuento_caja")).context["locales"]
        self.assertEqual([l["local"] for l in locales], ["Causa Uno"])
        self.assertEqual(locales[0]["total"], 5000)

    def test_la_barra_dice_el_local(self):
        self.assertContains(self.ana.get(reverse("pedidos:caja")), "· panel · Causa Uno")

    # Acciones: lo del otro local da 404 y no cambia nada

    def test_cocina_no_cambia_un_pedido_de_otro_local(self):
        ajeno = self.pedido(self.cuenta_otro, Pedido.Estado.PENDIENTE)
        r = self.ana.post(reverse("pedidos:cambiar_estado", args=[ajeno.pk]), {"estado": "en_preparacion"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.estado(ajeno), Pedido.Estado.PENDIENTE)

    def test_entregas_no_entrega_un_pedido_de_otro_local(self):
        ajeno = self.pedido(self.cuenta_otro, Pedido.Estado.LISTO)
        r = self.ana.post(reverse("pedidos:marcar_entregado", args=[ajeno.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.estado(ajeno), Pedido.Estado.LISTO)

    def test_caja_no_cobra_ni_anula_un_pedido_de_otro_local(self):
        ajeno = self.pedido(self.cuenta_otro, Pedido.Estado.POR_COBRAR, pagado=False)
        r = self.ana.post(reverse("pedidos:cobrar_presencial", args=[ajeno.pk]), {"metodo": "efectivo"})
        self.assertEqual(r.status_code, 404)
        r = self.ana.post(reverse("pedidos:cancelar_presencial", args=[ajeno.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.estado(ajeno), Pedido.Estado.POR_COBRAR)
        self.assertFalse(Pago.objects.filter(pedido=ajeno).exists())

    def test_su_propio_pedido_si_lo_puede_anular(self):
        # El cobro completo de un pedido propio lo prueban las pruebas de pago presencial.
        propio = self.pedido(self.cuenta_causa, Pedido.Estado.POR_COBRAR, pagado=False)
        r = self.ana.post(reverse("pedidos:cancelar_presencial", args=[propio.pk]))
        self.assertRedirects(r, reverse("pedidos:caja"), fetch_redirect_response=False)
        self.assertEqual(self.estado(propio), Pedido.Estado.CANCELADO)

    def test_caja_no_cierra_la_mesa_de_otro_local(self):
        r = self.ana.post(reverse("pedidos:cerrar_mesa", args=[self.cuenta_otro.pk]))
        self.assertEqual(r.status_code, 404)
        self.cuenta_otro.refresh_from_db()
        self.assertEqual(self.cuenta_otro.estado, Cuenta.Estado.ABIERTA)

    def test_el_servicio_que_se_cierra_es_el_del_usuario(self):
        self.assertEqual(reverse("pedidos:cambiar_servicio"), "/pedidos/caja/servicio/")
        self.beto.post(reverse("pedidos:cambiar_servicio"), {"accion": "cerrar"})
        self.causa.refresh_from_db()
        self.otro.refresh_from_db()
        self.assertTrue(self.causa.recibe_pedidos)
        self.assertFalse(self.otro.recibe_pedidos)

    def test_webpay_el_personal_solo_ve_sin_firma_los_pagos_de_su_local(self):
        ajeno = IntentoWebpay.objects.create(cuenta=self.cuenta_otro, monto=Decimal("5000"),
                                             estado=IntentoWebpay.Estado.POR_VERIFICAR)
        propio = IntentoWebpay.objects.create(cuenta=self.cuenta_causa, monto=Decimal("5000"),
                                              estado=IntentoWebpay.Estado.POR_VERIFICAR)
        self.assertEqual(self.ana.get(reverse("pedidos:webpay_resultado", args=[ajeno.pk])).status_code, 404)
        self.assertEqual(self.ana.post(reverse("pedidos:webpay_verificar", args=[ajeno.pk])).status_code, 404)
        r = self.ana.get(reverse("pedidos:webpay_resultado", args=[propio.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["personal"])

    # Sin local asignado: nada del panel, ni siendo superusuario

    def test_personal_sin_local_no_ve_datos(self):
        sin_local = personal("sin_local")
        self.pedido(self.cuenta_causa, Pedido.Estado.PENDIENTE)
        for ruta in ("pedidos:cocina", "pedidos:entregas", "pedidos:caja", "pedidos:recuento_caja"):
            r = sin_local.get(reverse(ruta))
            self.assertEqual(r.status_code, 403, ruta)
            self.assertContains(r, "no tiene un local asignado", status_code=403)
            self.assertNotContains(r, "Causa Uno", status_code=403)

    def test_superusuario_sin_local_tampoco_ve_datos(self):
        jefe = personal("jefe", is_superuser=True)
        self.assertEqual(jefe.get(reverse("pedidos:caja")).status_code, 403)
        self.assertEqual(jefe.get(reverse("pedidos:caja_listas"), HTTP_HX_REQUEST="true").status_code, 403)

    def test_personal_sin_local_no_puede_actuar(self):
        sin_local = personal("sin_local_accion")
        propio = self.pedido(self.cuenta_causa, Pedido.Estado.POR_COBRAR, pagado=False)
        r = sin_local.post(reverse("pedidos:cobrar_presencial", args=[propio.pk]), {"metodo": "efectivo"})
        self.assertEqual(r.status_code, 403)
        r = sin_local.post(reverse("pedidos:cambiar_servicio"), {"accion": "cerrar"})
        self.assertEqual(r.status_code, 403)
        self.causa.refresh_from_db()
        self.assertTrue(self.causa.recibe_pedidos)
        self.assertFalse(Pago.objects.exists())

    def test_local_desactivado_cuenta_como_sin_local(self):
        Local.objects.filter(pk=self.causa.pk).update(activo=False)
        self.assertEqual(self.ana.get(reverse("pedidos:caja")).status_code, 403)
