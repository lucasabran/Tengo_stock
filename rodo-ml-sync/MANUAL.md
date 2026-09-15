# Manual: Rodo -> Mercado Libre (sync de catalogo)

Este proyecto scrapea el catalogo publico de rodo.com.ar y publica los
productos en Mercado Libre con un margen de precio sobre el costo de Rodo
(por default +80% en articulos chicos, +100% en electrodomesticos grandes),
usando la API oficial de MercadoLibre. Esta pensado para que lo pueda operar
cualquiera del equipo, no solo quien lo armo originalmente.

## Indice

1. [Instalacion](#1-instalacion)
2. [Crear la app de Mercado Libre](#2-crear-la-app-de-mercado-libre-una-sola-vez)
3. [Login (obtener el token de acceso)](#3-login-obtener-el-token-de-acceso)
4. [Scrapear el catalogo de Rodo](#4-scrapear-el-catalogo-de-rodo)
5. [Publicar en Mercado Libre](#5-publicar-en-mercado-libre)
6. [Como leer el excel de resultado](#6-como-leer-el-excel-de-resultado)
7. [Por que quedan productos en ERROR (y que hacer)](#7-por-que-quedan-productos-en-error-y-que-hacer)
8. [Seguridad: por que todo se publica "pausado"](#8-seguridad-por-que-todo-se-publica-pausado)
9. [Como seguir mejorando el % de exito automatico](#9-como-seguir-mejorando-el--de-exito-automatico)
10. [Archivos del proyecto](#10-archivos-del-proyecto)
11. [Mantenimiento continuo (sync y chequeo de moderaciones)](#11-mantenimiento-continuo-correr-esto-seguido-no-solo-una-vez)
12. [Problemas comunes](#12-problemas-comunes)

---

## 1. Instalacion

Necesitas Python 3.10+ instalado. Despues, desde la carpeta del proyecto:

```bash
pip install -r requirements.txt
```

## 2. Crear la app de Mercado Libre (una sola vez)

1. Entra a https://developers.mercadolibre.com.ar/apps con la cuenta de
   vendedor de Mercado Libre (si nunca usaste el lado developer, primero te
   va a pedir "vincular" tu cuenta -- aceptar).
2. "Crear nueva aplicacion". Completa nombre/descripcion (lo que quieras).
3. **Redirect URI**: cualquier URL https que exista, por ejemplo
   `https://www.google.com`. No hace falta que responda nada especial, es
   solo donde ML te redirige con el codigo de autorizacion.
4. **Flujos OAuth**: dejar tildado "Authorization Code" (y "Refresh Token"
   si queres que el token se renueve solo cada 6hs en vez de tener que
   volver a loguearte -- ver seccion de login mas abajo).
5. **Permisos**: como minimo necesitas "Publicacion y sincronizacion" en
   Lectura y escritura. El resto podes dejarlo en "Sin acceso" (menos
   permisos = menos riesgo si el token se filtra alguna vez).
6. Al crear, ML te muestra el **App ID (Client ID)** y el **Client Secret**
   (para verlo hay que tocar el icono de ojo, y puede pedir una verificacion
   de seguridad extra por tu celular).
7. Copia `.env.example` a `.env` y completa:
   ```
   ML_CLIENT_ID=tu_client_id
   ML_CLIENT_SECRET=tu_client_secret
   ML_REDIRECT_URI=https://www.google.com
   ```

**IMPORTANTE**: `.env` tiene tus credenciales reales. Nunca lo subas a
GitHub (ya esta en `.gitignore`, pero revisa antes de cada `git add`).

## 3. Login (obtener el token de acceso)

MercadoLibre usa OAuth: hay que autorizar la app una vez desde el navegador
para conseguir un `access_token`.

### Opcion A -- con el script (recomendado)

```bash
python ml_auth.py login
```

Se abre el navegador, aceptas los permisos, y ML te redirige a tu
`ML_REDIRECT_URI` con algo como `...?code=TG-xxxxx...` en la URL. Copia ese
`code` completo y pegalo cuando la consola lo pida. Esto guarda `token.json`.

### Opcion B -- a mano (si el paso A falla)

1. Abri en el navegador (reemplazando tu Client ID):
   ```
   https://auth.mercadolibre.com.ar/authorization?response_type=code&client_id=TU_CLIENT_ID&redirect_uri=https://www.google.com
   ```
2. Aceptar los permisos.
3. En la URL final (`https://www.google.com/?code=TG-...`) copiar el valor
   de `code`.
4. Correr:
   ```bash
   python -c "
   import json, time, os
   import requests
   from dotenv import load_dotenv
   load_dotenv()
   resp = requests.post('https://api.mercadolibre.com/oauth/token', data={
       'grant_type': 'authorization_code',
       'client_id': os.environ['ML_CLIENT_ID'],
       'client_secret': os.environ['ML_CLIENT_SECRET'],
       'code': 'PEGA_EL_CODE_ACA',
       'redirect_uri': os.environ['ML_REDIRECT_URI'],
   })
   data = resp.json()
   data['obtained_at'] = int(time.time())
   with open('token.json', 'w', encoding='utf-8') as f:
       json.dump(data, f, indent=2)
   print(resp.status_code, data)
   "
   ```

### Sobre la duracion del token

El `access_token` dura **6 horas**. Si tu app tiene el flujo "Refresh Token"
habilitado, `ml_auth.py`/`ml_upload.py` lo renuevan solos. **Si no lo tiene
habilitado (chequealo en la configuracion de la app en ML), vas a tener que
repetir el login cada vez que el token expire** -- vas a ver el error
`"No hay refresh_token guardado"`. Para evitarlo, anda a "Administrar
permisos" de tu app en developers.mercadolibre.com.ar y activa "Refresh
Token" en los flujos OAuth.

## 4. Scrapear el catalogo de Rodo

Rodo corre sobre Magento y expone una API GraphQL publica de catalogo (no
hace falta login ni credenciales para esto -- es informacion publica del
sitio). El scraper la usa en vez de leer el HTML, es mas rapido y confiable.

```bash
# Prueba chica primero (siempre)
python scraper.py --out prueba.xlsx --limit 20

# Catalogo completo (por default recorre "Productos", la categoria raiz)
python scraper.py --out productos_rodo.xlsx

# Solo una subcategoria puntual (ver IDs con la opcion --category-id)
python scraper.py --out solo_celulares.xlsx --category-id 495
```

Parametros utiles:
- `--markup 1.018` -> multiplicador de precio (1.018 = +1.8%, es el default)
- `--limit N` -> traer solo N productos (para probar)
- `--category-id ID` -> recorrer una categoria puntual de Rodo en vez de
  todo el catalogo (los IDs de categoria se ven en la salida del scraper al
  autodetectar, o inspeccionando `categoryList` via GraphQL)

El excel que genera tiene: `url, sku, title, description, price_original,
price_ml, currency, images, category, availability`. La `description` se
arma con la tabla de especificaciones tecnicas de Rodo (Marca, Modelo,
Pantalla, etc.), porque el campo "descripcion larga" de Magento viene vacio
para la mayoria de los productos de este catalogo.

## 5. Publicar en Mercado Libre

```bash
# SIEMPRE probar antes con --dry-run (no publica nada, solo simula)
python ml_upload.py --in productos_rodo.xlsx --dry-run --limit 10

# Publicar de verdad (quedan como BORRADOR PAUSADO, ver seccion 8)
python ml_upload.py --in productos_rodo.xlsx --out resultado_publicacion.xlsx
```

Parametros utiles:
- `--limit N` -> probar con pocos productos primero
- `--listing-type` -> tipo de publicacion (`gold_special` por default; ver
  los tipos habilitados para tu cuenta en
  `GET https://api.mercadolibre.com/sites/MLA/listing_types`)
- `--condition` -> `new` por default
- `--allow-catalog-attach` -> **NO USAR sin leer la seccion 8 primero**
- `--markup-chico` / `--markup-grande` -> ver mas abajo
- `--publish-status paused|active` -> `paused` por default (ver seccion 8)

El script es seguro para correr varias veces sobre el mismo archivo: usa
`published_skus.json` para no volver a publicar un SKU que ya se publico
bien (lo marca como `SKIPPED`).

### Como se calcula el precio de venta

`precio_venta = costo_rodo * markup`, con dos multiplicadores segun el
tamaño del producto (definido el 3/11/25):

- `--markup-chico` (default **1.8**, +80%): todo Electrohogar excepto los
  grandes de linea blanca.
- `--markup-grande` (default **2.0**, +100%): heladera, freezer,
  refrigerador, lavarropas, lavaseca, secarropas, aire acondicionado,
  split, lavavajillas, cocina (ver `LARGE_ITEM_KEYWORDS` en `ml_upload.py`
  si hay que sumar mas palabras clave).

El precio publicado es siempre el de **contado / 1 pago**. Los recargos
por cuotas (12.5% a 3 cuotas, 20% a 6, 33% a 9, 50% a 12, segun la tabla
de referencia del vendedor) **no se meten en el precio del articulo**
-- Mercado Libre solo permite un precio unico por publicacion. Esos
recargos se administran aparte, en la configuracion de cuotas sin interes
/ financiacion de Mercado Libre.

**IMPORTANTE -- por que NO se descuenta la comision de venta de ML:** en
un momento el precio se calculaba para dejar un margen NETO ya
descontada la comision de ML (que ronda 10-16% segun categoria) usando
`--account-for-ml-fee`. El vendedor decidio simplificarlo: con un margen
bruto del 80-100% sobra de sobra para cubrir esa comision, asi que por
default el calculo es directo (`costo_rodo * markup`) sin consultar la
comision. La opcion `--account-for-ml-fee` sigue disponible por si en
algun momento se usa un markup mas chico donde la comision si importe
(ver seccion 8: se detecto vendiendo a perdida real con un margen chico
del 1.8% sin tener esto en cuenta).

## 6. Como leer el excel de resultado

Columnas: `url, sku, title, price_ml, status, detail, metodo`

| status | Que significa |
|---|---|
| `OK` | Se publico. `detail` tiene el ID de la publicacion en ML (ej `MLA123456789`). Queda **pausada** (ver seccion 8), hay que revisarla y activarla a mano. |
| `ERROR` | No se pudo publicar. `detail` tiene el mensaje de error de la API de ML -- ver seccion 7. |
| `SKIPPED` | Se salteo: o falta titulo/precio, o el SKU ya estaba publicado antes (`detail` dice el ID existente). |
| `DRY_RUN` | Solo con `--dry-run`: muestra que categoria y que dimensiones de paquete le asignaria, sin publicar nada. |

`metodo` dice como se publico: `directo` (con nuestro titulo/fotos propios,
lo normal) o `catalogo` (enganchado a una ficha de catalogo de ML -- solo
pasa si corriste con `--allow-catalog-attach`, desactivado por default).

## 7. Por que quedan productos en ERROR (y que hacer)

Hay tres motivos tipicos:

**a) Mercado Libre exige un codigo de barras (GTIN) real.**
Pasa cuando el producto (marca+modelo) ya esta cargado en el catalogo
oficial de ML. Rodo no publica codigos de barras en su sitio, asi que no
hay forma de resolver esto automaticamente. **Que hacer**: entra a la
publicacion en el editor de ML (o crea una nueva ahi) y usa el buscador de
catalogo -- si escribis la marca y el modelo, ML te va a sugerir la ficha
oficial correcta (con una persona mirando la pantalla, no a ciegas como
haria un script).

**b) Falta un atributo puntual que Rodo no publica** (ej: "Colección" de un
videojuego, "Tipo de lavarropas", "Línea del procesador"). El mensaje de
error dice exactamente cual. **Que hacer**: revisa si se puede agregar un
valor generico razonable en `GENERIC_ATTRIBUTE_DEFAULTS` o un sinonimo en
`ATTRIBUTE_ALIASES` dentro de `ml_upload.py` (ver seccion 9), o completalo
a mano en el editor de ML.

**c) Dimensiones/peso de paquete mal estimados.** El script estima peso y
tamaño del paquete por palabra clave o categoria (ver `PACKAGE_KEYWORDS` y
`CATEGORY_ESTIMATES` en `ml_upload.py`) porque Rodo no publica ese dato.
Si ML dice que el paquete declarado es "demasiado chico" para el producto,
hay que subir el valor estimado para esa palabra clave/categoria.

## 8. Seguridad: por que todo se publica "pausado"

Todas las publicaciones se crean con `status: paused` (borrador, invisible
para compradores) **a proposito**, por dos motivos:

1. **Evita el problema del GTIN casi siempre.** ML valida el requisito de
   codigo de barras real de forma mas estricta para publicaciones activas
   que para borradores.
2. **Da lugar a revision humana antes de vender algo mal representado.**

Hubo un incidente real durante el desarrollo de este proyecto: una version
anterior intentaba "enganchar" automaticamente productos a fichas de
catalogo existentes de ML para esquivar el GTIN. Se detecto que en varios
casos enganchaba a la ficha equivocada -- **una marca distinta, un combo
con regalo que Rodo no incluye, y hasta un repuesto/control remoto en vez
del producto principal** (un aire acondicionado de $780.000 publicado con
titulo y foto de un control remoto). Esa funcion quedo **desactivada por
default** (flag `--allow-catalog-attach`, con advertencia en el codigo).
No la actives salvo que agregues una verificacion mucho mas estricta
(marca Y color/variante exactos) y revises a mano cada publicacion antes
de activarla.

**Flujo recomendado**: publicar (queda pausado) -> revisar cada
publicacion en ML (titulo, fotos, precio, categoria) -> activar a mano.

### Segundo incidente real: "paused" no se sostenia solo

En una tanda grande (699 productos) se detecto que Mercado Libre pasaba
publicaciones de `paused` a `active` **por su cuenta, un rato despues de
creadas** (aparentemente al terminar de procesar las fotos), aunque se
hubiera pedido `status: paused` al crearlas. Resultado: 134 publicaciones
quedaron activas y publicas sin revision. Se pausaron todas a mano
apenas se detecto.

**Arreglo aplicado**: despues de crear cada item, `ml_upload.py` ahora hace
un **PUT explicito de confirmacion** (`force_pause` en el codigo) pidiendo
`status: paused` de nuevo, como si un vendedor lo pausara a mano. Esa
confirmacion demostro sostenerse (queda con `sub_status: paused_by_seller`,
un estado mas firme). Igual, **como red de seguridad extra**, correr de
tanto en tanto (sobre todo despues de una tanda grande):

```bash
python pause_sweep.py           # revisa y pausa cualquier cosa que se haya activado sola
python pause_sweep.py --dry-run # solo mostrar, no tocar nada
```

No asumir que "publicar en modo pausado" es garantia permanente -- revisar
(con `pause_sweep.py` o a mano en ML) despues de cualquier tanda grande,
sobre todo si no se va a revisar/activar cada publicacion enseguida.

## 9. Como seguir mejorando el % de exito automatico

El catalogo de Rodo es enorme y cada categoria de ML pide atributos
distintos -- esto se va a seguir puliendo con el tiempo, no hay forma de
cubrir todo de una. Los lugares donde sumar mejoras, todos en
`ml_upload.py`:

- **`GENERIC_ATTRIBUTE_DEFAULTS`**: valores genericos seguros para
  atributos que Rodo no publica (ej: `"voltaje": "220V"`). Sumar una
  entrada nueva cuando aparezca un atributo faltante que tenga un valor
  razonable para (casi) todo el catalogo argentino.
- **`ATTRIBUTE_ALIASES`**: cuando ML pide un atributo con un nombre
  distinto al que usa Rodo para lo mismo (ej: ML dice "Línea del
  procesador", Rodo dice "Tipo de procesador").
- **`PACKAGE_KEYWORDS` / `CATEGORY_ESTIMATES`**: estimaciones de peso y
  dimensiones de paquete por palabra clave del titulo o por categoria.
- **`PLATFORM_KEYWORDS`**: plataforma de videojuegos segun palabras del
  titulo (PS5, Xbox, etc.)

Como se corrige un atributo nuevo, paso a paso:
1. Correr `ml_upload.py`, ver el `ERROR` con el mensaje de ML (dice el
   nombre exacto del campo que falta).
2. Decidir si tiene un valor generico razonable (agregar a
   `GENERIC_ATTRIBUTE_DEFAULTS`), si es un sinonimo de algo que ya
   scrapeamos (agregar a `ATTRIBUTE_ALIASES`), o si realmente no se puede
   inferir (dejarlo como caso manual).
3. Volver a correr sobre el mismo excel de entrada -- `published_skus.json`
   evita que se dupliquen los que ya salieron bien.

## 10. Archivos del proyecto

**Scripts que corren de a uno (setup / publicacion inicial):**

| Archivo | Que es |
|---|---|
| `scraper_manual.py` | Baja el catalogo de Rodo (GraphQL publico) a un excel. Autocontenido, sin depender de otros archivos del proyecto. |
| `ml_auth.py` | Login OAuth con Mercado Libre, guarda/renueva `token.json`. |
| `ml_upload.py` | Publica el excel del scraper en Mercado Libre (precio, empaque, fotos, atributos -- toda la logica principal vive aca). |

**Scripts que conviene correr seguido, ya con el catalogo publicado (ver seccion 11):**

| Archivo | Que es |
|---|---|
| `sync_prices_stock.py` | Compara TODO lo publicado contra el precio/stock actual de Rodo y actualiza lo que cambio, pausa lo descontinuado, repone y reactiva lo que se vendio y volvio a tener stock. |
| `moderation_sweep.py` | Encuentra publicaciones ocultas por moderacion de ML (`waiting_for_patch`) y resuelve las de catalogo que se pueden verificar con confianza. |
| `activate_sweep.py` / `pause_sweep.py` | Redes de seguridad: activan/pausan publicaciones registradas que quedaron en un estado que no corresponde. |
| `catalog_optin.py` | Antecesor de `moderation_sweep.py` para el mismo problema de catalogo, mas lento (busca el producto de catalogo en vez de que ML lo sugiera) -- usar `moderation_sweep.py` primero. |

**Archivos de estado y configuracion (todos especificos de la cuenta de ML de quien los usa -- ninguno se sube a git):**

| Archivo | Que es |
|---|---|
| `.env` | Credenciales de la app de ML. Copiar de `.env.example`. |
| `token.json` | Token de acceso vigente, se regenera con `ml_auth.py login`. |
| `published_skus.json` | SKU de Rodo -> ID de publicacion en ML. Es la fuente de verdad de que ya esta publicado (evita duplicados). |
| `stock_paused_skus.json` | SKUs pausados por falta de stock real en Rodo (para no reactivarlos a ciegas). |
| `discontinued_skus.json` | SKUs que ya no existen en Rodo (productos discontinuados). |
| `catalog_listings.json` | ID de publicacion tradicional -> ID de su publicacion de catalogo hermana (ver seccion 11). |
| `requirements.txt` | Dependencias de Python. |

## 11. Mantenimiento continuo (correr esto seguido, no solo una vez)

Publicar el catalogo es el arranque. Despues de eso, el trabajo real es
mantenerlo sincronizado -- Rodo cambia precios y stock todo el tiempo, y
Mercado Libre puede ocultar publicaciones por su cuenta.

### Sync de precio y stock

```bash
python sync_prices_stock.py
```

Recorre TODO lo publicado (`published_skus.json`) y compara contra Rodo:
actualiza precios que cambiaron, pausa lo que Rodo dejo de tener, pausa lo
que ya no existe en Rodo (descontinuado), y **repone stock (3 unidades por
default, `ml_upload.DEFAULT_STOCK`) y reactiva** lo que se vendio y Rodo
volvio a tener. Correrlo seguido (se recomienda al menos una vez por
semana) evita vender algo sin stock real o con un precio viejo.

### El aviso de ML "pausamos tus publicaciones porque debes competir en catalogo"

Mercado Libre puede ocultar una publicacion (`status: under_review,
sub_status: waiting_for_patch`) pidiendo que confirmes si es el mismo
producto que uno de su catalogo. **Esto NO se resuelve solo** -- si se
deja, escala a `forbidden` (bloqueo permanente). La primera vez que nos
paso esto, 49 publicaciones llevaban semanas ocultas sin que nadie lo
supiera.

```bash
python moderation_sweep.py            # solo reporta, no toca nada
python moderation_sweep.py --create   # confirma los matches verificados con confianza
```

Para cada publicacion oculta, consulta el motivo real
(`GET /moderations/last_moderation/{id}-ITM`) y:
- Si ML sugiere un producto de catalogo (`OPT_OBEY`), verifica que la
  marca (atributo real `BRAND`, no adivinada) y el codigo de modelo mas
  especifico del titulo aparezcan literal en el nombre del producto
  sugerido antes de confirmar. Si confirma, reactiva la publicacion
  tradicional Y crea una publicacion de catalogo hermana (queda registrada
  en `catalog_listings.json`) -- las dos conviven, no es duplicar.
- Si el titulo o las fotos no coinciden con el producto
  (`INCONSISTENCY_CHECK`), lo reporta para revisar las fotos a mano (en la
  practica, casi siempre es la foto de portada mostrando un accesorio
  suelto en vez del producto completo, o el color equivocado).
- Todo lo que no se pueda verificar con confianza alta **se deja sin
  tocar** -- mejor perder una reactivacion posible que arriesgar un match
  a un producto de catalogo equivocado (ver seccion 8, el incidente real
  de matching que motivo esta cautela).

### Sobre "cuotas" -- que SI se puede hacer y que NO

Cobrarle mas al comprador por pagar en cuotas (recargo por cantidad de
cuotas) **no es algo que Mercado Libre permita configurar**, ni con
publicaciones separadas (prohibido explicitamente, riesgo de suspension de
cuenta por "publicaciones duplicadas"), ni con variantes, ni de ninguna
otra forma -- el interes de las cuotas lo determina el banco/tarjeta del
comprador.

Lo que SI existe, en cada publicacion (seccion "Cargo por vender y
opciones de cuotas" del editor de Mercado Libre): el VENDEDOR paga una
comision de venta mas alta para ofrecerle cuotas sin interes (o con
interes bajo) al comprador **al mismo precio publicado**. No le cobra de
mas al comprador -- resigna margen a cambio de mejor posicionamiento.
Ejemplo real visto en la cuenta (comision base 14,5%): 3 cuotas +8,9%,
6 cuotas +13,4% (la que ML recomienda), 9 cuotas +17,8%, 12 cuotas +21,6%.
Es una decision de negocio (cuanto margen resignar) -- no esta
automatizado en ningun script de este proyecto.

## 12. Problemas comunes

**"No hay refresh_token guardado. Corra: python ml_auth.py login"**
El access_token vencio (dura 6hs) y la app no tiene habilitado el flujo
"Refresh Token". Volve a correr `python ml_auth.py login`, o habilita ese
flujo en la configuracion de la app en ML para que no vuelva a pasar.

**`invalid client_id or client_secret` al hacer login**
Revisa que copiaste el Client Secret bien -- si lo copiaste mirando la
pantalla en vez de con Ctrl+C, es facil confundir `l` minuscula con `I`
mayuscula o similares. Mejor copiar y pegar directo, no transcribir a mano.

**Un producto que antes fallaba ahora funciona con el mismo comando**
Es esperable: el requisito de GTIN real depende de si ESE modelo puntual
ya esta en el catalogo interno de ML, y ML va sumando/actualizando su
catalogo todo el tiempo.

**El scraper no encuentra productos / trae 0**
Rodo puede estar caido (probar abrir rodo.com.ar en el navegador primero)
o haber cambiado su API GraphQL. Revisar `scraper_manual.py` -- las
queries estan comentadas y son faciles de ajustar si cambia el schema.

**`python ml_auth.py login` no abre el navegador solo**
Puede pasar segun el entorno donde lo corras. El script igual sigue y pide
pegar el `code` por consola -- copia manualmente la URL que imprime en la
terminal, abrila en cualquier navegador donde ya tengas sesion iniciada en
ML, autoriza la app, y en la pagina a la que te redirige copia la URL
COMPLETA de la barra de direcciones (aunque la pagina se vea vacia/como un
buscador comun) -- el `?code=...` esta ahi.
