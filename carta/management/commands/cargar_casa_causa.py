"""Siembra de datos para recorrer Kippu (decisión 15).

Fuente: cuaderno de obra §5-ter (La Casa Causa). Supuestos acordados con Sebastián:
- Grupos sin nombre en el cuaderno se llaman "Tamaño".
- Vaso/Jarra no es obligatorio; Vaso cuesta $0.
- Agregados permite hasta 2 selecciones.
- "Local de prueba 2" no está en el cuaderno: existe solo para probar D-14 (Varios restaurantes).

Idempotente: usa get_or_create y no pisa cambios hechos en el admin. Las imágenes de semilla van en
carta/semillas/imagenes/<slug-del-local>/<slug-del-producto>.webp (también .jpg, .jpeg o .png) y se
copian al almacenamiento de media solo si el producto no tiene imagen. Las descripciones se cargan
solo si el producto no tiene una.

Uso: python manage.py cargar_casa_causa
"""
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from carta.models import Categoria, DiaDestacado, GrupoOpcion, OpcionProducto, Producto
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
        ("Arroz con mariscos", 14500, True, False, [AGREGADOS]),
        ("Chaufa de mariscos", 13500, True, False, [AGREGADOS]),
        ("Tallarín saltado criollo", 12500, True, False, [AGREGADOS]),
        ("Ají de gallina", 11500, True, False, FONDO),
        ("Cau cau", 11200, True, False, FONDO),
        ("Chaufa de pollo", 10900, True, False, [AGREGADOS]),
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

# 12 textos de Cowork (13 oct) y 23 de Gian (15 nov), que también corrigió el del lomo saltado.
DESCRIPCIONES = {
    "Causa limeña clásica": "Masa fría de papa amarilla sazonada con ají amarillo y limón, rellena de pollo con mayonesa y palta. Con huevo duro y aceituna de botija.",
    "Papa a la huancaína": "Rodajas de papa sancochada bañadas en crema de ají amarillo y queso fresco, sobre hojas de lechuga. Con huevo duro y aceitunas de botija.",
    "Anticuchos de corazón (2 palitos)": "Dos brochetas de corazón de res marinado en ají panca y asado a la parrilla. Con papa dorada, choclo y crema de rocoto.",
    "Yuquitas fritas con huancaína": "Bastones de yuca frita, crujientes por fuera y suaves por dentro, espolvoreados con perejil. Con crema huancaína de ají amarillo y queso fresco para untar.",
    "Tequeños de queso (6 u.)": "Seis rollitos de masa wantán rellenos de queso fresco derretido, fritos hasta quedar dorados y crujientes. Con guacamole para acompañar.",
    "Chicharrón de pollo": "Trozos de pollo marinados, apanados y fritos hasta quedar crujientes. Con salsa criolla de cebolla morada y tomate, crema de ají amarillo y limón.",
    "Ceviche clásico": "Pescado blanco marinado en limón, con cebolla morada, cilantro y ají limo. Con camote glaseado, choclo y cancha.",
    "Ceviche mixto": "Pescado blanco, camarones, calamar y choritos marinados en limón, con cebolla morada, cilantro y ají limo. Con camote glaseado, choclo y lechuga.",
    "Tiradito de corvina": "Láminas finas de corvina bañadas en crema de ají amarillo y limón, con cebolla morada, ají limo y cilantro. Con cancha tostada.",
    "Pulpo al olivo": "Láminas finas de pulpo bañadas en crema de aceituna de botija, con aceite de oliva, aceitunas y tostadas.",
    "Causa de camarones": "Capas de masa fría de papa amarilla con ají amarillo y limón, rellenas de camarones con mayonesa y palta. Coronada con camarones y salsa golf.",
    "Leche de tigre": "Jugo de ceviche de pescado blanco con limón, ají limo, cebolla morada y cilantro, servido en vaso y coronado con un camarón. Con choclo, cancha y limón.",
    "Choritos a la chalaca": "Choritos cocidos servidos en su concha, cubiertos con chalaca de cebolla morada, tomate, ají limo, cilantro y limón. Se sirven fríos, con un gajo de limón.",
    "Lomo saltado": "Tiras de lomo de res salteadas al wok a fuego alto con cebolla morada, tomate, ají amarillo, sillao y vinagre, terminadas con cilantro picado.",
    "Pescado a lo macho": "Filete de pescado frito bañado en salsa cremosa y picante de mariscos (camarones, calamar, choritos y pulpo) con ají panca y ají amarillo.",
    "Seco de cordero": "Cordero guisado lentamente en salsa de culantro, ají amarillo y chicha de jora, con trozos de papa amarilla. Con frejoles guisados y salsa criolla.",
    "Arroz con mariscos": "Arroz meloso al ají panca y ají amarillo con camarones, calamar, choritos y conchas, con arvejas y pimentón. Con salsa criolla.",
    "Chaufa de mariscos": "Arroz salteado al wok con camarones, calamar, choritos, trozos de pescado, huevo revuelto, pimentón y cebollín, sazonado con sillao y aceite de ajonjolí.",
    "Tallarín saltado criollo": "Tallarines salteados al wok a fuego alto con tiras de lomo de res, cebolla morada, tomate y cebollín, sazonados con sillao, vinagre y ají amarillo.",
    "Ají de gallina": "Pollo deshilachado en crema de ají amarillo, pan, leche y nueces, sobre papa amarilla. Con huevo duro y aceituna de botija.",
    "Cau cau": "Guiso de mondongo con papa en cubos y arvejas, en salsa de ají amarillo y palillo. Terminado con hojas de hierbabuena fresca.",
    "Chaufa de pollo": "Arroz salteado al wok con trozos de pollo, huevo revuelto, pimentón y cebollín, sazonado con sillao y aceite de ajonjolí.",
    "Suspiro limeño": "Manjar blanco cremoso cubierto con merengue al oporto y un toque de canela.",
    "Picarones (6 u.)": "Seis anillos fritos de masa de zapallo y camote, con miel de chancaca especiada con canela y naranja.",
    "Tres leches": "Bizcocho esponjoso empapado en una mezcla de leche evaporada, leche condensada y crema, cubierto con crema chantilly y canela. Con una frutilla.",
    "Mazamorra morada": "Postre espeso de maíz morado cocido con trozos de piña, pasas y canela, servido en pocillo y espolvoreado con canela molida.",
    "Arroz con leche": "Arroz cocido lentamente en leche con azúcar, canela y clavo de olor, hasta quedar cremoso. Servido en pocillo con canela en rama y canela molida.",
    "Pisco sour": "Pisco, jugo de limón, jarabe de goma y clara de huevo, batido y servido con gotas de amargo de angostura.",
    "Chilcano de pisco": "Pisco con ginger ale, jugo de limón, hielo y gotas de amargo de angostura, servido en vaso alto con una rodaja de limón.",
    "Maracuyá sour": "Pisco, jugo de maracuyá, jugo de limón, jarabe de goma y clara de huevo, batido y servido con semillas de maracuyá y hierbabuena.",
    "Cerveza artesanal": "Cerveza artesanal rubia en botella individual, servida helada junto a un vaso.",
    "Chicha morada": "Bebida de maíz morado hervido con piña, manzana, canela y clavo de olor, con un toque de limón. Sin alcohol.",
    "Limonada de hierbabuena": "Limonada de limón recién exprimido, licuada con hojas frescas de hierbabuena, endulzada y servida bien helada con hielo y una rodaja de limón. Sin alcohol.",
    "Inca Kola": "Gaseosa peruana de color amarillo y sabor dulce, servida helada.",
    "Agua mineral": "Agua mineral en botella individual, servida helada.",
}

# Inglés de la carta (fase 3). Se cargan solo en campos vacíos: no pisan lo que se edite en el admin.
CATEGORIAS_EN = {
    "Piqueos": "Small bites",
    "Entradas y ceviches": "Starters and ceviches",
    "Fondos": "Main courses",
    "Postres": "Desserts",
    "Barra": "Drinks",
}
GRUPOS_EN = {"Tamaño": "Size", "Acompañamiento": "Side", "Agregados": "Extras"}
OPCIONES_EN = {
    "Personal": "Single serving",
    "Para compartir": "To share",
    "Arroz blanco": "White rice",
    "Papas fritas": "French fries",
    "Ambos": "Both",
    "Huevo frito": "Fried egg",
    "Porción extra de arroz": "Extra rice",
    "Simple": "Single",
    "Doble": "Double",
    "Vaso": "Glass",
    "Jarra": "Pitcher",
}
PRODUCTOS_EN = {
    "Causa limeña clásica": ("Classic causa limeña", "Chilled yellow potato mash seasoned with ají amarillo and lime, filled with chicken, mayonnaise and avocado. With hard-boiled egg and botija olive."),
    "Papa a la huancaína": ("Potatoes à la huancaína", "Slices of boiled potato covered in a creamy sauce of ají amarillo and fresh cheese, on lettuce leaves. With hard-boiled egg and botija olives."),
    "Anticuchos de corazón (2 palitos)": ("Beef heart anticuchos (2 skewers)", "Two skewers of beef heart marinated in ají panca and grilled. With golden potato, Andean corn and rocoto sauce."),
    "Yuquitas fritas con huancaína": ("Fried yuca with huancaína", "Fried yuca sticks, crispy outside and soft inside, sprinkled with parsley. With huancaína sauce of ají amarillo and fresh cheese for dipping."),
    "Tequeños de queso (6 u.)": ("Cheese tequeños (6 pcs.)", "Six wonton rolls filled with melted fresh cheese, fried until golden and crispy. With guacamole on the side."),
    "Chicharrón de pollo": ("Crispy fried chicken", "Marinated chicken pieces, breaded and fried until crispy. With criolla salsa of red onion and tomato, ají amarillo sauce and lime."),
    "Ceviche clásico": ("Classic ceviche", "White fish cured in lime with red onion, cilantro and ají limo. With glazed sweet potato, Andean corn and cancha."),
    "Ceviche mixto": ("Mixed seafood ceviche", "White fish, shrimp, squid and mussels cured in lime with red onion, cilantro and ají limo. With glazed sweet potato, Andean corn and lettuce."),
    "Tiradito de corvina": ("Corvina tiradito", "Thin slices of corvina in a creamy ají amarillo and lime sauce, with red onion, ají limo and cilantro. With toasted cancha."),
    "Pulpo al olivo": ("Octopus in olive sauce", "Thin slices of octopus covered in a cream of botija olives, with olive oil, olives and toast."),
    "Causa de camarones": ("Shrimp causa", "Layers of chilled yellow potato mash with ají amarillo and lime, filled with shrimp, mayonnaise and avocado. Topped with shrimp and golf sauce."),
    "Leche de tigre": ("Leche de tigre", "White fish ceviche juice with lime, ají limo, red onion and cilantro, served in a glass and topped with a shrimp. With Andean corn, cancha and lime."),
    "Choritos a la chalaca": ("Mussels a la chalaca", "Cooked mussels served in their shells, topped with chalaca salsa of red onion, tomato, ají limo, cilantro and lime. Served cold with a lime wedge."),
    "Lomo saltado": ("Lomo saltado", "Strips of beef tenderloin stir-fried in a hot wok with red onion, tomato, ají amarillo, soy sauce and vinegar, finished with chopped cilantro."),
    "Pescado a lo macho": ("Fish a lo macho", "Fried fish fillet covered in a creamy, spicy seafood sauce (shrimp, squid, mussels and octopus) with ají panca and ají amarillo."),
    "Seco de cordero": ("Lamb seco", "Lamb slowly stewed in a sauce of cilantro, ají amarillo and chicha de jora, with pieces of yellow potato. With stewed beans and criolla salsa."),
    "Arroz con mariscos": ("Seafood rice", "Creamy rice with ají panca and ají amarillo, shrimp, squid, mussels and scallops, with peas and bell pepper. With criolla salsa."),
    "Chaufa de mariscos": ("Seafood chaufa", "Wok-fried rice with shrimp, squid, mussels, pieces of fish, scrambled egg, bell pepper and scallions, seasoned with soy sauce and sesame oil."),
    "Tallarín saltado criollo": ("Creole stir-fried noodles", "Noodles stir-fried in a hot wok with strips of beef tenderloin, red onion, tomato and scallions, seasoned with soy sauce, vinegar and ají amarillo."),
    "Ají de gallina": ("Ají de gallina", "Shredded chicken in a creamy sauce of ají amarillo, bread, milk and walnuts, over yellow potato. With hard-boiled egg and botija olive."),
    "Cau cau": ("Cau cau", "Tripe stew with diced potato and peas in a sauce of ají amarillo and turmeric. Finished with fresh mint leaves."),
    "Chaufa de pollo": ("Chicken chaufa", "Wok-fried rice with pieces of chicken, scrambled egg, bell pepper and scallions, seasoned with soy sauce and sesame oil."),
    "Suspiro limeño": ("Suspiro limeño", "Creamy dulce de leche topped with port meringue and a touch of cinnamon."),
    "Picarones (6 u.)": ("Picarones (6 pcs.)", "Six fried rings of squash and sweet potato dough, with chancaca syrup spiced with cinnamon and orange."),
    "Tres leches": ("Tres leches cake", "Fluffy sponge cake soaked in evaporated milk, condensed milk and cream, topped with whipped cream and cinnamon. With a strawberry."),
    "Mazamorra morada": ("Purple corn pudding", "Thick dessert of purple corn cooked with pieces of pineapple, raisins and cinnamon, served in a bowl and dusted with ground cinnamon."),
    "Arroz con leche": ("Rice pudding", "Rice slowly cooked in milk with sugar, cinnamon and cloves until creamy. Served in a bowl with a cinnamon stick and ground cinnamon."),
    "Pisco sour": ("Pisco sour", "Pisco, lime juice, simple syrup and egg white, shaken and served with drops of angostura bitters."),
    "Chilcano de pisco": ("Pisco chilcano", "Pisco with ginger ale, lime juice, ice and drops of angostura bitters, served in a tall glass with a slice of lime."),
    "Maracuyá sour": ("Passion fruit sour", "Pisco, passion fruit juice, lime juice, simple syrup and egg white, shaken and served with passion fruit seeds and mint."),
    "Cerveza artesanal": ("Craft beer", "Blonde craft beer in an individual bottle, served cold with a glass."),
    "Chicha morada": ("Chicha morada", "Drink of purple corn boiled with pineapple, apple, cinnamon and cloves, with a touch of lime. Non-alcoholic."),
    "Limonada de hierbabuena": ("Mint lemonade", "Freshly squeezed lime lemonade blended with fresh mint leaves, sweetened and served very cold with ice and a slice of lime. Non-alcoholic."),
    "Inca Kola": ("Inca Kola", "Yellow Peruvian soda with a sweet flavor, served cold."),
    "Agua mineral": ("Mineral water", "Mineral water in an individual bottle, served cold."),
}

# Destacado del día de La Casa Causa (fase 3): día de la semana (lunes = 0) → productos.
DESTACADOS_CASA_CAUSA = {
    0: ["Ají de gallina"],
    1: ["Seco de cordero"],
    2: ["Cau cau"],
    3: ["Lomo saltado"],
    4: ["Ceviche mixto", "Pescado a lo macho"],
    5: ["Arroz con mariscos", "Causa limeña clásica"],
    6: ["Ceviche clásico", "Picarones (6 u.)"],
}

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
            descripcion = DESCRIPCIONES.get(nombre_producto, "")
            if descripcion and not producto.descripcion:
                producto.descripcion = descripcion
                producto.save(update_fields=["descripcion"])
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


def _completar(objeto, valores):
    """Llena solo los campos vacíos: lo escrito en el admin se respeta."""
    vacios = [campo for campo, valor in valores.items() if valor and not getattr(objeto, campo)]
    for campo in vacios:
        setattr(objeto, campo, valores[campo])
    if vacios:
        objeto.save(update_fields=vacios)


def sembrar_ingles(local):
    for categoria in Categoria.objects.filter(local=local):
        _completar(categoria, {"nombre_en": CATEGORIAS_EN.get(categoria.nombre, "")})
    for producto in Producto.objects.filter(categoria__local=local):
        nombre_en, descripcion_en = PRODUCTOS_EN.get(producto.nombre, ("", ""))
        _completar(producto, {"nombre_en": nombre_en, "descripcion_en": descripcion_en})
    for grupo in GrupoOpcion.objects.filter(producto__categoria__local=local):
        _completar(grupo, {"nombre_en": GRUPOS_EN.get(grupo.nombre, "")})
    for opcion in OpcionProducto.objects.filter(grupo__producto__categoria__local=local):
        _completar(opcion, {"nombre_en": OPCIONES_EN.get(opcion.nombre, "")})


def sembrar_destacados(local, destacados):
    """Solo si el local no tiene ninguno: si el admin ya los cambió, no se pisan."""
    if DiaDestacado.objects.filter(producto__categoria__local=local).exists():
        return
    productos = {p.nombre: p for p in Producto.objects.filter(categoria__local=local)}
    for dia, nombres in destacados.items():
        for nombre in nombres:
            if nombre in productos:
                DiaDestacado.objects.get_or_create(producto=productos[nombre], dia=dia)


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
            sembrar_destacados(locales[0], DESTACADOS_CASA_CAUSA)
            sembrar_ingles(locales[0])
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
                f"{productos.exclude(imagen='').count()} con imagen, "
                f"{productos.exclude(descripcion='').count()} con descripción, "
                f"{DiaDestacado.objects.filter(producto__in=productos).count()} destacados del día, "
                f"{productos.exclude(nombre_en='').count()} con nombre en inglés"
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
