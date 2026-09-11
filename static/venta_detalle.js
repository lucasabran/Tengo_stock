const detailEl = document.getElementById("detail");
const pageTitle = document.getElementById("page-title");

async function load() {
  let sale;
  try {
    sale = await fetchJSON(`/api/sales/${window.SALE_ID}`);
  } catch (err) {
    detailEl.innerHTML = `<div class="empty">${escapeHtml(errorMessage(err))}</div>`;
    return;
  }

  pageTitle.textContent = sale.number;

  const rows = sale.items
    .map(
      (i) => `
        <tr>
          <td>${escapeHtml(i.product_name)}<div class="card-sku">SKU: ${escapeHtml(i.sku)}</div></td>
          <td>${i.quantity}</td>
          <td>${money(i.unit_price)}</td>
          <td>${money(i.line_total)}</td>
          <td>${i.already_returned > 0 ? `${i.already_returned} devuelta(s)` : ""}</td>
        </tr>
      `
    )
    .join("");

  detailEl.innerHTML = `
    <div class="card">
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(sale.channel_name)}</div>
          <div class="card-sku">${escapeHtml(sale.customer_name || "Sin cliente")} &middot; ${formatDateTime(sale.created_at)}</div>
        </div>
        <div class="card-price">${money(sale.total)}</div>
      </div>
      ${sale.note ? `<div class="card-desc">${escapeHtml(sale.note)}</div>` : ""}
      <div class="card-desc">Forma de pago: ${escapeHtml(sale.payment_method || "-")}</div>
    </div>

    <table class="cart-table">
      <thead><tr><th>Producto</th><th>Cant.</th><th>Precio</th><th>Subtotal</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="totals">
      <div>Subtotal: ${money(sale.subtotal)}</div>
      <div>Descuento: ${money(sale.discount)}</div>
      <div>Total: ${money(sale.total)}</div>
    </div>

    <div class="card-actions detail-actions">
      <a class="btn-secondary" href="/ventas/${sale.id}/comprobante" target="_blank">Ver comprobante</a>
      <a class="btn-secondary" href="/devoluciones/nueva?sale_id=${sale.id}">Registrar devolucion</a>
    </div>
  `;
}

load();
