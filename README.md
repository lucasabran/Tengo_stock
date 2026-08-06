# Stock

App chica para llevar el stock: SKU, nombre, precio, descripcion y cantidad.
Se abre desde el navegador (PC o celu) y todos los que tengan el link y la
clave pueden cargar y editar productos.

## Usuario y clave

La app pide usuario y contraseña (un cartel del navegador, no hace falta
pantalla propia). Por defecto, mientras no configures nada, es:

- Usuario: `admin`
- Clave: `admin1234`

**Antes de compartirla con tus empleados o subirla a internet, cambiala.**
Se configura con variables de entorno `STOCK_USER` y `STOCK_PASSWORD`. En
Windows, antes de correr `python app.py`:

```bash
set STOCK_USER=tunombre
set STOCK_PASSWORD=tuclavesegura
python app.py
```

Es una sola clave compartida entre todos los empleados (no hay usuarios
individuales por ahora).

## Como correrla (primera vez)

1. Abrir una terminal en esta carpeta (`stock-app`).
2. Instalar dependencias:

   ```bash
   pip install -r requirements.txt
   ```

3. Levantar el servidor:

   ```bash
   python app.py
   ```

4. Va a decir algo como `Running on http://0.0.0.0:5000`. En la misma PC
   entrás desde `http://localhost:5000`.

## Como entrar desde el celu

El celu tiene que estar conectado al **mismo WiFi** que la PC donde corre
el programa.

1. En la PC, buscar la IP local:
   - Windows: abrir otra terminal y correr `ipconfig`, buscar "Direccion IPv4"
     (algo como `192.168.0.15`).
2. En el celu, abrir el navegador y entrar a `http://192.168.0.15:5000`
   (con la IP que te haya dado el paso anterior).
3. Listo, desde ahi se puede buscar, cargar stock nuevo, editar precio/cantidad
   y eliminar productos.

> Mientras la terminal con `python app.py` este abierta, el sitio funciona.
> Si la cerras, se corta.

## Carga masiva (importar todo el stock de una)

En vez de cargar producto por producto, se puede importar un Excel (.xlsx)
o CSV con todo el inventario de una vez:

1. En la web, hace click en **"Descargar plantilla"** para bajar un CSV con
   las columnas correctas.
2. Completalo con tu stock actual (podes abrirlo con Excel/Google Sheets)
   o armar tu propio archivo, siempre que tenga estas columnas (el nombre
   puede estar en español o ingles, no importan mayusculas):
   - `sku` / `codigo`
   - `name` / `nombre` / `producto`
   - `price` / `precio`
   - `quantity` / `cantidad` / `stock`
   - `description` / `descripcion` / `detalle` (opcional)
3. Guardalo como `.csv` o `.xlsx` y en la web toca **"Importar stock"**,
   elegis el archivo.
4. Te va a avisar cuantos productos se crearon y cuantos se actualizaron.

Si un SKU ya existe, la importacion **lo actualiza** (nombre, precio,
cantidad, descripcion) en vez de duplicarlo. Asi tambien podes usarla mas
adelante para re-sincronizar todo el stock, no solo para la carga inicial.

## Los datos

Todo se guarda en un archivo `stock.db` (SQLite) que se crea solo la primera
vez que corres la app. Ese archivo es tu base de datos completa: convendria
hacerle una copia de vez en cuando (copiarlo a un pendrive o subirlo a Drive)
por las dudas.

## Proximo paso: conectar el bot

Esta app ya expone una API REST simple que el bot va a poder consultar:

- `GET /api/products?q=texto` -> busca por SKU o nombre
- `GET /api/products/<sku>` -> no implementado individual, pero se puede
  filtrar con `?q=`
- `POST /api/products/<sku>/add-stock` -> suma o resta stock

Cuando armes el bot de IG/WhatsApp, la idea es que en vez de leer un archivo
Excel, le pegue a esta misma API (o directamente a `stock.db`) para saber
que hay en stock y a que precio, en tiempo real.

### Para que funcione desde afuera de tu WiFi (empleados en otro lado)

La app ya esta lista para subirse a un hosting (tiene `Procfile` y
`gunicorn` en `requirements.txt`, que es lo que piden Render, Railway, etc).

Importante antes de subirla: muchos hostings gratuitos **no guardan de forma
permanente los archivos** (el `stock.db`) y lo resetean en cada reinicio o
despliegue. Para stock real eso es un problema, asi que hay que elegir un
plan que tenga disco persistente (a veces es un agregado pago, unos pocos
dolares por mes) o pasar la base a un servicio de base de datos en la nube.
Lo definimos juntos antes de publicarla para no perder datos.
