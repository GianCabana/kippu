"""El local del panel sale siempre del usuario autenticado, nunca de la URL (regla 5, D-14)."""
from functools import wraps

from django.shortcuts import render

from mesas.models import PerfilPersonal


def local_del_personal(usuario):
    if not usuario.is_authenticated:
        return None
    perfil = (PerfilPersonal.objects.select_related("local")
              .filter(usuario=usuario, local__activo=True).first())
    return perfil.local if perfil else None


def con_local(vista):
    """Va debajo de staff_member_required: deja el local en request.local_personal."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        local = local_del_personal(request.user)
        if local is None:
            return render(request, "pedidos/sin_local.html", status=403)
        request.local_personal = local
        return vista(request, *args, **kwargs)
    return envoltura
