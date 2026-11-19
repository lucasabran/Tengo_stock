# Subir el stock a internet (Render, con disco persistente)

La app ya está lista para esto (tiene `Procfile`, `gunicorn`, login con
clave). Estos pasos los tenés que hacer vos porque requieren tus propias
cuentas — yo te voy guiando si te trabás en alguno.

## 1. Cuenta de GitHub (gratis)

Render despliega leyendo el código desde un repositorio de GitHub.

1. Andá a github.com y creá una cuenta si no tenés.
2. Creá un repositorio nuevo, por ejemplo `stock-tengostock`. Puede ser
   privado.
3. Avisame cuando lo tengas creado y te paso los comandos exactos para subir
   el código de esta carpeta ahí (`git remote add`, `git push`).

## 2. Cuenta de Render (gratis crearla)

1. Andá a render.com y creá una cuenta (podés entrar con la cuenta de
   GitHub del paso 1, es lo más rápido).
2. "New" → "Web Service" → conectá el repositorio que creaste.
3. Configuración del servicio:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** el que tenga **Persistent Disk** (disco persistente) — es el
     que evita que se borre el stock. Es el que vamos a pagar (unos
     USD 5-7/mes).
4. Agregá un **Disk**:
   - Mount path: `/var/data`
   - Size: `1 GB` alcanza de sobra (el stock ocupa muy poco).
5. En "Environment", agregá las variables:
   - `STOCK_USER` = el usuario que quieras
   - `STOCK_PASSWORD` = una clave segura (no dejes la de prueba `admin1234`)
   - `STOCK_DB_PATH` = `/var/data/stock.db` (asi la base se guarda en el
     disco persistente, no en el codigo)
6. Deploy. Render te va a dar una URL fija tipo
   `https://tu-stock.onrender.com` — esa es la que compartís con tus
   empleados.

## 3. Avisame cuando llegues a cada paso

Si te trabás con algo (la pantalla no se parece a lo que describo, un botón
no aparece, etc.), mandame captura y seguimos desde ahí.

## 4. Automatizaciones (variables opcionales en Render > Environment)

Todo lo de abajo funciona solo si cargás las variables. Sin ellas el sistema anda igual que antes.
**Nunca pegues estas claves en el codigo ni en GitHub (el repo es publico): solo en Render.**

| Para qué | Variables |
|---|---|
| Ventas de Tienda Nube entrando solas | `TN_STORE_ID` (id de la tienda) y `TN_ACCESS_TOKEN` (token de la app 44717). Opcional: `TN_CONTACT` (mail de contacto para la API). Despues se activa desde la pestaña **Tienda Nube**. |
| Resumen diario por mail (8:00 hs Argentina) | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`; opcional `SMTP_PORT` (587 por defecto, 465 usa SSL) y `SMTP_FROM`. Los destinatarios se cargan en **Usuarios > Herramientas**. |

Siempre activas (no necesitan variables):
- **Copia de seguridad diaria** en `/var/data/backups/diario-AAAAMMDD.db` (se conservan las ultimas 14). Se descargan desde Usuarios > Herramientas.
- **Verificacion en dos pasos** opcional: cada usuario la activa en **Mi cuenta**. Si alguien pierde el celular, el dueño le resetea la clave desde Usuarios y se le quita tambien la verificacion. Si el que la pierde es el dueño: `STOCK_FORCE_OWNER_RESET=1` + `STOCK_PASSWORD` (ver arriba) y se le quita tambien.

### Tienda Nube: como funciona y que cuidar
- Solo entran pedidos **pagados despues de la fecha de activacion** (por defecto, desde el momento en que se activa), para no descontar dos veces lo que ya se cargo a mano.
- Se busca el producto por **SKU**. Las variantes de garantia (`ABC-G2`) se asignan al producto base (`ABC`). Si un SKU no coincide, el pedido queda en "Para revisar" y se asocia a mano una sola vez desde la pestaña.
- Si no hay stock suficiente en la oficina elegida, el pedido tambien queda para revisar (no se deja el stock en negativo).
- Un pedido ya cargado que se cancela en Tienda Nube **no se deshace solo**: queda un aviso para decidir la devolucion.
