from django.test import TestCase
from django.urls import reverse

from carta.models import Categoria, Producto
from mesas.models import Mesa

from .models import Cuenta, DetallePedido, Pago, Pedido


class MisPedidosTicketTests(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=994, activa=True)
        self.cuenta = Cuenta.objects.create(mesa=self.mesa)
        categoria = Categoria.objects.create(nombre='Ticket')
        self.producto = Producto.objects.create(nombre='Lomo saltado', categoria=categoria, precio=13900)
        self.url = reverse('pedidos:mis_pedidos', args=[self.mesa.codigo])

    def crear_pedido(self, estado, pagado=True):
        pedido = Pedido.objects.create(mesa=self.mesa, cuenta=self.cuenta, estado=estado, propina=1390)
        DetallePedido.objects.create(pedido=pedido, producto=self.producto, nombre_producto='Lomo saltado',
                                     precio_unitario=13900, cantidad=1)
        if pagado:
            Pago.objects.create(cuenta=self.cuenta, pedido=pedido, monto=15290, metodo='webpay')
        sesion = self.client.session
        sesion[f'pedidos_{self.mesa.codigo}'] = sesion.get(f'pedidos_{self.mesa.codigo}', []) + [pedido.pk]
        sesion.save()
        return pedido

    def test_pedido_pagado_en_cola(self):
        self.crear_pedido('pendiente')
        r = self.client.get(self.url)
        self.assertContains(r, 'Pagado')
        self.assertContains(r, 'En cocina · en cola')
        self.assertContains(r, '$15.290')
        self.assertContains(r, 'class="tk-pasos"')
        self.assertContains(r, 'Pedir algo más')
        self.assertContains(r, 'http-equiv="refresh" content="15"')

    def test_estados_de_la_linea_de_tiempo(self):
        pedido = self.crear_pedido('en_preparacion')
        self.assertContains(self.client.get(self.url), 'En cocina · preparando')
        Pedido.objects.filter(pk=pedido.pk).update(estado='listo')
        self.assertContains(self.client.get(self.url), 'Te lo llevamos a la mesa')

    def test_pago_pendiente_y_cancelado(self):
        self.crear_pedido('sin_pagar', pagado=False)
        r = self.client.get(self.url)
        self.assertContains(r, 'Pago pendiente')
        Pedido.objects.update(estado='cancelado')
        r = self.client.get(self.url)
        self.assertContains(r, 'Cancelado')
        self.assertNotContains(r, 'class="tk-pasos"')

    def test_pedidos_anteriores_como_ticket_corto(self):
        self.crear_pedido('entregado')
        self.crear_pedido('pendiente')
        r = self.client.get(self.url)
        self.assertContains(r, 'Pedidos anteriores')
        self.assertContains(r, 'tk tk--corto')
