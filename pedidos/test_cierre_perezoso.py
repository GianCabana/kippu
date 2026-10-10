from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from carta.models import Categoria, Producto
from mesas.models import Mesa

from .models import Cuenta, DetallePedido, IntentoWebpay, Pago, Pedido


class CierrePerezosoTests(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=903, activa=True)
        self.cuenta = Cuenta.objects.create(mesa=self.mesa)
        categoria = Categoria.objects.create(nombre='Perezoso', local=self.mesa.local)
        self.producto = Producto.objects.create(categoria=categoria, nombre='Producto', precio=3500)
        self.url_carta = reverse('carta:por_mesa', args=[self.mesa.codigo])

    def crear_pedido(self, estado='entregado', intento='autorizado', pagado=True):
        pedido = Pedido.objects.create(mesa=self.mesa, cuenta=self.cuenta, estado=estado)
        DetallePedido.objects.create(pedido=pedido, producto=self.producto, nombre_producto='Producto',
                                     precio_unitario=3500, cantidad=1)
        intento = IntentoWebpay.objects.create(cuenta=self.cuenta, pedido=pedido, monto=3500, estado=intento)
        if pagado:
            Pago.objects.create(cuenta=self.cuenta, pedido=pedido, intento_webpay=intento,
                                monto=3500, metodo='webpay')
        return pedido

    def envejecer(self, minutos):
        hace = timezone.now() - timedelta(minutes=minutos)
        Cuenta.objects.filter(pk=self.cuenta.pk).update(creada=hace)
        Pedido.objects.filter(cuenta=self.cuenta).update(creado=hace)
        Pago.objects.filter(cuenta=self.cuenta).update(creado=hace)
        IntentoWebpay.objects.filter(cuenta=self.cuenta).update(creado=hace, actualizado=hace)

    def abrir_carta(self):
        respuesta = self.client.get(self.url_carta)
        self.assertEqual(respuesta.status_code, 200)
        self.cuenta.refresh_from_db()

    def test_todo_entregado_y_mas_de_una_hora_cierra_la_cuenta(self):
        self.crear_pedido()
        self.envejecer(61)
        self.abrir_carta()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.CERRADA)
        self.assertIsNotNone(self.cuenta.cerrada)
        self.assertFalse(Cuenta.objects.filter(mesa=self.mesa, estado='abierta').exists())
        nueva, _ = Cuenta.objects.get_or_create(mesa=self.mesa, estado=Cuenta.Estado.ABIERTA)
        self.assertNotEqual(nueva.pk, self.cuenta.pk)

    def test_todo_entregado_pero_veinte_minutos_sigue_abierta(self):
        self.crear_pedido()
        self.envejecer(20)
        self.abrir_carta()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.ABIERTA)

    def test_pedido_pagado_sin_entregar_sigue_abierta(self):
        self.crear_pedido(estado='listo')
        self.envejecer(120)
        self.abrir_carta()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.ABIERTA)

    def test_pago_en_curso_sigue_abierta(self):
        self.crear_pedido(estado='sin_pagar', intento='iniciado', pagado=False)
        self.envejecer(120)
        self.abrir_carta()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.ABIERTA)

    def test_abrir_la_carta_dos_veces_no_crea_cuentas(self):
        self.crear_pedido()
        self.envejecer(61)
        self.abrir_carta()
        self.abrir_carta()
        self.assertEqual(Cuenta.objects.filter(mesa=self.mesa).count(), 1)
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.CERRADA)

    def test_sin_cuenta_abierta_abrir_la_carta_no_crea_ninguna(self):
        Cuenta.objects.filter(pk=self.cuenta.pk).update(estado='cerrada', cerrada=timezone.now())
        self.abrir_carta()
        self.assertEqual(Cuenta.objects.filter(mesa=self.mesa).count(), 1)

    def test_cuenta_abandonada_sin_pagos_se_cierra_y_cancela_el_borrador(self):
        borrador = self.crear_pedido(estado='sin_pagar', intento='anulado', pagado=False)
        self.envejecer(61)
        self.abrir_carta()
        borrador.refresh_from_db()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.CERRADA)
        self.assertEqual(borrador.estado, Pedido.Estado.CANCELADO)

    def test_actividad_reciente_de_un_intento_mantiene_abierta(self):
        self.crear_pedido()
        self.envejecer(120)
        IntentoWebpay.objects.filter(cuenta=self.cuenta).update(
            actualizado=timezone.now() - timedelta(minutes=10))
        self.abrir_carta()
        self.assertEqual(self.cuenta.estado, Cuenta.Estado.ABIERTA)
