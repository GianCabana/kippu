from django.contrib import admin

from .models import Categoria, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "local", "activa")
    list_filter = ("local", "activa")
    search_fields = ("nombre", "local__nombre")
    list_select_related = ("local",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "local", "categoria", "precio", "disponible")
    list_filter = ("categoria__local", "categoria", "disponible")
    search_fields = ("nombre", "descripcion", "categoria__local__nombre")
    list_select_related = ("categoria", "categoria__local")

    @admin.display(description="Local", ordering="categoria__local__nombre")
    def local(self, obj):
        return obj.categoria.local
