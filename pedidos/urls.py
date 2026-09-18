from django.urls import path

from . import views, vistas_webpay

app_name = "pedidos"

urlpatterns = [
    path("caja/cuenta/<int:cuenta_id>/cerrar/", views.cerrar_mesa, name="cerrar_mesa"),
    path("mesa/<uuid:codigo>/pagar/", vistas_webpay.iniciar_cliente, name="webpay_cliente"),
    path(
        "mesa/<uuid:codigo>/agregar/<int:producto_id>/",
        views.agregar_al_carrito,
        name="agregar",
    ),
    path(
        "mesa/<uuid:codigo>/quitar/<int:producto_id>/",
        views.quitar_del_carrito,
        name="quitar",
    ),
    path(
        "mesa/<uuid:codigo>/enviar/",
        views.enviar_pedido,
        name="enviar",
    ),

    path("cocina/", views.cocina, name="cocina"),
         path(
        "cocina/pedido/<int:pedido_id>/estado/",
        views.cambiar_estado,
        name="cambiar_estado",
    ),
        path(
        "entregas/",
        views.entregas,
        name="entregas",
    ),
    path(
        "entregas/pedido/<int:pedido_id>/entregar/",
        views.marcar_entregado,
        name="marcar_entregado",
    ),
        path(
        "mesa/<uuid:codigo>/mis-pedidos/",
        views.mis_pedidos,
        name="mis_pedidos",
    ),
        path(
        "caja/",
        views.caja,
        name="caja",
    ),
    path("caja/cuenta/<int:cuenta_id>/pagar/", vistas_webpay.iniciar, name="webpay_iniciar"),
    path("webpay/retorno/", vistas_webpay.retorno, name="webpay_retorno"),
    path("webpay/resultado/<int:intento_id>/", vistas_webpay.resultado, name="webpay_resultado"),
    path("webpay/verificar/<int:intento_id>/", vistas_webpay.verificar, name="webpay_verificar"),
]
