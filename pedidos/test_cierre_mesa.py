from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from mesas.models import Mesa
from carta.models import Producto
from .models import Cuenta, Pedido, DetallePedido, Pago, IntentoWebpay
from .cierre import cerrar_cuenta
from .pagos import ErrorPago


class CierreMesaTests(TestCase):
    def setUp(self):
        self.mesa=Mesa.objects.create(numero=902,activa=True)
        self.cuenta=Cuenta.objects.create(mesa=self.mesa)
        categoria=Producto._meta.get_field('categoria').remote_field.model.objects.create(nombre='Cierre',activa=True)
        self.producto=Producto.objects.create(categoria=categoria,nombre='Producto',precio=3500,disponible=True)
        self.pedido=Pedido.objects.create(mesa=self.mesa,cuenta=self.cuenta,estado='entregado')
        DetallePedido.objects.create(pedido=self.pedido,producto=self.producto,nombre_producto='Producto',precio_unitario=3500,cantidad=1)
        self.intento=IntentoWebpay.objects.create(cuenta=self.cuenta,pedido=self.pedido,monto=3500,estado='autorizado')
        self.pago=Pago.objects.create(cuenta=self.cuenta,pedido=self.pedido,intento_webpay=self.intento,monto=3500,metodo='webpay')
        self.user=get_user_model().objects.create_user(username='personal_cierre',password='Pruebas123!',is_staff=True)
        self.client.force_login(self.user)
        self.url=reverse('pedidos:cerrar_mesa',args=[self.cuenta.pk])

    def test_cierre_conserva_historial_y_qr(self):
        codigo=self.mesa.codigo
        r=self.client.post(self.url)
        self.assertEqual(r.status_code,302)
        self.cuenta.refresh_from_db();self.mesa.refresh_from_db()
        self.assertEqual(self.cuenta.estado,'cerrada')
        self.assertIsNotNone(self.cuenta.cerrada)
        self.assertEqual(self.mesa.codigo,codigo)
        self.assertTrue(self.mesa.activa)
        self.assertTrue(Pago.objects.filter(pk=self.pago.pk).exists())
        self.assertTrue(Pedido.objects.filter(pk=self.pedido.pk).exists())
        self.assertContains(self.client.get(reverse('pedidos:caja')),'Últimos cierres')

    def test_repetir_no_modifica_fecha(self):
        cuenta,nuevo=cerrar_cuenta(self.cuenta.pk)
        fecha=cuenta.cerrada
        cuenta,nuevo=cerrar_cuenta(self.cuenta.pk)
        self.assertFalse(nuevo)
        self.assertEqual(cuenta.cerrada,fecha)

    def test_bloquea_pedido_pagado_no_entregado(self):
        for estado in ('sin_pagar','pendiente','en_preparacion','listo','cancelado'):
            with self.subTest(estado=estado):
                Pedido.objects.filter(pk=self.pedido.pk).update(estado=estado)
                with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)
                self.cuenta.refresh_from_db();self.assertEqual(self.cuenta.estado,'abierta')

    def test_bloquea_cualquier_pago_incierto(self):
        for estado in ('creado','iniciado','por_verificar'):
            with self.subTest(estado=estado):
                IntentoWebpay.objects.filter(pk=self.intento.pk).update(estado=estado)
                with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)

    def test_bloquea_pedido_sin_pago_y_autorizacion_sin_registro(self):
        self.pago.delete()
        with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)
        IntentoWebpay.objects.filter(pk=self.intento.pk).update(estado='rechazado')
        with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)

    def test_monto_incongruente_y_observacion_bloquean(self):
        Pago.objects.filter(pk=self.pago.pk).update(monto=1)
        with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)
        Pago.objects.filter(pk=self.pago.pk).update(monto=3500)
        IntentoWebpay.objects.filter(pk=self.intento.pk).update(observacion='Revisar')
        with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)

    def test_legacy_no_se_cierra_por_suposicion(self):
        Pago.objects.filter(pk=self.pago.pk).update(pedido=None)
        with self.assertRaises(ErrorPago):cerrar_cuenta(self.cuenta.pk)

    def test_staff_post_csrf(self):
        self.assertEqual(self.client.get(self.url).status_code,405)
        self.assertEqual(Client().post(self.url).status_code,302)
        anon=get_user_model().objects.create_user(username='cliente_cierre',password='Pruebas123!')
        c=Client();c.force_login(anon)
        self.assertEqual(c.post(self.url).status_code,302)
        c=Client(enforce_csrf_checks=True);c.force_login(self.user)
        self.assertEqual(c.post(self.url).status_code,403)
        self.cuenta.refresh_from_db();self.assertEqual(self.cuenta.estado,'abierta')

    def test_nueva_compra_abre_otra_cuenta(self):
        cerrar_cuenta(self.cuenta.pk)
        cliente=Client();session=cliente.session
        session[f'carrito_{self.mesa.codigo}']={str(self.producto.pk):1};session.save()
        with patch('pedidos.pagos.obtener_webpay') as factory:
            factory.return_value.create.return_value={'token':'n'*64,'url':'https://webpay3gint.transbank.cl/webpayserver/initTransaction'}
            r=cliente.post(reverse('pedidos:webpay_cliente',args=[self.mesa.codigo]))
        self.assertEqual(r.status_code,200)
        nueva=r.context['intento'].cuenta
        self.assertNotEqual(nueva.pk,self.cuenta.pk)
        self.assertEqual(nueva.estado,'abierta')
        self.assertEqual(nueva.mesa_id,self.mesa.pk)

    def test_descarta_borrador_y_permite_su_carrito_en_nueva_visita(self):
        cliente=Client();session=cliente.session
        session[f'carrito_{self.mesa.codigo}']={str(self.producto.pk):2};session.save()
        with patch('pedidos.pagos.obtener_webpay') as factory:
            factory.return_value.create.side_effect=TimeoutError()
            cliente.post(reverse('pedidos:webpay_cliente',args=[self.mesa.codigo]))
            borrador=Pedido.objects.get(estado='sin_pagar')
            self.client.post(self.url)
            borrador.refresh_from_db();self.assertEqual(borrador.estado,'cancelado')
            self.assertEqual(cliente.session[f'carrito_{self.mesa.codigo}'],{str(self.producto.pk):2})
            factory.return_value.create.side_effect=None
            factory.return_value.create.return_value={'token':'b'*64,'url':'https://webpay3gint.transbank.cl/webpayserver/initTransaction'}
            r=cliente.post(reverse('pedidos:webpay_cliente',args=[self.mesa.codigo]))
        self.assertEqual(r.status_code,200)
        self.assertNotEqual(r.context['intento'].cuenta_id,self.cuenta.pk)
        self.assertEqual(r.context['intento'].monto,Decimal('7000'))
        self.pedido.refresh_from_db();self.assertEqual(self.pedido.estado,'entregado')
