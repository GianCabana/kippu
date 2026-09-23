from django.urls import path
from . import views

app_name = "carta"

urlpatterns = [
    path("", views.lista_carta, name="lista"),
    path(
        "mesa/<uuid:codigo>/",
        views.lista_carta,
        name="por_mesa",
    ),
]