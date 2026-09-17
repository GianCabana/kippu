from django.contrib import admin

from .models import DetallePedido, Pedido


class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0

    fields = (
        "producto",
        "nombre_producto",
        "precio_unitario",
        "cantidad",
        "subtotal",
    )

    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "mesa",
        "estado",
        "creado",
        "total",
    )

    list_filter = ("estado", "mesa", "creado")
    search_fields = ("=id",)

    readonly_fields = (
        "mesa",
        "cuenta",
        "creado",
        "total",
     )

    inlines = [DetallePedidoInline]
    list_select_related = ("mesa","cuenta")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("detalles")

    @admin.display(description="Total CLP")
    def total(self, obj):
        monto = sum(detalle.subtotal for detalle in obj.detalles.all())
        return f"${monto:,.0f}".replace(",", ".")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False