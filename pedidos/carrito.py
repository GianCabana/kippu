from carta.models import Producto


class Carrito:
    MAXIMO_POR_PRODUCTO = 20

    def __init__(self, request, mesa):
        self.session = request.session
        self.clave = f"carrito_{mesa.codigo}"
        self.productos = self.session.get(self.clave, {})

    def guardar(self):
        self.session[self.clave] = self.productos
        self.session.modified = True

    def agregar(self, producto):
        producto_id = str(producto.pk)
        cantidad = self.productos.get(producto_id, 0)

        if cantidad >= self.MAXIMO_POR_PRODUCTO:
            return False

        self.productos[producto_id] = cantidad + 1
        self.guardar()
        return True

    def quitar(self, producto):
        producto_id = str(producto.pk)
        cantidad = self.productos.get(producto_id, 0)

        if cantidad <= 1:
            self.productos.pop(producto_id, None)
        else:
            self.productos[producto_id] = cantidad - 1

        self.guardar()

    def cantidad_total(self):
        return sum(self.productos.values())

    def obtener_detalle(self):
        productos = Producto.objects.filter(
            pk__in=self.productos.keys(),
        ).select_related("categoria")

        detalle = []
        total = 0

        for producto in productos:
            cantidad = self.productos.get(
                str(producto.pk),
                0,
            )

            if cantidad < 1:
                continue

            subtotal = producto.precio * cantidad
            total += subtotal

            detalle.append(
                {
                    "producto": producto,
                    "cantidad": cantidad,
                    "subtotal": subtotal,
                }
            )

        return detalle, total