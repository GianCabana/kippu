# Kippu · Webpay Plus y comprobante de demostración

Esta entrega se integra sobre los models.py, views.py y urls.py que compartiste.
El cobro se inicia desde Caja con un usuario de personal. Usa exclusivamente
Webpay Plus en integración y tarjetas de prueba. No emite boletas tributarias.

## 1. Copiar los archivos

Detén el servidor. Guarda una copia de tu proyecto o registra los cambios
pendientes en Git. Extrae el ZIP fuera del proyecto y copia su carpeta `pedidos`
dentro de `C:\Users\theca\Desktop\kippu`, combinando las carpetas y reemplazando
solo los archivos coincidentes. No borres tu carpeta pedidos ni sus migraciones.
Copia también `requirements-webpay-demo.txt` a la carpeta donde está manage.py.

Reemplazados:
- pedidos/models.py: limpieza de sangrías, método __str__ de Pago y vista de
  cocina mal ubicada; nuevos campos del intento y método de pago Webpay.
- pedidos/views.py: conserva tus vistas y bloquea pedidos nuevos durante el pago.
- pedidos/urls.py: conserva las rutas actuales y agrega las de Webpay.
- pedidos/webpay.py: SDK 6.1.0, ambiente de integración explícito, timeout 15 s.
- pedidos/templates/pedidos/caja.html: agrega el inicio de pago y consulta del intento.

Nuevos:
- pedidos/pagos.py: validaciones, transacciones e idempotencia.
- pedidos/vistas_webpay.py: inicio, retorno GET/POST, resultado y consulta posterior.
- pedidos/templates/pedidos/webpay_salida.html
- pedidos/templates/pedidos/webpay_resultado.html
- pedidos/test_webpay_demo.py

Las pantallas de carta, cocina, entregas y mis pedidos se conservan. No se
incluyen migraciones numeradas porque deben depender de tu historial real.

## 2. Instalar y migrar

En PowerShell, desde la carpeta kippu:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-webpay-demo.txt
.\.venv\Scripts\python.exe manage.py makemigrations pedidos
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test pedidos.test_webpay_demo
```

No borres migraciones anteriores ni la base de datos. Los nuevos campos tienen
valores iniciales vacíos. No se convertirán intentos antiguos en pagos aprobados.
Para la primera prueba crea una cuenta de prueba nueva. Si antes ya había un
intento activo incompleto, no lo borres ni lo marques como pagado manualmente.

Las pruebas usan la base temporal de Django y simulan las respuestas del SDK:
no llaman a Transbank ni hacen cobros. El usuario de base de datos debe poder
crear una base de prueba. La batería de concurrencia solo corre en un backend
con SELECT FOR UPDATE, como PostgreSQL.

## 3. Abrir Kippu

```powershell
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Para la primera prueba utiliza el mismo navegador del PC durante todo el flujo:
http://127.0.0.1:8000/pedidos/caja/

La URL de retorno se construye con el host desde el cual abres Caja. No requiere
cambiar settings.py para esa prueba local. Si usas un celular, abre Kippu con la
IP del PC accesible en su red y ya autorizada en ALLOWED_HOSTS, no 127.0.0.1.
Si el entorno de Transbank no acepta tu URL local o la demostración es remota,
usa una URL HTTPS accesible del proyecto. Puedes fijar en settings.py:

```python
WEBPAY_RETURN_URL = "https://TU-DOMINIO/pedidos/webpay/retorno/"
```

Sustituye TU-DOMINIO por el host real. Configura ese host y HTTPS de Django según
tu despliegue. No amplíes ALLOWED_HOSTS a '*'. No cambies SESSION_COOKIE_SAMESITE:
el resultado usa un enlace firmado y puede verse aunque el retorno de Webpay no
incluya la sesión del navegador.

## 4. Pago aprobado

1. Envía pedidos de prueba desde la carta de una mesa.
2. Llévalos por Cocina y Entregas hasta que estén Entregados.
3. Abre Caja y pulsa Actualizar cuentas.
4. Pulsa Pagar con Webpay. El monto se recalcula en el servidor; no viene del botón.
5. En la página de preparación pulsa Continuar a Webpay.
6. Utiliza la tarjeta VISA de integración publicada por Transbank:
   - Número: 4051 8856 0044 6623
   - CVV: 123
   - Vencimiento: una fecha futura válida
   - Si solicita autenticación: RUT 11.111.111-1, clave 123.
7. Completa el formulario de Transbank y espera el retorno a Kippu.
8. Debe aparecer Pago autorizado, con la cuenta cerrada y el comprobante.
9. Pulsa Imprimir / Guardar como PDF. El navegador abre el diálogo de impresión;
   el usuario elige impresora o Guardar como PDF. No hay impresión silenciosa.
10. Recarga el resultado: no debe crear otro Pago ni volver a confirmar el cobro.

Tarjetas de prueba y credenciales oficiales:
https://www.transbankdevelopers.cl/documentacion/como_empezar#ambiente-de-integracion
Flujo y verificación:
https://www.transbankdevelopers.cl/documentacion/webpay-plus

## 5. Otros resultados

- Rechazo: prueba Mastercard 5186 0595 5959 0568, CVV 123, vencimiento futuro.
  La cuenta permanece abierta y no aparece comprobante de pago aprobado.
- Anular en Webpay: se consulta el estado, no se llama a commit por el retorno de
  anulación. Si Transbank todavía informa INITIALIZED, se conserva el mismo
  intento y se puede continuar desde Caja. No se crea otro mientras siga activo.
- Cerrar la pestaña: vuelve a Caja, consulta el último intento y verifica su estado.
- Error de red al confirmar: queda Por verificar, se bloquea otro cobro y se ofrece
  Verificar con Transbank. La consulta puede recuperar una autorización previa.
- La opción Verificar solo confirma si previamente llegó un retorno normal con
  token_ws. Un retorno de anulación o timeout nunca habilita commit por sí solo.
- Nunca se libera un pago incierto solo porque pasó cierto tiempo. Si continúa
  sin resultado final, conserva el intento y revisa la incidencia.
- Un fallo al crear el formulario, antes de entregar su token al navegador, queda
  Fallido. Se puede volver a iniciar desde Caja; no se reintenta automáticamente.
- Durante el pago, enviar otro pedido a esa cuenta muestra un aviso y no lo guarda.
- Tras cerrar la cuenta, el siguiente pedido de esa mesa inicia otra cuenta.

## 6. Datos y límites

El comprobante conserva una copia de nombres, cantidades y precios al iniciar
el pago. Guarda orden, monto, autorización, código de respuesta, tipo de pago y
solo los últimos cuatro dígitos de la tarjeta devueltos por Transbank. No guarda
CVV ni número completo. El documento indica claramente que es una demostración.

Se exige AUTHORIZED, response_code 0 y coincidencia exacta de monto, orden y sesión.
Pago, autorización y cierre se guardan en una transacción de base de datos. Un pago
confirmado bloquea otro cobro. Si alguien modifica la cuenta por fuera del flujo
mientras se paga, se registra el dinero autorizado, pero se deja la cuenta abierta
con un aviso de revisión; no debe cobrarse nuevamente.

Las consultas de cierre serializan retornos de una mesa en PostgreSQL. SQLite no
ofrece el mismo bloqueo por fila; úsalo solo para pruebas locales secuenciales.
No edites pedidos ni cuentas desde el administrador durante un cobro de prueba.

El enlace público del comprobante está firmado y vence en una hora. Un usuario de
personal puede consultar el resultado desde su URL aun después del vencimiento.
No cambies a producción con este paquete: está fijado al ambiente de integración.

## 7. Git

Después de comprobarlo:

```powershell
git add pedidos/models.py pedidos/views.py pedidos/urls.py pedidos/webpay.py pedidos/pagos.py pedidos/vistas_webpay.py pedidos/templates/pedidos/caja.html pedidos/templates/pedidos/webpay_salida.html pedidos/templates/pedidos/webpay_resultado.html pedidos/test_webpay_demo.py pedidos/migrations/ requirements-webpay-demo.txt
git diff --cached --stat
git commit -m "feat: integrar Webpay de prueba y comprobante de pago"
```

Revisa antes del commit que los archivos preparados correspondan a este cambio.

## Validación de esta entrega

Se probó con Django 5.2 y transbank-sdk 6.1.0 en un proyecto temporal con modelos
mínimos equivalentes de Mesa y Producto. Las llamadas a Transbank se simularon.
Las pruebas se incluyen para repetirlas con tus modelos reales. Debes completar
el recorrido real en el ambiente de integración con las tarjetas de prueba.
