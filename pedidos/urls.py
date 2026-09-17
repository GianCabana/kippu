from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
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
]