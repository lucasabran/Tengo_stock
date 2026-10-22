# Bot de WhatsApp con IA — Tengo Stock

**Vende por WhatsApp las 24 h con la información de la tienda online (Tiendanube).**
Busca productos en tiempo real (precio, stock, opciones, precio de cada plan de garantía
extendida, cupones y promos) y manda el link para comprar. Cuando algo lo supera (pedidos
ya hechos, reclamos, devoluciones, "quiero hablar con alguien"), te avisa y deja de
responderle a ese cliente para que lo atiendas vos.

Es independiente del sistema de gestión: está en el mismo repositorio de GitHub pero
corre como **otro servicio de Render** y no lee ni modifica nada del sistema de gestión.

## Qué hace y qué no

| Hace | No hace |
|---|---|
| Busca productos y da precio, stock y link | No cobra ni toma pedidos (la compra es en la web) |
| Recomienda 2–3 opciones según presupuesto | No consulta el estado de pedidos (deriva a una persona) |
| Informa el adicional de cada plan de garantía | No inventa cuotas, envíos ni promos: usa `info_tienda.md` |
| Informa cupones y promos vigentes | No lee audios ni fotos (pide que escriban) |

## Paso 1 — Datos de la tienda
Completá en `info_tienda.md` cada **[COMPLETAR]** (cuotas, envíos, retiro, garantía, horario).
Lo que quede sin completar, el bot lo deriva a una persona.

## Paso 2 — Probarlo en la PC (sin WhatsApp)
1. Creá una API key en https://console.anthropic.com → **API Keys** (cargá saldo; USD 20 alcanzan para empezar).
2. Copiá `.env.example` como `.env` (en esta carpeta) y pegá la key en `ANTHROPIC_API_KEY`.
   Los datos de Tiendanube los toma solos de `tiendanube/.env`.
3. Desde la carpeta `stock-app`:
   ```
   pip install -r whatsapp_bot/requirements.txt
   python -m whatsapp_bot.probar
   ```

## Paso 3 — Número de WhatsApp (Meta)
1. https://developers.facebook.com → **Mis apps → Crear app → Otro → Empresa** → elegí el portfolio de Tengo Stock.
2. Agregá el producto **WhatsApp** (Meta da un número de prueba gratis para empezar).
3. **WhatsApp → Configuración de la API**: copiá el **Identificador del número de teléfono** → `WHATSAPP_PHONE_NUMBER_ID`.
4. Token permanente: **business.facebook.com → Configuración → Usuarios del sistema → Agregar** (Admin)
   → **Generar token** con `whatsapp_business_messaging` y `whatsapp_business_management` → `WHATSAPP_TOKEN`.
5. **Configuración de la app → Básica → Clave secreta de la app** → `META_APP_SECRET`.
6. Número real: **WhatsApp → Configuración de la API → Agregar número**. Si es el número que ya usás
   en la app WhatsApp Business, elegí **conectar la app WhatsApp Business** (coexistencia): seguís
   contestando desde el celular y el bot atiende por la API. Si no aparece, usá un número nuevo.

> Con el número de prueba y celulares argentinos, Meta a veces rechaza el envío por el "9":
> poné `AR_QUITAR_9=1` mientras pruebes y volvé a `0` con el número real.

## Paso 4 — Render (servicio nuevo, separado del sistema de gestión)
1. Render → **New → Web Service** → elegí el repositorio **Tengo_stock** (el mismo de GitHub).
2. Configuración:
   - Name: `tengostock-whatsapp`
   - Branch: `main` · Root Directory: *(vacío)*
   - Build Command: `pip install -r whatsapp_bot/requirements.txt`
   - Start Command: `gunicorn whatsapp_bot.servidor:app --workers 1 --threads 8 --timeout 120`
   - Plan: **Starter** (el gratis se duerme y los mensajes llegan tarde). No necesita disco.
3. **Environment**: cargá las variables de `.env.example` con sus valores
   (`TIENDANUBE_TOKEN` es el `ACCESS_TOKEN` de `tiendanube/.env`).
4. Al terminar, `https://tengostock-whatsapp.onrender.com/whatsapp/estado` tiene que mostrar
   `"ok": true` y la cantidad de productos.

## Paso 5 — Conectar el webhook en Meta
**WhatsApp → Configuración → Webhook → Editar**
- URL: `https://tengostock-whatsapp.onrender.com/whatsapp/webhook`
- Token de verificación: el mismo de `WHATSAPP_VERIFY_TOKEN`
- En **Campos del webhook**, suscribite a **messages**.

Mandá "hola" al número del bot y listo.

## Cómo atender cuando el bot deriva
- Con `OWNER_PHONE` cargado te llega un WhatsApp con el cliente, el motivo y un link al chat.
  WhatsApp solo deja mandarte ese aviso si **le escribiste al bot en las últimas 24 h**
  (mandale un "hola" cada mañana). También queda en los logs de Render.
- El bot no le responde a ese cliente durante 12 h (`PAUSA_HORAS`).
- Comandos desde tu número: `#bot 5491122334455` (vuelve a atenderlo), `#pausa 5491122334455`, `#pausados`.

## Mantenimiento
- Promos o cupones nuevos: editá `info_tienda.md` y subí el cambio a GitHub (Render se actualiza solo).
- Precios y stock: nada, el bot relee la tienda cada 30 minutos.
- Las conversaciones se guardan en memoria: si el servicio se reinicia, empieza de cero.

## Costos aproximados
- Claude: centavos de dólar por conversación (console.anthropic.com → Usage; podés poner tope mensual).
- WhatsApp: responder a clientes que te escriben es gratis; los mensajes que inicia la tienda se cobran.
- Render: USD 7/mes por este servicio.

## Archivos
- `servidor.py`: arranque del servicio · `webhook.py`: recibe y envía mensajes de WhatsApp
- `asistente.py`: instrucciones del bot y herramientas (buscar, ver producto, derivar)
- `catalogo.py`: lee y busca productos en Tiendanube · `info_tienda.md`: datos de la tienda
- `probar.py`: chat de prueba en la consola
