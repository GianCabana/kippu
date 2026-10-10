"""Siembra de datos para recorrer Kippu (decisión 15).

Fuente: cuaderno de obra §5-ter (La Casa Causa). Supuestos acordados con Sebastián:
- Grupos sin nombre en el cuaderno se llaman "Tamaño".
- Vaso/Jarra no es obligatorio; Vaso cuesta $0.
- Agregados permite hasta 2 selecciones.
- "Local de prueba 2" no está en el cuaderno: existe solo para probar D-14 (Varios restaurantes).

Idempotente: usa get_or_create y no pisa cambios hechos en el admin. Las imágenes de semilla van en
carta/semillas/imagenes/<slug-del-local>/<slug-del-producto>.webp (también .jpg, .jpeg o .png) y se
copian al almacenamiento de media solo si el producto no tiene imagen.

Uso: python manage.py cargar_casa_causa
"""
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from carta.models import Categoria, GrupoOpcion, OpcionProducto, Producto
from mesas.models import Local, Mesa

DIRECTORIO_SEMILLAS = Path(__file__).resolve().parents[2] / "semillas" / "imagenes"
EXTENSIONES = (".webp", ".jpg", ".jpeg", ".png")

TAMANO_CEVICHE = ("Tamaño", True, False, 1, [("Personal", 0), ("Para compartir", 5000)])
ACOMPANAMIENTO = ("Acompañamiento", True, False, 1, [("Arroz blanco", 0), ("Papas fritas", 0), ("Ambos", 1200)])
AGREGADOS = ("Agregados", False, True, 2, [("Huevo frito", 1500), ("Porción extra de arroz", 1800)])
TAMANO_PISCO = ("Tamaño", True, False, 1, [("Simple", 0), ("Doble", 3000)])
VASO_JARRA = ("Tamaño", False, False, 1, [("Vaso", 0), ("Jarra", 4500)])
FONDO = [ACOMPANAMIENTO, AGREGADOS]

# (categoría, [(producto, precio, disponible, requiere_mayoria_edad, grupos)])
CARTA_CASA_CAUSA = [
    ("Piqueos", [
        ("Causa limeña clásica", 6500, True, False, []),
        ("Papa a la huancaína", 5900, True, False, []),
        ("Anticuchos de corazón (2 palitos)", 7900, True, False, []),
        ("Yuquitas fritas con huancaína", 5500, True, False, []),
        ("Tequeños de queso (6 u.)", 6200, True, False, []),
        ("Chicharrón de pollo", 7500, True, False, []),
    ]),
    ("Entradas y ceviches", [
        ("Ceviche clásico", 10900, True, False, [TAMANO_CEVICHE]),
        ("Ceviche mixto", 12500, True, False, [TAMANO_CEVICHE]),
        ("Tiradito de corvina", 11500, True, False, []),
        ("Pulpo al olivo", 12900, False, False, []),
        ("Causa de camarones", 8900, True, False, []),
        ("Leche de tigre", 6900, True, False, []),
        ("Choritos a la chalaca", 7200, True, False, []),
    ]),
    ("Fondos", [
        ("Lomo saltado", 13900, True, False, FONDO),
        ("Pescado a lo macho", 15900, True, False, FONDO),
        ("Seco de cordero", 14900, True, False, FONDO),
        ("Arroz con mariscos", 14500, True, False, FONDO),
        ("Chaufa de mariscos", 13500, True, False, FONDO),
        ("Tallarín saltado criollo", 12500, True, False, FONDO),
        ("Ají de gallina", 11500, True, False, FONDO),
        ("Cau cau", 11200, True, False, FONDO),
        ("Chaufa de pollo", 10900, True, False, FONDO),
    ]),
    ("Postres", [
        ("Suspiro limeño", 5500, True, False, []),
        ("Picarones (6 u.)", 5900, True, False, []),
        ("Tres leches", 5500, True, False, []),
        ("Mazamorra morada", 4900, True, False, []),
        ("Arroz con leche", 4500, True, False, []),
    ]),
    ("Barra", [
        ("Pisco sour", 6500, True, True, [TAMANO_PISCO]),
        ("Chilcano de pisco", 6900, True, True, []),
        ("Maracuyá sour", 6900, True, True, []),
        ("Cerveza artesanal", 4900, True, True, []),
        ("Chicha morada", 3200, True, False, [VASO_JARRA]),
        ("Limonada de hierbabuena", 3500, True, False, [VASO_JARRA]),
        ("Inca Kola", 2800, True, False, []),
        ("Agua mineral", 2200, True, False, []),
    ]),
]

CARTA_PRUEBA_2 = [
    ("Prueba", [
        ("Producto de prueba 1", 1000, True, False, []),
        ("Producto de prueba 2", 1000, True, False, []),
    ]),
]

LOCALES = [
    ("La Casa Causa", "la-casa-causa", 16, CARTA_CASA_CAUSA),
    ("Local de prueba 2", "local-de-prueba-2", 2, CARTA_PRUEBA_2),
]


def sembrar_local(nombre, slug, cantidad_mesas, carta):
    local, _ = Local.objects.get_or_create(slug=slug, defaults={"nombre": nombre, "activo": True})
    for numero in range(1, cantidad_mesas + 1):
        Mesa.objects.get_or_create(local=local, numero=numero, defaults={"activa": True})
    for nombre_categoria, productos in carta:
        categoria, _ = Categoria.objects.get_or_create(local=local, nombre=nombre_categoria)
        for nombre_producto, precio, disponible, mayoria_edad, grupos in productos:
            producto, _ = Producto.objects.get_or_create(
                categoria=categoria,
                nombre=nombre_producto,
                defaults={
                    "precio": Decimal(precio),
                    "disponible": disponible,
                    "requiere_mayoria_edad": mayoria_edad,
                },
            )
            for orden_grupo, (nombre_grupo, requerido, multiple, maximo, opciones) in enumerate(grupos):
                grupo, _ = GrupoOpcion.objects.get_or_create(
                    producto=producto,
                    nombre=nombre_grupo,
                    defaults={
                        "requerido": requerido,
                        "seleccion_multiple": multiple,
                        "max_selecciones": maximo,
                        "orden": orden_grupo,
                    },
                )
                for orden_opcion, (nombre_opcion, extra) in enumerate(opciones):
                    OpcionProducto.objects.get_or_create(
                        grupo=grupo,
                        nombre=nombre_opcion,
                        defaults={"precio_extra": Decimal(extra), "orden": orden_opcion},
                    )
    return local


def buscar_semilla(slug_local, slug_producto):
    for extension in EXTENSIONES:
        ruta = DIRECTORIO_SEMILLAS / slug_local / f"{slug_producto}{extension}"
        if ruta.is_file():
            return ruta
    return None


def asignar_imagen(producto, slug_local):
    """Copia la semilla solo si el producto no tiene una imagen que exista: nunca pisa la del local."""
    if producto.imagen and producto.imagen.storage.exists(producto.imagen.name):
        return
    semilla = buscar_semilla(slug_local, slugify(producto.nombre))
    if semilla is None:
        return
    with semilla.open("rb") as archivo:
        producto.imagen.save(semilla.name, File(archivo), save=True)


class Command(BaseCommand):
    help = "Carga La Casa Causa y Local de prueba 2 (idempotente), con imágenes de semilla si existen."

    def handle(self, *args, **opciones):
        with transaction.atomic():
            locales = [sembrar_local(*datos) for datos in LOCALES]
        # Fuera de la transacción: un archivo copiado no se deshace con un rollback.
        for local in locales:
            for producto in Producto.objects.filter(categoria__local=local).select_related("categoria__local"):
                asignar_imagen(producto, local.slug)

        for local in locales:
            productos = Producto.objects.filter(categoria__local=local)
            self.stdout.write(
                f"{local.nombre}: {local.mesas.count()} mesas, {local.categorias.count()} categorías, "
                f"{productos.count()} productos, "
                f"{GrupoOpcion.objects.filter(producto__in=productos).count()} grupos, "
                f"{OpcionProducto.objects.filter(grupo__producto__in=productos).count()} opciones, "
                f"{productos.filter(disponible=False).count()} no disponibles, "
                f"{productos.filter(requiere_mayoria_edad=True).count()} +18, "
                f"{productos.exclude(imagen='').count()} con imagen"
            )
        self.stdout.write(self.estado_local_principal())
        self.stdout.write(f"Locales en total: {Local.objects.count()}")

    def estado_local_principal(self):
        # Decisión 12: la migración mesas/0002 lo crea siempre; sin datos no sirve y se oculta.
        principal = Local.objects.filter(slug="kippu-principal").first()
        if principal is None:
            return "Kippu Principal: no existe."
        if principal.mesas.exists() or principal.categorias.exists():
            return "Kippu Principal tiene mesas o categorías: no se desactiva. Revísalo en el admin."
        if principal.activo:
            Local.objects.filter(pk=principal.pk).update(activo=False)
        return "Kippu Principal: inactivo (vacío)."
