"""Pruebas del pago previo. SDK simulado: no se hacen cobros ni llamadas remotas."""
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from mesas.models import Mesa
from carta.models import Producto
from .models import Cuenta, Pedido, Pago, IntentoWebpay
from .pagos import resolver_intento


class PagoPrevioTests(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=901, activa=True)
        categoria = Producto._meta.get_field('categoria').remote_field.model.objects.create(nombre='Pruebas', activa=True)
        self.producto = Producto.objects.create(categoria=categoria, nombre='Producto prueba', precio=3500, disponible=True)
        self.staff = get_user_model().objects.create_user(username='cocina_test', password='Pruebas123!', is_staff=True)
        self.operador = Client()
        self.operador.force_login(self.staff)
        self.carrito = f'carrito_{self.mesa.codigo}'
        self.llenar(self.client)
        self.patch = patch('pedidos.pagos.obtener_webpay')
        self.sdk = self.patch.start().return_value
        self.addCleanup(self.patch.stop)
        self.sdk.create.side_effect = lambda *args: {'token':str(IntentoWebpay.objects.count()).zfill(64), 'url':'https://webpay3gint.transbank.cl/webpayserver/initTransaction'}

    def llenar(self, client, cantidad=2):
        session = client.session
        session[self.carrito] = {str(self.producto.pk): cantidad}
        session.save()

    def iniciar(self, client=None, ruta='webpay_cliente'):
        return (client or self.client).post(reverse('pedidos:'+ruta, kwargs={'codigo':self.mesa.codigo}))

    def crear(self, client=None):
        r = self.iniciar(client)
        self.assertEqual(r.status_code, 200)
        return r.context['intento']

    def respuesta(self, intento, status='AUTHORIZED', code=0):
        return {'status':status, 'response_code':code, 'amount':int(intento.monto),
            'buy_order':intento.orden_compra, 'session_id':str(intento.session_id),
            'authorization_code':'123456', 'payment_type_code':'VD', 'card_detail':{'card_number':'6623'}}

    def aprobar(self, intento):
        self.sdk.status.return_value = self.respuesta(intento, 'INITIALIZED')
        self.sdk.commit.return_value = self.respuesta(intento)
        return self.client.post(reverse('pedidos:webpay_retorno'), {'token_ws':intento.token})

    def test_cliente_anonimo_crea_borrador_fuera_de_cocina(self):
        i = self.crear()
        self.assertEqual(i.pedido.estado, 'sin_pagar')
        self.assertIsNone(i.iniciado_por_id)
        self.assertEqual(i.monto, Decimal('7000'))
        self.assertEqual(self.client.session[self.carrito], {str(self.producto.pk):2})
        self.assertFalse(self.operador.get(reverse('pedidos:cocina')).context['pedidos'].exists())
        self.assertIn('firma=', self.client.post(reverse('pedidos:webpay_cliente', args=[self.mesa.codigo])).url)

    def test_pago_confirmado_envia_a_cocina_sin_cerrar_mesa(self):
        i = self.crear()
        r = self.aprobar(i)
        i.pedido.refresh_from_db(); i.cuenta.refresh_from_db()
        self.assertEqual(i.pedido.estado, 'pendiente')
        self.assertEqual(i.cuenta.estado, 'abierta')
        self.assertEqual(Pago.objects.get().pedido_id, i.pedido_id)
        self.assertIsNone(Pago.objects.get().registrado_por_id)
        recibo = self.client.get(r.url)
        self.assertContains(recibo, 'Pago autorizado')
        self.assertContains(recibo, 'enviado a cocina')
        self.assertEqual(self.client.session[self.carrito], {})
        self.assertEqual(list(self.operador.get(reverse('pedidos:cocina')).context['pedidos']), [i.pedido])
        self.assertContains(self.client.get(reverse('pedidos:mis_pedidos', args=[self.mesa.codigo])), 'Ver pago / comprobante')

    def test_doble_click_y_retorno_duplicado(self):
        i = self.crear()
        self.assertEqual(self.iniciar().status_code,302)
        self.sdk.create.assert_called_once()
        self.aprobar(i); self.aprobar(i)
        self.sdk.commit.assert_called_once()
        self.assertEqual(Pago.objects.count(),1)
        self.assertEqual(Pedido.objects.count(),1)
        self.assertEqual(self.iniciar().status_code,302)
        self.assertEqual(IntentoWebpay.objects.count(),1)

    def test_rechazo_conserva_carrito_y_permite_reintentar_mismo_pedido(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'FAILED',-1)
        resolver_intento(i.pk,confirmar=True)
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.client.session[self.carrito],{str(self.producto.pk):2})
        segundo=self.crear()
        self.assertEqual(segundo.pedido_id,i.pedido_id)
        self.assertNotEqual(segundo.pk,i.pk)
        self.assertFalse(self.operador.get(reverse('pedidos:cocina')).context['pedidos'].exists())

    def test_cancelacion_no_hace_commit_y_no_libera_estado_incierto(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'INITIALIZED')
        self.client.post(reverse('pedidos:webpay_retorno'),{'TBK_TOKEN':i.token})
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.iniciar().status_code,302)
        self.sdk.create.assert_called_once()
        self.assertEqual(self.client.session[self.carrito],{str(self.producto.pk):2})

    def test_timeout_se_recupera_sin_segundo_cobro(self):
        i=self.crear()
        self.sdk.status.side_effect=TimeoutError()
        self.client.post(reverse('pedidos:webpay_retorno'),{'token_ws':i.token})
        i.refresh_from_db(); self.assertEqual(i.estado,'por_verificar')
        self.assertEqual(self.iniciar().status_code,302)
        self.sdk.status.side_effect=None
        self.sdk.status.return_value=self.respuesta(i)
        resolver_intento(i.pk)
        self.sdk.commit.assert_not_called()
        self.assertEqual(Pago.objects.count(),1)

    def test_respuesta_incorrecta_no_libera_cocina(self):
        i=self.crear()
        for campo, valor in [('amount',1),('buy_order','ajena'),('session_id','ajena'),('response_code','0'),('response_code',-1),('authorization_code','')]:
            with self.subTest(campo=campo,valor=valor):
                respuesta=self.respuesta(i); respuesta[campo]=valor
                self.sdk.status.return_value=respuesta
                resolver_intento(i.pk,confirmar=True)
                self.assertFalse(Pago.objects.exists())
                i.pedido.refresh_from_db(); self.assertEqual(i.pedido.estado,'sin_pagar')

    def test_dos_clientes_misma_mesa_pagan_pedidos_separados(self):
        otro=Client();self.llenar(otro,1)
        primero=self.crear();segundo=self.crear(otro)
        self.assertEqual(primero.cuenta_id,segundo.cuenta_id)
        self.assertNotEqual(primero.pedido_id,segundo.pedido_id)
        self.aprobar(primero);self.aprobar(segundo)
        self.assertEqual(Pago.objects.count(),2)
        self.assertEqual(set(Pago.objects.values_list('monto',flat=True)),{Decimal('3500'),Decimal('7000')})
        visibles=self.client.get(reverse('pedidos:mis_pedidos',args=[self.mesa.codigo])).context['pedidos']
        self.assertEqual([p.pk for p in visibles],[primero.pedido_id])

    def test_mutaciones_bloqueadas_durante_pago(self):
        self.crear()
        for accion in ('agregar','quitar'):
            r=self.client.post(reverse('pedidos:'+accion,args=[self.mesa.codigo,self.producto.pk]))
            self.assertIn('resultado',r.url)
            self.assertEqual(self.client.session[self.carrito],{str(self.producto.pk):2})

    def test_enviar_antiguo_tampoco_omite_pago(self):
        self.assertEqual(self.iniciar(ruta='enviar').status_code,200)
        self.assertEqual(Pedido.objects.get().estado,'sin_pagar')
        self.assertFalse(Pago.objects.exists())

    def test_controles_staff_post_csrf_y_comprobante_privado(self):
        url=reverse('pedidos:webpay_cliente',args=[self.mesa.codigo])
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url).status_code,403)
        self.assertEqual(self.client.get(reverse('pedidos:cocina')).status_code,302)
        i=self.crear()
        self.assertEqual(Client().get(reverse('pedidos:webpay_resultado',args=[i.pk])).status_code,404)
        self.assertEqual(Client().post(reverse('pedidos:webpay_verificar',args=[i.pk])).status_code,404)
        r=self.aprobar(i)
        self.assertEqual(Client().get(r.url).status_code,200)

    def test_no_permite_transiciones_manuales_sin_pago(self):
        i=self.crear()
        Pedido.objects.filter(pk=i.pedido_id).update(estado='pendiente')
        self.operador.post(reverse('pedidos:cambiar_estado',args=[i.pedido_id]),{'estado':'en_preparacion'})
        i.pedido.refresh_from_db();self.assertEqual(i.pedido.estado,'pendiente')
        Pedido.objects.filter(pk=i.pedido_id).update(estado='listo')
        self.operador.post(reverse('pedidos:marcar_entregado',args=[i.pedido_id]))
        i.pedido.refresh_from_db();self.assertEqual(i.pedido.estado,'listo')
        self.assertFalse(self.operador.get(reverse('pedidos:entregas')).context['pedidos'].exists())

    def test_precio_servidor_disponibilidad_y_cantidad(self):
        Producto.objects.filter(pk=self.producto.pk).update(disponible=False)
        self.assertEqual(self.iniciar().status_code,302)
        self.assertFalse(IntentoWebpay.objects.exists())
        Producto.objects.filter(pk=self.producto.pk).update(disponible=True,precio=4200)
        for cantidad in (-1,0,21,'2',True):
            self.llenar(self.client,cantidad)
            self.assertEqual(self.iniciar().status_code,302)
            self.assertFalse(IntentoWebpay.objects.exists())
        self.llenar(self.client,2)
        i=self.crear();self.assertEqual(i.monto,Decimal('8400'))

    def test_fallo_creacion_no_envia_y_reintenta(self):
        self.sdk.create.side_effect=TimeoutError()
        self.assertEqual(self.iniciar().status_code,302)
        self.assertEqual(IntentoWebpay.objects.get().estado,'fallido')
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.client.session[self.carrito],{str(self.producto.pk):2})

    def test_pago_con_snapshot_alterado_requiere_revision(self):
        i=self.crear()
        i.pedido.detalles.update(cantidad=5)
        r=self.aprobar(i)
        self.assertEqual(Pago.objects.count(),1)
        i.pedido.refresh_from_db();self.assertEqual(i.pedido.estado,'sin_pagar')
        self.assertContains(self.client.get(r.url),'consulta al personal')
        self.assertEqual(self.iniciar().status_code,302)
        self.sdk.create.assert_called_once()

    def test_retorno_timeout_y_referencias_incorrectas(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'INITIALIZED')
        self.assertEqual(self.client.post(reverse('pedidos:webpay_retorno'),{'TBK_ORDEN_COMPRA':i.orden_compra,'TBK_ID_SESION':str(i.session_id)}).status_code,302)
        self.sdk.commit.assert_not_called()
        self.assertEqual(self.client.post(reverse('pedidos:webpay_retorno'),{'token_ws':i.token,'TBK_ORDEN_COMPRA':'otra'}).status_code,404)

    def test_despues_de_pagar_otro_pedido_independiente(self):
        i=self.crear();r=self.aprobar(i);self.client.get(r.url)
        self.client.post(reverse('pedidos:agregar',args=[self.mesa.codigo,self.producto.pk]))
        segundo=self.crear()
        self.assertNotEqual(i.pedido_id,segundo.pedido_id)
        self.assertEqual(segundo.monto,Decimal('3500'))
        self.assertEqual(segundo.cuenta_id,i.cuenta_id)

    def test_recorrido_preparacion_listo_entregado(self):
        i=self.crear();self.aprobar(i)
        for estado in ('en_preparacion','listo'):
            self.operador.post(reverse('pedidos:cambiar_estado',args=[i.pedido_id]),{'estado':estado})
            i.pedido.refresh_from_db();self.assertEqual(i.pedido.estado,estado)
        self.operador.post(reverse('pedidos:marcar_entregado',args=[i.pedido_id]))
        i.pedido.refresh_from_db();self.assertEqual(i.pedido.estado,'entregado')
        self.assertContains(self.operador.get(reverse('pedidos:caja')),'Ver comprobante')

    def test_enlace_salida_firmado_y_url_proveedor_validada(self):
        i=self.crear()
        from .vistas_webpay import _url_resultado
        self.assertEqual(Client().get(_url_resultado(i.pk)).status_code,200)
        self.sdk.status.return_value=self.respuesta(i,'FAILED',-1)
        resolver_intento(i.pk,True)
        self.sdk.create.side_effect=None
        self.sdk.create.return_value={'token':'z'*64,'url':'https://ejemplo.invalid/pago'}
        self.assertEqual(self.iniciar().status_code,302)
        self.assertEqual(IntentoWebpay.objects.first().estado,'fallido')

    def test_cliente_modifica_tras_rechazo_y_no_borra_carrito_de_otro(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'FAILED',-1)
        resolver_intento(i.pk,True)
        self.client.post(reverse('pedidos:quitar',args=[self.mesa.codigo,self.producto.pk]))
        segundo=self.crear()
        self.assertNotEqual(segundo.pedido_id,i.pedido_id)
        self.assertEqual(segundo.monto,Decimal('3500'))
        i.pedido.refresh_from_db(); self.assertEqual(i.pedido.estado,'cancelado')
        otro=Client();self.llenar(otro,4)
        from .vistas_webpay import _url_resultado
        self.aprobar(segundo)
        otro.get(_url_resultado(segundo.pk))
        self.assertEqual(otro.session[self.carrito],{str(self.producto.pk):4})


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature('has_select_for_update')
class ConcurrenciaPagoTests(TransactionTestCase):
    """Requieren PostgreSQL; SQLite no implementa bloqueos SELECT FOR UPDATE."""
    setUp = PagoPrevioTests.setUp
    llenar = PagoPrevioTests.llenar
    iniciar = PagoPrevioTests.iniciar
    crear = PagoPrevioTests.crear
    respuesta = PagoPrevioTests.respuesta

    def test_dos_posts_simultaneos_crean_un_solo_intento(self):
        barrier = Barrier(2)
        cookies = self.client.cookies.copy()
        def enviar(_):
            close_old_connections()
            try:
                cliente=Client();cliente.cookies=cookies.copy()
                barrier.wait(timeout=10)
                return self.iniciar(cliente).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados=list(pool.map(enviar,range(2)))
        self.assertEqual(sorted(resultados),[200,302])
        self.assertEqual(Pedido.objects.count(),1)
        self.assertEqual(IntentoWebpay.objects.count(),1)
        self.sdk.create.assert_called_once()

    def test_dos_retornos_simultaneos_registran_un_pago(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'INITIALIZED')
        self.sdk.commit.return_value=self.respuesta(i)
        barrier=Barrier(2)
        def confirmar(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return resolver_intento(i.pk,True).estado
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados=list(pool.map(confirmar,range(2)))
        self.assertEqual(resultados,['autorizado','autorizado'])
        self.assertEqual(Pago.objects.count(),1)
        self.sdk.commit.assert_called_once()
