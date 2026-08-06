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
4. Agregá un **Disk** (en la sección "Disks" del servicio):
   - Mount path: `/opt/render/project/src`
   - Esto hace que `stock.db` sobreviva a los reinicios.
5. En "Environment", agregá las variables:
   - `STOCK_USER` = el usuario que quieras
   - `STOCK_PASSWORD` = una clave segura (no dejes la de prueba `admin1234`)
6. Deploy. Render te va a dar una URL fija tipo
   `https://tu-stock.onrender.com` — esa es la que compartís con tus
   empleados.

## 3. Avisame cuando llegues a cada paso

Si te trabás con algo (la pantalla no se parece a lo que describo, un botón
no aparece, etc.), mandame captura y seguimos desde ahí.
