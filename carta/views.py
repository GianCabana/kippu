from django.shortcuts import render
from .models import Producto


def lista_carta(request):
    productos = (
        Producto.objects.filter(
            disponible=True,
            categoria__activa=True,
        )
        .select_related("categoria")
        .order_by("categoria__nombre", "categoria_id", "nombre")
    )

    return render(
        request,
        "carta/lista.html",
        {"productos": productos},
    )