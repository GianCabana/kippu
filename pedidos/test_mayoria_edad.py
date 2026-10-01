"""Pruebas del control +18 en carta, pago, cocina y entrega."""

from django.test import TestCase
from django.urls import reverse

from . import test_webpay_demo as base
from .models import IntentoWebpay, Pago, Pedido


class MayoriaEdadTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def iniciar(self, client=None, ruta="webpay_cliente", confirmacion="si"):
        datos = {"propina": "0"}
        if confirmacion is not None:
            datos["confirma_mayoria_edad"] = confirmacion
        return (client or self.client).post(
            reverse(
                f"pedidos:{ruta}",
                kwargs={"codigo": self.mesa.codigo},
            ),
            datos,
        )

    def convertir_producto_en_mayores_18(self):
        self.producto.requiere_mayoria_edad = True
        self.producto.save(update_fields=["requiere_mayoria_edad"])

    def test_carta_y_carrito_identifican_producto_restringido(self):
        self.convertir_producto_en_mayores_18()

        respuesta = self.client.get(
            reverse("carta:por_mesa", args=[self.mesa.codigo])
        )

        self.assertContains(respuesta, "+18")
        self.assertContains(respuesta, "Venta exclusiva para mayores de 18 años")
        self.assertContains(respuesta, "Confirmo que tengo 18 años o más")
        self.assertContains(respuesta, 'name="confirma_mayoria_edad"')

    def test_servidor_rechaza_pago_sin_confirmacion(self):
        self.convertir_producto_en_mayores_18()

        respuesta = self.iniciar(confirmacion=None)

        self.assertRedirects(
            respuesta,
            reverse("carta:por_mesa", args=[self.mesa.codigo]),
        )
        self.assertFalse(IntentoWebpay.objects.exists())
        self.assertFalse(Pedido.objects.exists())
        mensajes = [str(mensaje) for mensaje in respuesta.wsgi_request._messages]
        self.assertTrue(any("18 años o más" in mensaje for mensaje in mensajes))

    def test_servidor_rechaza_confirmacion_alterada(self):
        self.convertir_producto_en_mayores_18()

        respuesta = self.iniciar(confirmacion="no")

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(IntentoWebpay.objects.exists())
        self.assertFalse(Pedido.objects.exists())

    def test_confirmacion_y_restriccion_quedan_en_snapshot(self):
        self.convertir_producto_en_mayores_18()

        salida = self.iniciar()
        self.assertEqual(salida.status_code, 200)
        intento = salida.context["intento"]
        pedido = intento.pedido
        detalle = pedido.detalles.get()

        self.assertTrue(pedido.mayoria_edad_confirmada)
        self.assertTrue(detalle.requiere_mayoria_edad)
        self.assertTrue(intento.detalle[0]["requiere_mayoria_edad"])
        self.assertContains(salida, "productos +18")

    def test_pago_autorizado_llega_a_cocina_con_alerta(self):
        self.convertir_producto_en_mayores_18()
        intento = self.crear()

        self.aprobar(intento)
        intento.pedido.refresh_from_db()

        self.assertEqual(intento.pedido.estado, Pedido.Estado.PENDIENTE)
        self.assertTrue(Pago.objects.filter(pedido=intento.pedido).exists())
        cocina = self.operador.get(reverse("pedidos:cocina"))
        self.assertContains(cocina, "+18")
        self.assertContains(cocina, "Pedido con verificación de edad")

    def test_entrega_solicita_identificacion(self):
        self.convertir_producto_en_mayores_18()
        intento = self.crear()
        self.aprobar(intento)
        Pedido.objects.filter(pk=intento.pedido_id).update(
            estado=Pedido.Estado.LISTO
        )

        entrega = self.operador.get(reverse("pedidos:entregas"))

        self.assertContains(entrega, "+18")
        self.assertContains(entrega, "Solicitar identificación antes de entregar")

    def test_producto_normal_no_exige_confirmacion(self):
        respuesta = self.iniciar(confirmacion=None)

        self.assertEqual(respuesta.status_code, 200)
        pedido = respuesta.context["intento"].pedido
        self.assertFalse(pedido.mayoria_edad_confirmada)
        self.assertFalse(pedido.detalles.get().requiere_mayoria_edad)
