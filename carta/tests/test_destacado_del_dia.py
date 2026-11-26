"""Fase 3: "Destacado de hoy" arriba de la carta, según el día de la semana en Chile."""
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from carta.models import Categoria, DiaDestacado, Producto
from mesas.models import Local, Mesa

LUNES = date(2026, 11, 16)
MARTES = date(2026, 11, 17)


class DestacadoDelDiaTests(TestCase):
    def setUp(self):
        self.local = Local.objects.create(nombre="Local destacado", slug="local-destacado")
        self.mesa = Mesa.objects.create(local=self.local, numero=1, activa=True)
        categoria = Categoria.objects.create(local=self.local, nombre="Fondos")
        self.aji = Producto.objects.create(categoria=categoria, nombre="Ají de gallina", precio=11500)
        self.seco = Producto.objects.create(categoria=categoria, nombre="Seco de cordero", precio=14900)
        DiaDestacado.objects.create(producto=self.aji, dia=DiaDestacado.Dia.LUNES)
        DiaDestacado.objects.create(producto=self.seco, dia=DiaDestacado.Dia.MARTES)

    def carta(self, dia):
        with patch("carta.views.timezone.localdate", return_value=dia):
            return self.client.get(reverse("carta:por_mesa", args=[self.mesa.codigo]))

    def test_muestra_el_destacado_del_dia(self):
        respuesta = self.carta(LUNES)

        self.assertEqual(respuesta.context["destacados_hoy"], [self.aji])
        self.assertEqual(respuesta.context["dia_hoy"], "Lunes")
        self.assertContains(respuesta, "Destacado de hoy")
        self.assertContains(respuesta, 'aria-label="Ver Ají de gallina, destacado de hoy"')

    def test_cambia_segun_el_dia(self):
        self.assertEqual(self.carta(MARTES).context["destacados_hoy"], [self.seco])

    def test_reutiliza_la_ficha_del_producto(self):
        html = self.carta(LUNES).content.decode()

        self.assertIn(f'data-abrir-detalle="detalle-{self.aji.pk}"', html)
        self.assertEqual(html.count(f'id="detalle-{self.aji.pk}"'), 1)

    def test_sin_destacados_no_muestra_la_seccion(self):
        DiaDestacado.objects.all().delete()

        respuesta = self.carta(LUNES)

        self.assertNotContains(respuesta, "Destacado de hoy")

    def test_no_destaca_productos_no_disponibles(self):
        Producto.objects.filter(pk=self.aji.pk).update(disponible=False)

        self.assertEqual(self.carta(LUNES).context["destacados_hoy"], [])

    def test_no_muestra_destacados_de_otro_local(self):
        otro = Local.objects.create(nombre="Otro", slug="otro")
        categoria = Categoria.objects.create(local=otro, nombre="Fondos")
        ajeno = Producto.objects.create(categoria=categoria, nombre="Ajeno", precio=1000)
        DiaDestacado.objects.create(producto=ajeno, dia=DiaDestacado.Dia.LUNES)

        self.assertEqual(self.carta(LUNES).context["destacados_hoy"], [self.aji])

    def test_un_producto_no_se_repite_el_mismo_dia(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DiaDestacado.objects.create(producto=self.aji, dia=DiaDestacado.Dia.LUNES)


class SemillaDestacadosTests(TestCase):
    def cargar(self):
        call_command("cargar_casa_causa", stdout=StringIO())

    def test_carga_un_destacado_para_cada_dia(self):
        self.cargar()

        dias = set(DiaDestacado.objects.filter(producto__categoria__local__slug="la-casa-causa").values_list("dia", flat=True))
        self.assertEqual(dias, set(range(7)))

    def test_no_pisa_los_cambios_del_admin(self):
        self.cargar()
        DiaDestacado.objects.filter(dia=DiaDestacado.Dia.LUNES).delete()

        self.cargar()

        self.assertFalse(DiaDestacado.objects.filter(dia=DiaDestacado.Dia.LUNES).exists())
