from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from transbank.common.integration_type import IntegrationType
from .models import IntentoWebpay, Pago
from .pagos import resolver_intento
from . import test_webpay_demo as base
from .vistas_webpay import _url_resultado


class RecuperacionDemoTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta

    def viejo(self, minutos=21):
        i=self.crear()
        IntentoWebpay.objects.filter(pk=i.pk).update(creado=timezone.now()-timedelta(minutes=minutos))
        i.refresh_from_db()
        self.sdk.options.integration_type=IntegrationType.TEST
        self.sdk.status.return_value=self.respuesta(i,'INITIALIZED',None)
        self.sdk.status.return_value['authorization_code']=None
        return i

    def test_vencido_test_consulta_y_libera_reintento(self):
        i=self.viejo()
        resultado=resolver_intento(i.pk)
        self.assertEqual(resultado.estado,'fallido')
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        nuevo=self.crear()
        self.assertNotEqual(nuevo.pk,i.pk)
        self.assertNotEqual(nuevo.token,i.token)
        self.assertEqual(nuevo.pedido_id,i.pedido_id)

    def test_no_expira_solo_por_tiempo_si_falla_consulta(self):
        i=self.viejo()
        self.sdk.status.side_effect=TimeoutError()
        self.assertEqual(resolver_intento(i.pk).estado,'por_verificar')
        self.assertEqual(self.iniciar().status_code,302)
        self.sdk.create.assert_called_once()

    def test_no_expira_produccion(self):
        i=self.viejo()
        self.sdk.options.integration_type=IntegrationType.LIVE
        self.assertEqual(resolver_intento(i.pk).estado,'iniciado')
        self.assertEqual(self.iniciar().status_code,302)

    def test_autorizado_antiguo_sin_retorno_no_se_registra(self):
        i=self.viejo()
        self.sdk.status.return_value=self.respuesta(i)
        self.assertEqual(resolver_intento(i.pk).estado,'por_verificar')
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())

    def test_autorizado_sin_retorno_no_va_a_cocina(self):
        # Regla 3: sin commit propio, un AUTHORIZED de status() no basta.
        i=self.crear()
        self.sdk.status.return_value=self.respuesta(i)
        resultado=resolver_intento(i.pk)
        self.assertEqual(resultado.estado,'por_verificar')
        self.assertIn('personal',resultado.observacion)
        self.sdk.commit.assert_not_called()
        self.assertFalse(Pago.objects.exists())
        i.pedido.refresh_from_db()
        self.assertEqual(i.pedido.estado,'sin_pagar')

    def test_autorizado_con_retorno_previo_se_registra(self):
        # El commit ya ocurrió tras el retorno, pero Kippu no alcanzó a guardar el pago.
        i=self.crear()
        IntentoWebpay.objects.filter(pk=i.pk).update(retorno_confirmable=True)
        self.sdk.status.return_value=self.respuesta(i)
        self.assertEqual(resolver_intento(i.pk).estado,'autorizado')
        self.sdk.commit.assert_not_called()
        self.assertEqual(Pago.objects.count(),1)
        i.pedido.refresh_from_db()
        self.assertEqual(i.pedido.estado,'pendiente')

    def test_antes_del_plazo_no_libera_y_oculta_continuar(self):
        i=self.viejo(7)
        self.assertEqual(resolver_intento(i.pk).estado,'iniciado')
        pagina=self.client.get(_url_resultado(i.pk))
        self.assertNotContains(pagina,'Continuar este pago en Webpay')
        self.assertContains(pagina,'Verificar con Transbank')
        self.assertEqual(self.iniciar().status_code,302)

    def test_no_expira_con_retorno_confirmable(self):
        i=self.viejo()
        self.sdk.commit.return_value=self.sdk.status.return_value.copy()
        self.assertEqual(resolver_intento(i.pk,confirmar=True).estado,'por_verificar')
        self.assertFalse(Pago.objects.exists())

    def test_no_expira_respuesta_ajena(self):
        i=self.viejo()
        self.sdk.status.return_value['amount']=1
        self.assertEqual(resolver_intento(i.pk).estado,'por_verificar')

    def test_recuperado_permite_cerrar_borrador_sin_pago(self):
        from .cierre import cerrar_cuenta
        i=self.viejo()
        resolver_intento(i.pk)
        cuenta,nueva=cerrar_cuenta(i.cuenta_id)
        self.assertTrue(nueva)
        self.assertEqual(cuenta.estado,'cerrada')
        i.pedido.refresh_from_db()
        self.assertEqual(i.pedido.estado,'cancelado')
        self.assertFalse(Pago.objects.exists())
