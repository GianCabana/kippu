# Validación

- Django 5.2, modelos entregados, sesiones y cliente HTTP de pruebas.
- 20 pruebas funcionales pasaron con el SDK de Transbank simulado.
- 2 pruebas de concurrencia incluidas, omitidas en SQLite porque requieren
  SELECT FOR UPDATE. Ejecutarlas en PostgreSQL del proyecto.
- Probados: cliente anónimo, importe del servidor, disponibilidad y cantidades,
  pedido fuera de cocina antes de pagar, autorización, idempotencia, rechazo,
  cancelación, timeout/recuperación, respuesta incongruente, CSRF y permisos,
  comprobante firmado, antigua ruta de envío, dos navegadores en una mesa,
  bloqueo del carrito durante el pago, reintentos y recorrido hasta entrega.
- Migración ensayada desde los modelos enviados: conservó un pago histórico tras
  cambiar la relación cuenta/pago y añadir los campos nuevos.
- Se usó un proyecto temporal con modelos mínimos de Mesa/Producto/Categoria y un
  carrito compatible con el compartido. No se dispone de tu proyecto completo ni
  de tu base PostgreSQL.
- No se hizo una transacción en el sitio de integración de Transbank ni se probó
  una impresora física. Falta esa prueba desde tu equipo.
