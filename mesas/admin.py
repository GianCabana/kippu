import qrcode

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero", "activa", "boton_qr")
    list_filter = ("activa",)
    readonly_fields = ("codigo", "boton_qr")

    def get_urls(self):
        rutas_extra = [
            path(
                "<int:object_id>/qr/",
                self.admin_site.admin_view(self.descargar_qr),
                name="mesas_mesa_qr",
            ),
        ]
        return rutas_extra + super().get_urls()

    @admin.display(description="Código QR")
    def boton_qr(self, obj):
        if obj is None or obj.pk is None:
            return "Guarda la mesa para descargar su QR."

        enlace = reverse(
            "admin:mesas_mesa_qr",
            args=[obj.pk],
        )

        return format_html(
            '<a class="button" href="{}">Descargar QR</a>',
            enlace,
        )

    def descargar_qr(self, request, object_id):
        mesa = get_object_or_404(
            self.get_queryset(request),
            pk=object_id,
        )

        if not self.has_view_or_change_permission(request, mesa):
            raise PermissionDenied

        enlace = (
            settings.PUBLIC_BASE_URL
            + mesa.get_absolute_url()
        )

        imagen = qrcode.make(enlace)

        respuesta = HttpResponse(content_type="image/png")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="kippu-mesa-{mesa.numero}.png"'
        )

        imagen.save(respuesta, format="PNG")
        return respuesta