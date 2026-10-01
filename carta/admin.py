from django.contrib import admin

from .models import Categoria, GrupoOpcion, OpcionProducto, Producto


class GrupoOpcionInline(admin.TabularInline):
    model = GrupoOpcion
    extra = 0
    fields = (
        "nombre", "requerido", "seleccion_multiple",
        "max_selecciones", "activo", "orden",
    )


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "local", "activa")
    list_filter = ("local", "activa")
    search_fields = ("nombre", "local__nombre")
    list_select_related = ("local",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "local", "categoria", "precio", "disponible",
        "requiere_mayoria_edad",
    )
    list_filter = (
        "categoria__local", "categoria", "disponible",
        "requiere_mayoria_edad",
    )
    search_fields = ("nombre", "descripcion", "categoria__local__nombre")
    list_select_related = ("categoria", "categoria__local")
    inlines = [GrupoOpcionInline]

    @admin.display(description="Local", ordering="categoria__local__nombre")
    def local(self, obj):
        return obj.categoria.local


class OpcionProductoInline(admin.TabularInline):
    model = OpcionProducto
    extra = 1
    fields = ("nombre", "precio_extra", "activa", "orden")


@admin.register(GrupoOpcion)
class GrupoOpcionAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "producto", "requerido", "seleccion_multiple",
        "max_selecciones", "activo", "orden",
    )
    list_filter = (
        "producto__categoria__local", "activo", "requerido",
        "seleccion_multiple",
    )
    search_fields = (
        "nombre", "producto__nombre", "producto__categoria__local__nombre",
    )
    list_select_related = (
        "producto", "producto__categoria", "producto__categoria__local",
    )
    inlines = [OpcionProductoInline]


@admin.register(OpcionProducto)
class OpcionProductoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "grupo", "producto", "precio_extra", "activa", "orden",
    )
    list_filter = ("grupo__producto__categoria__local", "activa")
    search_fields = (
        "nombre", "grupo__nombre", "grupo__producto__nombre",
    )
    list_select_related = (
        "grupo", "grupo__producto", "grupo__producto__categoria",
    )

    @admin.display(description="Producto", ordering="grupo__producto__nombre")
    def producto(self, obj):
        return obj.grupo.producto
