# Kippu: pagar antes de preparar

El cliente paga su propio carrito con Webpay Plus (integración). Se crea un pedido
«Pendiente de pago» que NO aparece en cocina. Al confirmar la autorización, el
servidor registra Pago y cambia el pedido a «Pendiente» en una única transacción.
Cocina comienza la preparación, marca listo y el personal registra la entrega.
La cuenta/mesa no se cierra al pagar. El cierre de la visita queda como siguiente
funcionalidad; esta actualización tampoco cierra automáticamente al entregar.

## Instalar en Windows

1. Detén el servidor con Ctrl+C. Conserva una copia del código y la base de datos.
2. Descomprime este paquete fuera del proyecto.
3. Copia las carpetas `pedidos` y `carta` del paquete dentro de
   `C:\Users\theca\Desktop\kippu`. Combina carpetas y reemplaza archivos coincidentes.
   NO borres las carpetas originales, `carrito.py`, `admin.py` ni las migraciones.
   Se conservan las plantillas de cocina y entregas que ya tienes.
4. Copia `requirements-webpay-demo.txt` junto a `manage.py`.
5. En PowerShell, dentro del proyecto, ejecuta uno a uno:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-webpay-demo.txt
.\.venv\Scripts\python.exe manage.py makemigrations pedidos
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test pedidos.test_webpay_demo
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Las migraciones se generan contra TU historial: no se incluye numeración inventada.
Las columnas nuevas para datos antiguos son opcionales. `Pago.cuenta` pasa de
uno-a-uno a muchos-a-uno: la relación inversa ahora es `cuenta.pagos`.
`Pago.pedido` es uno-a-uno y opcional para conservar pagos anteriores.
`registrado_por` permite NULL: el cliente no necesita cuenta de administrador.
Si tienes vistas/informes adicionales con `cuenta.pago`, adapta ese acceso a
`cuenta.pagos.all()` o a una suma de sus montos.

Las pruebas usan una base temporal, sin modificar tus pedidos reales. En PostgreSQL,
el usuario de pruebas necesita permiso para crear esa base. Si aparece un error de
permisos, comparte el mensaje. No cambies a SQLite para simular que las pruebas de
concurrencia pasaron.

## Probar el recorrido

1. Entra como cliente a una mesa desde su QR, en una ventana privada si quieres
   separarlo del navegador del personal. No uses la carta sin mesa.
2. Agrega productos y abre el carrito: aparece **Pagar con Webpay**.
3. Presiona el botón y después **Continuar a Webpay**. El servidor calcula el monto.
4. Antes de completar el pago, comprueba en Cocina que ese pedido NO aparece.
5. Completa el pago con una tarjeta de integración, nunca una tarjeta real.
   Tarjetas de prueba: https://www.transbankdevelopers.cl/documentacion/como_empezar
6. Al regresar aparece el comprobante con **Imprimir / Guardar como PDF**.
   En el mismo navegador, se limpia el carrito pagado.
7. Cocina ve el pedido **Pendiente**. Luego: Comenzar preparación → Marcar listo →
   Entregas → Marcar entregado.
8. **Mis pedidos** permite seguir el estado y volver al comprobante.
9. Prueba un rechazo: el pedido no llega a cocina y conserva el carrito.
10. Recarga el resultado: debe existir un solo Pago para ese pedido.

Es un comprobante de DEMOSTRACIÓN, no una boleta SII. Imprimir abre el diálogo del
navegador para elegir impresora o PDF; no imprime silenciosamente.

## Teléfono y retorno

En el celular, `127.0.0.1` apunta al celular, NO al PC. Entra con un QR que use la IP
local del PC, mantén ambos equipos en la misma red y deja el servidor abierto.
El retorno usa el host desde el que abriste la carta. Si ya configuraste
`WEBPAY_RETURN_URL` en settings.py, debe apuntar al servidor accesible desde ese
navegador y terminar en `/pedidos/webpay/retorno/`. Para una demostración fuera de
la red local necesitas una URL HTTPS pública correctamente configurada.
Este paquete no publica el proyecto en Internet.

## Reintentos, Caja e historial

- Caja consulta los últimos 100 pagos e intentos activos; ya no cobra cuentas.
- Cada cliente paga su pedido; compartir mesa no mezcla los carritos.
- La antigua ruta «enviar» también exige Webpay, sin permitir omitir el pago.
- Si se interrumpe, entra a Mis pedidos → Ver pago / comprobante.
- Si el resultado es incierto, se bloquean nuevos intentos y cambios del carrito.
  Usa Verificar con Transbank o Continuar este pago, sin iniciar otro cobro.
- Cancelar en Webpay no se trata como rechazo definitivo si la consulta todavía
  indica INITIALIZED: se mantiene el intento hasta confirmar el resultado.
- Rechazo/fallo definitivo permite reintentar conservando el carrito.
- Modificar el carrito después de un rechazo cancela el borrador sin pago anterior;
  el nuevo carrito genera un pedido distinto.
- Los datos antiguos se conservan, pero NO se marcan pagados por suposición.
  Cocina/Entregas solo muestran pedidos vinculados a un Pago. Los pedidos antiguos
  sin vínculo permanecen en el administrador; usa pedidos nuevos para esta prueba.
- Los retornos del flujo anterior aún se consultan. Una autorización se registra
  como pago de cuenta antigua para revisión, sin convertirla en pago de un pedido.
  Cuentas antiguas pagadas o con intentos inciertos bloquean nuevos cobros hasta
  revisarlas con el personal.
- Si el detalle local cambió respecto al autorizado, se registra el dinero y se
  requiere revisión. No se envía a cocina ni permite cobrar otra vez ese pedido.
- El comprobante público requiere un enlace firmado de una hora. Desde Mis pedidos
  puedes obtener otro; el personal lo consulta desde Caja.
- El SDK permanece exclusivamente en INTEGRACIÓN, sin credenciales de producción.

## Guardar en Git

Después de verificar el recorrido, revisa los cambios:

```powershell
git status --short
git diff --stat
```

Agrega los archivos del cambio y la migración recién generada:

```powershell
git add pedidos/models.py pedidos/views.py pedidos/urls.py pedidos/pagos.py pedidos/vistas_webpay.py pedidos/webpay.py pedidos/test_webpay_demo.py pedidos/templates/pedidos/caja.html pedidos/templates/pedidos/mis_pedidos.html pedidos/templates/pedidos/webpay_salida.html pedidos/templates/pedidos/webpay_resultado.html carta/templates/carta/lista.html requirements-webpay-demo.txt
git add pedidos/migrations/*.py
git diff --cached --stat
git commit -m "Pagar pedidos con Webpay antes de enviarlos a cocina"
```

No agregues `.venv`, `.env`, contraseñas ni volcados de datos.
El commit debe ejecutarse en TU repositorio: no se ha realizado desde aquí.
