from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from . import test_webpay_demo as base
from .models import IntentoWebpay, Pago
from .pagos import resolver_intento
from .vistas_webpay import _url_resultado, _firma
from .cierre import cerrar_cuenta


class ReintentoTokenTests(TestCase):
    setUp=base.PagoPrevioTests.setUp
    llenar=base.PagoPrevioTests.llenar
    iniciar=base.PagoPrevioTests.iniciar
    crear=base.PagoPrevioTests.crear
    respuesta=base.PagoPrevioTests.respuesta

    def iniciado(self):
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i,'INITIALIZED',None)
        self.sdk.status.return_value['authorization_code']=None
        return i

    def accion(self,i,nombre,cliente=None):
        return (cliente or self.client).post(reverse('pedidos:'+nombre,args=[i.pk]),{'firma':_firma(i.pk)})

    def abortar(self,i):
        return self.client.post(reverse('pedidos:webpay_retorno'),{'TBK_TOKEN':i.token,
            'TBK_ID_SESION':str(i.session_id),'TBK_ORDEN_COMPRA':i.orden_compra})

    def test_cancelar_webpay_y_reintentar_inmediatamente(self):
        i=self.iniciado();r=self.abortar(i)
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')
        self.assertTrue(i.cancelacion_solicitada)
        self.assertContains(self.client.get(r.url),'Reintentar pago con un token nuevo')
        r=self.accion(i,'webpay_reintentar')
        self.assertEqual(r.status_code,200)
        nuevo=r.context['intento']
        self.assertNotEqual(i.token,nuevo.token)
        self.assertNotEqual(i.orden_compra,nuevo.orden_compra)
        self.assertEqual(i.pedido_id,nuevo.pedido_id)
        self.assertEqual(nuevo.reintento_de_id,i.pk)
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.client.session[self.carrito],{str(self.producto.pk):2})

    def test_reintentar_abandono_sin_retorno_no_reutiliza_token(self):
        i=self.iniciado()
        r=self.accion(i,'webpay_reintentar')
        self.assertEqual(r.status_code,200)
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')
        self.assertNotEqual(r.context['intento'].token,i.token)

    def test_doble_click_reintento_crea_un_solo_sucesor(self):
        i=self.iniciado()
        primero=self.accion(i,'webpay_reintentar').context['intento']
        segundo=self.accion(i,'webpay_reintentar').context['intento']
        self.assertEqual(primero.pk,segundo.pk)
        self.assertEqual(IntentoWebpay.objects.count(),2)
        self.assertEqual(self.sdk.create.call_count,2)

    def test_token_se_abre_solo_una_vez(self):
        i=self.iniciado()
        salida=self.accion(i,'webpay_abrir')
        self.assertContains(salida,'name="token_ws"')
        self.assertNotContains(salida,'name="csrfmiddlewaretoken"')
        self.assertEqual(self.accion(i,'webpay_abrir').status_code,302)
        i.refresh_from_db();self.assertTrue(i.formulario_abierto)
        self.assertNotContains(self.client.get(_url_resultado(i.pk)),'Continuar este pago en Webpay')

    def test_cancelar_antes_de_abrir_y_cerrar_mesa(self):
        i=self.iniciado()
        self.accion(i,'webpay_cancelar')
        cuenta,cerrada=cerrar_cuenta(i.cuenta_id)
        self.assertTrue(cerrada)
        self.assertEqual(cuenta.estado,'cerrada')
        self.assertEqual(self.accion(i,'webpay_abrir').status_code,302)

    def test_timeout_y_retorno_mixto_cancelan_sin_commit(self):
        i=self.iniciado()
        self.client.post(reverse('pedidos:webpay_retorno'),{
            'TBK_ID_SESION':str(i.session_id),'TBK_ORDEN_COMPRA':i.orden_compra})
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')
        self.sdk.commit.assert_not_called()

    def test_red_incierta_no_crea_otro_y_luego_recupera_cancelacion(self):
        i=self.iniciado();self.sdk.status.side_effect=TimeoutError()
        self.assertEqual(self.accion(i,'webpay_reintentar').status_code,302)
        i.refresh_from_db();self.assertEqual(i.estado,'por_verificar')
        self.assertTrue(i.cancelacion_solicitada)
        self.assertEqual(IntentoWebpay.objects.count(),1)
        self.sdk.status.side_effect=None
        self.accion(i,'webpay_verificar')
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')
        self.assertEqual(self.accion(i,'webpay_reintentar').status_code,200)

    def test_si_ya_autorizado_registra_y_no_reintenta(self):
        i=self.iniciado();self.sdk.status.return_value=self.respuesta(i)
        self.assertEqual(self.accion(i,'webpay_reintentar').status_code,302)
        self.assertEqual(Pago.objects.count(),1)
        self.assertEqual(IntentoWebpay.objects.count(),1)
        self.sdk.commit.assert_not_called()

    def test_retorno_viejo_no_confirma_token_abandonado(self):
        i=self.iniciado();nuevo=self.accion(i,'webpay_reintentar').context['intento']
        self.client.post(reverse('pedidos:webpay_retorno'),{'token_ws':i.token})
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        nuevo.refresh_from_db();self.assertEqual(nuevo.estado,'iniciado')

    def test_incongruencia_y_datos_de_autorizacion_bloquean_reintento(self):
        i=self.iniciado()
        self.sdk.status.return_value['amount']=1
        self.assertEqual(self.accion(i,'webpay_reintentar').status_code,302)
        self.assertEqual(IntentoWebpay.objects.count(),1)

    def test_sin_sesion_original_reintenta_con_enlace_firmado(self):
        i=self.iniciado();self.abortar(i)
        r=self.accion(i,'webpay_reintentar',Client())
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['intento'].pedido_id,i.pedido_id)

    def test_rutas_exigen_post_firma_y_csrf(self):
        i=self.iniciado()
        for nombre in ('webpay_reintentar','webpay_cancelar','webpay_abrir'):
            url=reverse('pedidos:'+nombre,args=[i.pk])
            self.assertEqual(self.client.get(url).status_code,405)
            self.assertEqual(Client().post(url).status_code,404)
            self.assertEqual(Client(enforce_csrf_checks=True).post(url,{'firma':_firma(i.pk)}).status_code,403)
        self.assertEqual(IntentoWebpay.objects.count(),1)

    def test_precio_cambiado_no_hace_otro_cobro(self):
        i=self.iniciado()
        self.producto.precio=9000;self.producto.save()
        r=self.accion(i,'webpay_reintentar')
        self.assertEqual(r.status_code,302)
        self.assertEqual(IntentoWebpay.objects.count(),1)
        self.assertContains(self.client.get(r.url),'Cambió la disponibilidad o el precio')
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')

    def test_retorno_mixto_no_se_confirma(self):
        i=self.iniciado()
        self.client.post(reverse('pedidos:webpay_retorno'),{'token_ws':i.token,'TBK_TOKEN':i.token,
            'TBK_ID_SESION':str(i.session_id),'TBK_ORDEN_COMPRA':i.orden_compra})
        i.refresh_from_db();self.assertEqual(i.estado,'anulado')
        self.sdk.commit.assert_not_called()

    def test_confirmacion_incierta_no_se_descarta_al_reintentar(self):
        i=self.iniciado();self.sdk.status.side_effect=TimeoutError()
        resolver_intento(i.pk,confirmar=True)
        self.sdk.status.side_effect=None
        self.sdk.commit.return_value=self.sdk.status.return_value.copy()
        self.accion(i,'webpay_reintentar')
        i.refresh_from_db();self.assertEqual(i.estado,'por_verificar')
        self.assertTrue(i.retorno_confirmable)
        self.assertFalse(i.cancelacion_solicitada)
        self.assertEqual(IntentoWebpay.objects.count(),1)

    def test_referencias_incorrectas_no_cancelan(self):
        i=self.iniciado()
        r=self.client.post(reverse('pedidos:webpay_retorno'),{'TBK_TOKEN':i.token,
            'TBK_ID_SESION':str(i.session_id),'TBK_ORDEN_COMPRA':'otra'})
        self.assertEqual(r.status_code,404)
        i.refresh_from_db();self.assertFalse(i.cancelacion_solicitada)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature


@skipUnlessDBFeature('has_select_for_update')
class ReintentoConcurrenteTests(TransactionTestCase):
    setUp=base.PagoPrevioTests.setUp
    llenar=base.PagoPrevioTests.llenar
    iniciar=base.PagoPrevioTests.iniciar
    crear=base.PagoPrevioTests.crear
    respuesta=base.PagoPrevioTests.respuesta
    iniciado=ReintentoTokenTests.iniciado

    def test_dos_reintentos_crean_un_sucesor(self):
        from .pagos import reintentar_pago
        from django.contrib.auth.models import AnonymousUser
        i=self.iniciado();barrier=Barrier(2)
        def enviar(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return reintentar_pago(i.pk,AnonymousUser(),'http://testserver/pedidos/webpay/retorno/')[0].pk
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(enviar,range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(IntentoWebpay.objects.count(),2)

    def test_cancelar_y_confirmar_se_serializan(self):
        i=self.iniciado();barrier=Barrier(2)
        self.sdk.commit.return_value=self.respuesta(i)
        def procesar(cancelar):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return resolver_intento(i.pk,confirmar=not cancelar,cancelar=cancelar).estado
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(procesar,[True,False]))
        i.refresh_from_db()
        self.assertIn(i.estado,['anulado','autorizado'])
        self.assertEqual(Pago.objects.count(),int(i.estado=='autorizado'))
        self.assertLessEqual(self.sdk.commit.call_count,1)
