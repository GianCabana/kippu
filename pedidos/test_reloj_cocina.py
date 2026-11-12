"""Fila 21: el reloj de cocina y de entregas cuenta desde el pago, no desde que se creó el pedido."""
from datetime import timedelta

from django.urls import reverse
from django.utils import dateformat, timezone

from .models import Pago, Pedido
from .test_pago_presencial import PagoPresencialBase


def iso(fecha):
    return dateformat.format(timezone.localtime(fecha), "c")


class RelojDesdeElPagoTests(PagoPresencialBase):
    def pagado_en_caja(self, minutos_esperando):
        self.llenar(self.client)
        pedido = self.pedido()
        self.envejecer(pedido, minutos_esperando)
        self.cobrar(pedido)
        pedido.refresh_from_db()
        return pedido

    def test_cocina_cuenta_desde_el_pago(self):
        pedido = self.pagado_en_caja(minutos_esperando=20)

        html = self.operador.get(reverse("pedidos:cocina")).content.decode()

        self.assertIn(f'data-pagado="{iso(pedido.pago.creado)}"', html)
        self.assertNotIn(iso(pedido.creado), html)

    def test_entregas_cuenta_desde_el_pago(self):
        pedido = self.pagado_en_caja(minutos_esperando=20)
        Pedido.objects.filter(pk=pedido.pk).update(estado=Pedido.Estado.LISTO)

        html = self.operador.get(reverse("pedidos:entregas")).content.decode()

        self.assertIn(f'data-pagado="{iso(pedido.pago.creado)}"', html)
        self.assertNotIn(iso(pedido.creado), html)

    def test_cocina_ordena_por_hora_de_pago(self):
        creado_primero = self.pagado_en_caja(minutos_esperando=20)
        creado_despues = self.pagado_en_caja(minutos_esperando=5)
        Pago.objects.filter(pk=creado_despues.pago.pk).update(creado=timezone.now() - timedelta(minutes=10))

        pedidos = list(self.operador.get(reverse("pedidos:cocina")).context["pedidos"])

        self.assertEqual(pedidos, [creado_despues, creado_primero])
