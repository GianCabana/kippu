from carta.models import GrupoOpcion, OpcionProducto, Producto


class ErrorOpciones(ValueError):
    pass


class Carrito:
    MAXIMO_POR_PRODUCTO = 20

    def __init__(self, request, mesa):
        self.session = request.session
        self.mesa = mesa
        self.clave = f"carrito_{mesa.codigo}"
        self.clave_opciones = f"opciones_carrito_{mesa.codigo}"
        self.productos = self.session.get(self.clave, {})
        self.opciones = self.session.get(self.clave_opciones, {})
        self.ultimo_error = ""

    def guardar(self):
        self.session[self.clave] = self.productos
        if self.opciones:
            self.session[self.clave_opciones] = self.opciones
        else:
            self.session.pop(self.clave_opciones, None)
        self.session.modified = True

    def vaciar(self):
        self.productos = {}
        self.opciones = {}
        self.guardar()

    def snapshot(self):
        opciones = {
            producto_id: list(self.opciones.get(producto_id, []))
            for producto_id in self.productos
            if self.opciones.get(producto_id)
        }
        return {
            "productos": dict(self.productos),
            "opciones": opciones,
        }

    @staticmethod
    def validar_opciones(producto, opcion_ids, exigir_requeridas=True):
        ids = []
        for valor in opcion_ids or []:
            try:
                opcion_id = int(valor)
            except (TypeError, ValueError):
                raise ErrorOpciones("Una opción seleccionada no es válida.")
            if opcion_id not in ids:
                ids.append(opcion_id)

        opciones = list(
            OpcionProducto.objects.filter(
                pk__in=ids,
                activa=True,
                grupo__activo=True,
                grupo__producto=producto,
            )
            .select_related("grupo")
            .order_by("grupo__orden", "grupo_id", "orden", "pk")
        )
        if len(opciones) != len(ids):
            raise ErrorOpciones(
                "Una opción ya no está disponible. Vuelve a elegir el producto."
            )

        seleccionadas_por_grupo = {}
        for opcion in opciones:
            seleccionadas_por_grupo.setdefault(opcion.grupo_id, []).append(opcion)

        grupos = GrupoOpcion.objects.filter(
            producto=producto,
            activo=True,
        ).order_by("orden", "pk")
        for grupo in grupos:
            cantidad = len(seleccionadas_por_grupo.get(grupo.pk, []))
            if exigir_requeridas and grupo.requerido and cantidad == 0:
                raise ErrorOpciones(f"Debes elegir una opción en {grupo.nombre}.")
            if not grupo.seleccion_multiple and cantidad > 1:
                raise ErrorOpciones(
                    f"Solo puedes elegir una opción en {grupo.nombre}."
                )
            if cantidad > grupo.max_selecciones:
                raise ErrorOpciones(
                    f"Puedes elegir hasta {grupo.max_selecciones} "
                    f"opciones en {grupo.nombre}."
                )
        return opciones

    def opciones_producto(self, producto):
        return list(self.opciones.get(str(producto.pk), []))

    def agregar(self, producto, opcion_ids=None):
        producto_id = str(producto.pk)
        cantidad = self.productos.get(producto_id, 0)
        nuevas_opciones = sorted({str(valor) for valor in (opcion_ids or [])})
        opciones_actuales = sorted(self.opciones.get(producto_id, []))

        if cantidad and opciones_actuales != nuevas_opciones:
            self.ultimo_error = "opciones_distintas"
            return False
        if cantidad >= self.MAXIMO_POR_PRODUCTO:
            self.ultimo_error = "maximo"
            return False

        self.productos[producto_id] = cantidad + 1
        if nuevas_opciones:
            self.opciones[producto_id] = nuevas_opciones
        else:
            self.opciones.pop(producto_id, None)
        self.guardar()
        return True

    def quitar(self, producto):
        producto_id = str(producto.pk)
        cantidad = self.productos.get(producto_id, 0)

        if cantidad <= 1:
            self.productos.pop(producto_id, None)
            self.opciones.pop(producto_id, None)
        else:
            self.productos[producto_id] = cantidad - 1

        self.guardar()

    def cantidad_total(self):
        return sum(self.productos.values())

    def obtener_detalle(self):
        productos = Producto.objects.filter(
            pk__in=self.productos.keys(),
            categoria__local=self.mesa.local,
        ).select_related("categoria", "categoria__local")

        ids_validos = {str(producto.pk) for producto in productos}
        ids_invalidos = set(self.productos) - ids_validos
        cambiado = False
        if ids_invalidos:
            for producto_id in ids_invalidos:
                self.productos.pop(producto_id, None)
                self.opciones.pop(producto_id, None)
            cambiado = True

        detalle = []
        total = 0
        for producto in productos:
            producto_id = str(producto.pk)
            cantidad = self.productos.get(producto_id, 0)
            if cantidad < 1:
                continue
            try:
                opciones = self.validar_opciones(
                    producto,
                    self.opciones.get(producto_id, []),
                    exigir_requeridas=False,
                )
            except ErrorOpciones:
                self.productos.pop(producto_id, None)
                self.opciones.pop(producto_id, None)
                cambiado = True
                continue

            precio_unitario = producto.precio + sum(
                opcion.precio_extra for opcion in opciones
            )
            subtotal = precio_unitario * cantidad
            total += subtotal
            detalle.append({
                "producto": producto,
                "cantidad": cantidad,
                "opciones": opciones,
                "opcion_ids": [opcion.pk for opcion in opciones],
                "precio_unitario": precio_unitario,
                "subtotal": subtotal,
            })

        if cambiado:
            self.guardar()
        return detalle, total
