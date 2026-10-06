from decimal import Decimal
import re

from django.test import TestCase
from django.urls import reverse

from . import test_webpay_demo as base
from .models import IntentoWebpay, Pago
from .pagos import resolver_intento
from carta.models import Categoria, Producto
from mesas.models import Mesa


class PropinaTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def iniciar(self, propina):
        return self.client.post(
            reverse('pedidos:webpay_cliente', args=[self.mesa.codigo]),
            {'propina': propina},
        )

    def test_propina_sugerida_diez_por_ciento(self):
        respuesta = self.iniciar('10')
        self.assertEqual(respuesta.status_code, 200)
        intento = respuesta.context['intento']
        self.assertEqual(intento.subtotal, Decimal('7000'))
        self.assertEqual(intento.propina, Decimal('700'))
        self.assertEqual(intento.monto, Decimal('7700'))
        self.assertEqual(intento.pedido.propina, Decimal('700'))
        self.assertContains(respuesta, 'Propina opcional')
        self.assertContains(respuesta, '7700')

    def test_propina_redondea_hacia_arriba_a_peso_entero(self):
        self.producto.precio = 3333
        self.producto.save(update_fields=['precio'])
        self.llenar(self.client, 1)
        intento = self.iniciar('10').context['intento']
        self.assertEqual(intento.subtotal, Decimal('3333'))
        self.assertEqual(intento.propina, Decimal('334'))
        self.assertEqual(intento.monto, Decimal('3667'))

    def test_cliente_puede_continuar_sin_propina(self):
        intento = self.iniciar('0').context['intento']
        self.assertEqual(intento.propina, Decimal('0'))
        self.assertEqual(intento.monto, intento.subtotal)

    def test_opcion_alterada_no_crea_intento(self):
        respuesta = self.iniciar('25')
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(IntentoWebpay.objects.exists())

    def test_pago_y_comprobante_conservan_desglose(self):
        intento = self.iniciar('10').context['intento']
        retorno = self.aprobar(intento)
        pago = Pago.objects.get()
        self.assertEqual(pago.monto, Decimal('7700'))
        intento.pedido.refresh_from_db()
        self.assertEqual(intento.pedido.propina, Decimal('700'))
        comprobante = self.client.get(retorno.url)
        self.assertContains(comprobante, 'Subtotal')
        self.assertContains(comprobante, 'Propina opcional')
        self.assertContains(comprobante, '7700')

    def test_reintento_conserva_la_propina_original(self):
        intento = self.iniciar('10').context['intento']
        self.sdk.status.return_value = self.respuesta(intento, 'FAILED', -1)
        resolver_intento(intento.pk, confirmar=True)
        nuevo = self.iniciar('10').context['intento']
        self.assertEqual(nuevo.pedido_id, intento.pedido_id)
        self.assertEqual(nuevo.subtotal, intento.subtotal)
        self.assertEqual(nuevo.propina, intento.propina)
        self.assertEqual(nuevo.monto, intento.monto)


class PropinaCarritoTests(TestCase):
    def setUp(self):
        self.mesa = Mesa.objects.create(numero=993)
        categoria = Categoria.objects.create(nombre='Propina carrito')
        self.producto = Producto.objects.create(nombre='Plato', categoria=categoria, precio=3333)
        self.agregar = reverse('pedidos:agregar', kwargs={'codigo': self.mesa.codigo, 'producto_id': self.producto.pk})
        self.carta = reverse('carta:por_mesa', kwargs={'codigo': self.mesa.codigo})

    def opciones_propina(self, html):
        return re.findall(r'<input[^>]*name="propina"[^>]*>', html)

    def revisar(self, respuesta):
        html = respuesta.content.decode()
        opciones = self.opciones_propina(html)
        self.assertEqual(len(opciones), 2)
        for opcion in opciones:
            self.assertNotIn('checked', opcion)
            self.assertIn('required', opcion)
        self.assertContains(respuesta, '$334')
        self.assertContains(respuesta, '$3.667')

    def test_fragmento_muestra_propina_y_total_sin_preseleccion(self):
        self.revisar(self.client.post(self.agregar, HTTP_HX_REQUEST='true'))

    def test_carta_muestra_propina_y_total_sin_preseleccion(self):
        self.client.post(self.agregar, HTTP_HX_REQUEST='true')
        self.revisar(self.client.get(self.carta))
