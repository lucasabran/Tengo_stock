# Plan Pre-Cyber + CyberMonday 2026 — Tengo Stock

**Fechas:** CyberMonday 2026 es del lunes 2 al miércoles 4 de noviembre.
**Regla:** los precios de lista no se tocan. Todo el descuento va por cupones que se aplican en el carrito.

---

## 1. Calendario

| Fecha | Qué pasa | Canal |
|---|---|---|
| **Hoy → 1/11** | Captar emails y WhatsApp con el cupón de bienvenida + "Lista VIP Cyber" | Popup de la web, Perfit, bot de WhatsApp |
| **Jue 29/10** | Aviso: "Se viene CyberMonday" (los códigos se anuncian el domingo) | Email 3 |
| **Dom 1/11, 20 h** | Acceso anticipado: los códigos CYBER se activan 4 h antes, solo para la lista VIP | Email 4 |
| **Lun 2/11, 0 h** | Arranca CyberMonday: banner, sección, Google con presupuesto más alto | Web, Google, Email 5 |
| **Mar 3/11** | Recordatorio con lo más vendido por categoría | Email 6 |
| **Mié 4/11, 18 h** | "Últimas horas" | Email 7 |
| **Jue 5/11** | Volver todo a la normalidad: desactivar cupones y banner, bajar el presupuesto | — |

---

## 2. Cupones (PARA APROBAR: no se crean hasta que digas los números)

### Cupón de bienvenida (desde ya)
| Código | Descuento | Mínimo de compra | Uso |
|---|---|---|---|
| **BIENVENIDA** | 5% | $150.000 | 1 por cliente, solo primera compra |

### Cupones escalonados CyberMonday (2/11 0 h → 4/11 23:59)
Cuanto más alto el carrito, mayor el descuento. Así se sube el ticket promedio sin tocar los precios.

| Código | Descuento | Mínimo de compra | Ejemplo |
|---|---|---|---|
| **CYBER5** | 5% | $300.000 | Carrito $400.000 → ahorra $20.000 |
| **CYBER8** | 8% | $800.000 | Carrito $1.000.000 → ahorra $80.000 |
| **CYBER10** | 10% | $1.500.000 | Carrito $2.000.000 → ahorra $200.000 |

- Revisar el margen de cada categoría antes de aprobar. En celulares y TV el margen suele ser bajo: se pueden **excluir del cupón** o dejarles solo el 5%.
- Los cupones no se suman entre sí (Tiendanube aplica uno por compra).
- Comunicación: **"CyberMonday: hasta 10% OFF extra con tu código + 3 y 6 cuotas sin interés"**.

> Para crearlos, decime: *"Creá BIENVENIDA 5% desde $150.000 y CYBER5/8/10 con esos mínimos, del 2/11 al 4/11"* (o los números que prefieras).

---

## 3. La tienda (web)
- **Banner CyberMonday** para celular y computadora (lo genero yo cuando aprueben los cupones). Va en el carrusel del 1/11 a la noche al 4/11.
- **Sección "CyberMonday":** reusar la categoría *DÍA DE LA MADRE* renombrada a *CYBERMONDAY* con los productos más vendidos y con stock. Así no queda una categoría vieja en el menú "Productos".
- **Barra de anuncios** (arriba de todo): "CYBERMONDAY · Hasta 10% OFF extra con tu código · 3 y 6 cuotas sin interés".
- **Popup de la ruleta:** cambiar el premio a "5% OFF con BIENVENIDA" y el título a "Sumate a la Lista VIP Cyber".

## 4. Google
- **Performance Max:** subir el presupuesto de $5.000 a **$10.000/día** del 1/11 al 4/11 y volver el 5/11. *(Necesita tu OK porque es gasto.)*
- **Recurso de promoción** en Performance Max y Marca: "Hasta 10% OFF · código CYBER10 · 2 al 4 de noviembre".
- **Merchant Center:** marcar los productos de la sección Cyber con `custom_label_0 = cyber` (lo hace `feed_google.py`), para poder medirlos aparte.

---

## 5. Emails (Perfit) — copiar y pegar

### Email 1 · Bienvenida (automatización: al suscribirse)
- **Asunto:** Tu 5% OFF de bienvenida está acá 🎁
- **Preheader:** Usalo en tu primera compra en Tengo Stock
- **Cuerpo:**
  > ¡Hola {{nombre}}! Gracias por sumarte a Tengo Stock.
  > Tenés **5% OFF** en tu primera compra con el código **BIENVENIDA** (compras desde $150.000).
  > Tecnología, electrodomésticos y climatización con garantía oficial, 3 y 6 cuotas sin interés y la opción de extender la garantía hasta 60 meses.
  > Además ya estás en la **Lista VIP Cyber**: el domingo 1/11 a las 20 h te mandamos los códigos antes que a nadie.
- **Botón:** VER PRODUCTOS → https://tengostockarg.com.ar

### Email 2 · Carrito abandonado (automatización: 1 h y 24 h después)
- **Asunto (1 h):** ¿Te quedó algo en el carrito? 🛒
- **Asunto (24 h):** Tu carrito te sigue esperando (y el stock vuela)
- **Cuerpo:**
  > Hola {{nombre}}, guardamos tu carrito: {{productos_del_carrito}}.
  > Recordá: 3 y 6 cuotas sin interés, y al tocar COMPRAR podés extender la garantía hasta 60 meses.
  > ¿Dudas? Escribinos por WhatsApp y te respondemos al toque.
- **Botón:** TERMINAR MI COMPRA → {{link_carrito}}

### Email 3 · Teaser (jueves 29/10)
- **Asunto:** Se viene CyberMonday en Tengo Stock ⚡
- **Preheader:** Hasta 10% OFF extra. Los códigos llegan el domingo.
- **Cuerpo:**
  > Del **2 al 4 de noviembre** vas a tener **hasta 10% OFF extra** con tu código, sumado a 3 y 6 cuotas sin interés.
  > Como estás en nuestra lista, **el domingo 1/11 a las 20 h** te mandamos los códigos 4 horas antes que al resto.
  > Tip: armá tu lista de favoritos desde ahora. Cuanto más grande el carrito, más grande el descuento.
- **Botón:** ARMAR MI LISTA → https://tengostockarg.com.ar

### Email 4 · Acceso VIP (domingo 1/11, 20 h)
- **Asunto:** 🔓 Tus códigos CyberMonday (solo para vos, desde YA)
- **Preheader:** Hasta 10% OFF extra según tu carrito
- **Cuerpo:**
  > Llegó tu acceso anticipado. Desde ahora y hasta el miércoles 4/11:
  > • **CYBER5**: 5% OFF en compras desde $300.000
  > • **CYBER8**: 8% OFF desde $800.000
  > • **CYBER10**: 10% OFF desde $1.500.000
  > Se suman las 3 y 6 cuotas sin interés. Stock limitado.
- **Botón:** COMPRAR CON MI CÓDIGO → https://tengostockarg.com.ar

### Email 5 · Lanzamiento (lunes 2/11, 9 h)
- **Asunto:** CyberMonday arrancó: hasta 10% OFF extra ⚡
- **Preheader:** Usá CYBER5, CYBER8 o CYBER10 según tu compra
- **Cuerpo:** igual al email 4, con 3 bloques de productos: *Tecnología · Electrodomésticos · Climatización*.
- **Botón:** VER OFERTAS → https://tengostockarg.com.ar

### Email 6 · Recordatorio (martes 3/11, 13 h)
- **Asunto:** Lo más elegido del CyberMonday (con stock) 🔥
- **Cuerpo:** "Esto es lo que más se está llevando la gente" + 6 productos + los 3 códigos.

### Email 7 · Última oportunidad (miércoles 4/11, 18 h)
- **Asunto:** ⏰ Últimas horas: tu código vence a las 23:59
- **Cuerpo:** "Hoy a las 23:59 se terminan los códigos CYBER. Si lo estabas pensando, es ahora." + los 3 códigos.

**Para configurar Perfit:** crear la cuenta en perfit.com.ar → *Integraciones → Tiendanube* (importa clientes y activa el carrito abandonado) → crear las 2 automatizaciones (1 y 2) y programar las 5 campañas (3 a 7).

---

## 6. WhatsApp
- **Bot con IA:** carpeta `whatsapp_bot/` (ver `LEEME.md`). Responde las 24 h con precios y stock reales.
  Cuando se creen los cupones, agregarlos en `info_tienda.md → Promociones vigentes` para que el bot los informe.
- **Mensajes masivos** (requieren plantillas aprobadas por Meta y se pagan por mensaje; mandar solo a quienes aceptaron recibirlos):
  - *Plantilla "cyber_vip" (1/11):* "Hola {{1}} 👋 Ya podés usar tus códigos CyberMonday en Tengo Stock: CYBER5, CYBER8 y CYBER10, hasta 10% OFF extra según tu compra. Válidos hasta el miércoles 4/11. 👉 tengostockarg.com.ar"
  - *Plantilla "cyber_ultimas_horas" (4/11):* "Hola {{1}}, hoy a las 23:59 vencen los códigos CyberMonday de Tengo Stock ⏰ Si querés que te ayudemos a elegir, respondé este mensaje."

---

## 7. Qué medir (5/11)
- Ventas y ticket promedio del 2 al 4/11 contra las 2 semanas anteriores (Tiendanube → Estadísticas).
- Usos de cada cupón (Descuentos → Cupones).
- Conversiones y costo por venta en Google Ads (campañas Performance Max y Marca).
- Emails: aperturas, clics y ventas atribuidas (Perfit).
- Conversaciones del bot y derivaciones (`derivaciones.log`).
