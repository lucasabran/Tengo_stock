# rodo-ml-sync

Scraper de un catalogo de proveedor (rodo.com.ar, via su API GraphQL
publica) + publicacion masiva en Mercado Libre con un margen de precio
configurable, sync continua de precio/stock, y resolucion automatica de
los problemas mas comunes que aparecen al publicar en volumen (medidas de
paquete, portada de fotos, publicaciones ocultas por moderacion de
catalogo). Pensado para que lo pueda operar y adaptar cualquiera del
equipo -- o alguien reusando el patron con otro proveedor y otra cuenta de
ML -- no solo quien lo armo originalmente.

**Para la guia completa (setup, cada comando, como leer los resultados, que
hacer con los errores, y como seguir mejorando esto) ver [MANUAL.md](MANUAL.md).**

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env   # completar con tu Client ID / Secret de developers.mercadolibre.com.ar
python ml_auth.py login
python scraper_manual.py --out productos_rodo.xlsx --limit 20
python ml_upload.py --in productos_rodo.xlsx --dry-run --limit 5
python ml_upload.py --in productos_rodo.xlsx --out resultado_publicacion.xlsx
```

Las publicaciones se crean **pausadas** (borrador, no visibles para
compradores) a proposito -- hay que revisarlas y activarlas a mano desde
Mercado Libre. Ver la seccion 8 de [MANUAL.md](MANUAL.md) para el porque.

Despues de la publicacion inicial, el trabajo real es mantenerlo
sincronizado -- ver la seccion 11 de [MANUAL.md](MANUAL.md):

```bash
python sync_prices_stock.py       # precio y stock al dia contra el proveedor
python moderation_sweep.py        # publicaciones ocultas por ML, resueltas donde se puede con confianza
```

## Estructura

- `scraper_manual.py` -- baja el catalogo del proveedor a un excel.
- `ml_auth.py` -- login OAuth con Mercado Libre.
- `ml_upload.py` -- publica el excel en Mercado Libre.
- `sync_prices_stock.py` -- mantiene precio/stock al dia contra el proveedor.
- `moderation_sweep.py` -- destraba publicaciones ocultas por moderacion de ML.
- `activate_sweep.py` / `pause_sweep.py` -- redes de seguridad de estado.
- `catalog_optin.py` -- version anterior de la resolucion de catalogo (mas lenta, ver MANUAL.md seccion 11).
- `MANUAL.md` -- guia completa paso a paso, con el historial de incidentes reales y sus arreglos.

## Adaptar esto a otro proveedor / otra cuenta

El unico archivo con logica especifica de Rodo (las queries GraphQL, como
arma la descripcion) es `scraper_manual.py` -- ahi es donde hay que tocar
para apuntar a otro sitio. Todo lo demas (`ml_upload.py` en adelante) solo
espera un excel con columnas `url, sku, title, description,
price_original, price_ml, currency, images, category, availability` y no
sabe nada de Rodo en particular. `MANUAL.md` seccion 8 y 11 documentan los
incidentes reales que motivaron cada resguardo del codigo -- vale la pena
leerlos antes de publicar en volumen con una cuenta nueva.
