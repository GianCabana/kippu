"""Pruebas de opciones, extras y recargos configurables por producto."""

from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from carta.models import GrupoOpcion, OpcionProducto, Producto

from . import test_webpay_demo as base
from .models import IntentoWebpay, Pedido
from .pagos import ErrorPago, reintentar_pago, resolver_intento


class OpcionesProductoTests(TestCase):
    setUp = base.PagoPrevioTests.setUp
    llenar = base.PagoPrevioTests.llenar
    iniciar = base.PagoPrevioTests.iniciar
    crear = base.PagoPrevioTests.crear
    respuesta = base.PagoPrevioTests.respuesta
    aprobar = base.PagoPrevioTests.aprobar

    def configurar_opciones(self):
        self.tamano = GrupoOpcion.objects.create(
            producto=self.producto,
            nombre="Tamaño",
            requerido=True,
            orden=1,
        )
        self.normal = OpcionProducto.objects.create(
            grupo=self.tamano,
            nombre="Normal",
            precio_extra=0,
            orden=1,
        )
        self.grande = OpcionProducto.objects.create(
            grupo=self.tamano,
            nombre="Grande",
            precio_extra=500,
            orden=2,
        )
        self.extras = GrupoOpcion.objects.create(
            producto=self.producto,
            nombre="Extras",
            seleccion_multiple=True,
            max_selecciones=2,
            orden=2,
        )
        self.queso = OpcionProducto.objects.create(
            grupo=self.extras,
            nombre="Queso",
            precio_extra=250,
            orden=1,
        )
        self.tocino = OpcionProducto.objects.create(
            grupo=self.extras,
            nombre="Tocino",
            precio_extra=600,
            orden=2,
        )
        self.salsa = OpcionProducto.objects.create(
            grupo=self.extras,
            nombre="Salsa",
            precio_extra=100,
            orden=3,
        )

    def seleccionar(self, *opciones, cantidad=1):
        session = self.client.session
        session[self.carrito] = {str(self.producto.pk): cantidad}
        session[f"opciones_carrito_{self.mesa.codigo}"] = {
            str(self.producto.pk): [str(opcion.pk) for opcion in opciones]
        }
        session.save()

    def test_carta_muestra_grupos_opciones_y_recargos(self):
        self.configurar_opciones()

        respuesta = self.client.get(
            reverse("carta:por_mesa", args=[self.mesa.codigo])
        )

        self.assertContains(respuesta, "Tamaño")
        self.assertContains(respuesta, "Extras")
        self.assertContains(respuesta, "Grande")
        self.assertContains(respuesta, "+ $500")
        self.assertContains(respuesta, "Elige hasta 2")

    def test_no_agrega_si_falta_opcion_obligatoria(self):
        self.configurar_opciones()
        session = self.client.session
        session[self.carrito] = {}
        session.save()

        respuesta = self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk])
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.client.session[self.carrito], {})
        mensajes = [str(mensaje) for mensaje in respuesta.wsgi_request._messages]
        self.assertTrue(any("Tamaño" in mensaje for mensaje in mensajes))

    def test_carrito_calcula_precio_con_extras(self):
        self.configurar_opciones()
        session = self.client.session
        session[self.carrito] = {}
        session.save()

        respuesta = self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]),
            {
                f"opcion_grupo_{self.tamano.pk}": str(self.grande.pk),
                f"opcion_grupo_{self.extras.pk}": [
                    str(self.queso.pk),
                    str(self.tocino.pk),
                ],
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        opciones = self.client.session[f"opciones_carrito_{self.mesa.codigo}"]
        self.assertEqual(
            set(opciones[str(self.producto.pk)]),
            {str(self.grande.pk), str(self.queso.pk), str(self.tocino.pk)},
        )
        carta = self.client.get(
            reverse("carta:por_mesa", args=[self.mesa.codigo])
        )
        item = carta.context["detalle_carrito"][0]
        self.assertEqual(item["precio_unitario"], Decimal("4850"))
        self.assertEqual(item["subtotal"], Decimal("4850"))
        self.assertContains(carta, "Tamaño:")
        self.assertContains(carta, "Grande")

    def test_servidor_rechaza_demasiados_extras(self):
        self.configurar_opciones()
        session = self.client.session
        session[self.carrito] = {}
        session.save()

        self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]),
            {
                f"opcion_grupo_{self.tamano.pk}": str(self.normal.pk),
                f"opcion_grupo_{self.extras.pk}": [
                    str(self.queso.pk),
                    str(self.tocino.pk),
                    str(self.salsa.pk),
                ],
            },
        )

        self.assertEqual(self.client.session[self.carrito], {})

    def test_servidor_rechaza_opcion_de_otro_producto(self):
        self.configurar_opciones()
        otro = Producto.objects.create(
            categoria=self.producto.categoria,
            nombre="Otro producto",
            precio=1000,
        )
        grupo_ajeno = GrupoOpcion.objects.create(
            producto=otro,
            nombre="Opción ajena",
        )
        opcion_ajena = OpcionProducto.objects.create(
            grupo=grupo_ajeno,
            nombre="No pertenece",
        )
        session = self.client.session
        session[self.carrito] = {}
        session.save()

        self.client.post(
            reverse("pedidos:agregar", args=[self.mesa.codigo, self.producto.pk]),
            {
                f"opcion_grupo_{self.tamano.pk}": str(self.normal.pk),
                "opcion": str(opcion_ajena.pk),
            },
        )

        self.assertEqual(self.client.session[self.carrito], {})

    def test_pago_guarda_snapshot_y_total_con_opciones(self):
        self.configurar_opciones()
        self.seleccionar(self.grande, self.queso, cantidad=2)

        intento = self.crear()
        detalle = intento.pedido.detalles.get()

        self.assertEqual(detalle.precio_unitario, Decimal("4250"))
        self.assertEqual(detalle.subtotal, Decimal("8500"))
        self.assertEqual(intento.subtotal, Decimal("8500"))
        self.assertEqual(intento.monto, Decimal("8500"))
        self.assertEqual(
            [opcion["nombre"] for opcion in detalle.opciones],
            ["Grande", "Queso"],
        )
        self.assertEqual(intento.detalle[0]["opciones"], detalle.opciones)

    def test_pago_autorizado_muestra_opciones_en_cocina(self):
        self.configurar_opciones()
        self.seleccionar(self.grande, self.queso)
        intento = self.crear()

        self.aprobar(intento)
        intento.pedido.refresh_from_db()

        self.assertEqual(intento.pedido.estado, Pedido.Estado.PENDIENTE)
        cocina = self.operador.get(reverse("pedidos:cocina"))
        self.assertContains(cocina, "Tamaño: Grande")
        self.assertContains(cocina, "Extras: Queso")

    def test_pago_rechaza_carrito_antiguo_sin_opcion_obligatoria(self):
        self.configurar_opciones()

        respuesta = self.iniciar()

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(IntentoWebpay.objects.exists())

    def test_reintento_se_bloquea_si_cambia_precio_del_extra(self):
        self.configurar_opciones()
        self.seleccionar(self.grande, self.queso)
        intento = self.crear()
        self.sdk.status.return_value = self.respuesta(intento, "FAILED", -1)
        resolver_intento(intento.pk, confirmar=True)
        self.grande.precio_extra = 900
        self.grande.save(update_fields=["precio_extra"])

        with self.assertRaises(ErrorPago):
            reintentar_pago(
                intento.pk,
                AnonymousUser(),
                "http://testserver/pedidos/webpay/retorno/",
            )
