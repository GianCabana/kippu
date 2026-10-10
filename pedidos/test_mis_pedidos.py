from django.test import Client, TestCase
from django.urls import reverse

from carta.models import Categoria, Producto
from mesas.models import Mesa

from .models import Cuenta, DetallePedido, Pago, Pedido


class MisPedidosBase(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=994, activa=True)
        self.cuenta = Cuenta.objects.create(mesa=self.mesa)
        categoria = Categoria.objects.create(nombre='Ticket')
        self.producto = Producto.objects.create(nombre='Lomo saltado', categoria=categoria, precio=13900)
        self.url = reverse('pedidos:mis_pedidos', args=[self.mesa.codigo])
        self.url_estado = reverse('pedidos:mis_pedidos_estado', args=[self.mesa.codigo])

    def crear_pedido(self, estado, pagado=True, cliente=None):
        cliente = cliente or self.client
        pedido = Pedido.objects.create(mesa=self.mesa, cuenta=self.cuenta, estado=estado, propina=1390)
        DetallePedido.objects.create(pedido=pedido, producto=self.producto, nombre_producto='Lomo saltado',
                                     precio_unitario=13900, cantidad=1)
        if pagado:
            Pago.objects.create(cuenta=self.cuenta, pedido=pedido, monto=15290, metodo='webpay')
        sesion = cliente.session
        sesion[f'pedidos_{self.mesa.codigo}'] = sesion.get(f'pedidos_{self.mesa.codigo}', []) + [pedido.pk]
        sesion.save()
        return pedido


class MisPedidosTicketTests(MisPedidosBase):
    def test_pedido_pagado_en_cola(self):
        self.crear_pedido('pendiente')
        r = self.client.get(self.url)
        self.assertContains(r, 'Pagado')
        self.assertContains(r, 'En cocina · en cola')
        self.assertContains(r, '$15.290')
        self.assertContains(r, 'class="tk-pasos"')
        self.assertContains(r, 'Pedir algo más')
        self.assertNotContains(r, 'http-equiv="refresh"')
        self.assertContains(r, f'hx-get="{self.url_estado}"')

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

    def test_sin_pedidos_activos_la_pagina_no_consulta(self):
        self.crear_pedido('entregado')
        self.assertNotContains(self.client.get(self.url), 'hx-get=')


class EstadoMisPedidosTests(MisPedidosBase):
    def test_fragmento_trae_el_estado_actual(self):
        pedido = self.crear_pedido('en_preparacion')
        r = self.client.get(self.url_estado)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'En cocina · preparando')
        self.assertContains(r, f'id="vivo-{pedido.pk}" hx-swap-oob="innerHTML"')
        self.assertContains(r, f'id="sello-{pedido.pk}" hx-swap-oob="innerHTML"')
        self.assertNotContains(r, 'Lomo saltado')
        Pedido.objects.filter(pk=pedido.pk).update(estado='listo')
        self.assertContains(self.client.get(self.url_estado), 'Te lo llevamos a la mesa')

    def test_fragmento_no_trae_pedidos_de_otro_navegador(self):
        propio = self.crear_pedido('pendiente')
        ajeno = self.crear_pedido('en_preparacion', cliente=Client())
        r = self.client.get(self.url_estado)
        self.assertContains(r, f'sello-{propio.pk}')
        self.assertNotContains(r, f'sello-{ajeno.pk}')
        self.assertNotContains(r, f'vivo-{ajeno.pk}')
        self.assertNotContains(r, 'En cocina · preparando')

    def test_fragmento_sin_pedidos_propios_no_trae_nada(self):
        self.crear_pedido('pendiente', cliente=Client())
        r = self.client.get(self.url_estado)
        self.assertNotContains(r, 'sello-', status_code=286)

    def test_deja_de_consultar_cuando_todo_termino(self):
        pedido = self.crear_pedido('listo')
        self.assertEqual(self.client.get(self.url_estado).status_code, 200)
        Pedido.objects.filter(pk=pedido.pk).update(estado='entregado')
        self.crear_pedido('cancelado', pagado=False)
        r = self.client.get(self.url_estado)
        self.assertEqual(r.status_code, 286)
        self.assertContains(r, 'Entregado', status_code=286)

    def test_mesa_inactiva_responde_404(self):
        self.crear_pedido('pendiente')
        Mesa.objects.filter(pk=self.mesa.pk).update(activa=False)
        self.assertEqual(self.client.get(self.url_estado).status_code, 404)
