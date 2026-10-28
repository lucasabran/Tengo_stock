const listEl = document.getElementById("list");
const skuEl = document.getElementById("filter-sku");
const fromEl = document.getElementById("filter-from");
const toEl = document.getElementById("filter-to");

const REASON_LABELS = {
  ajuste_manual: "Ajuste manual",
  compra_proveedor: "Compra a proveedor",
  ajuste_inventario: "Ajuste de inventario",
  devolucion_proveedor: "Devolucion a proveedor",
  otro: "Otro",
  venta: "Venta",
  devolucion: "Devolucion de cliente",
  transferencia: "Transferencia entre oficinas",
  stock_inicial: "Stock inicial",
};

const officeEl = document.getElementById("filter-office");

async function loadOffices() {
  const offices = await fetchJSON("/api/offices");
  if (window.USER_OFFICE) {
    officeEl.classList.add("hidden");
    return;
  }
  for (const o of offices) {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = o.name;
    officeEl.appendChild(opt);
  }
}

async function loadProducts() {
  const products = await fetchJSON("/api/products");
  for (const p of products) {
    const opt = document.createElement("option");
    opt.value = p.sku;
    opt.textContent = `${p.name} (${p.sku})`;
    skuEl.appendChild(opt);
  }
}

function render(movements) {
  listEl.innerHTML = "";
  if (!movements.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay movimientos registrados.</div>';
    return;
  }
  for (const m of movements) {
    const row = document.createElement("div");
    row.className = "list-row";
    const positive = m.change_qty > 0;
    const sign = positive ? "+" : "";
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(m.product_name)} <span class="card-sku">SKU: ${escapeHtml(m.sku)}</span></div>
        <div class="list-row-sub">${escapeHtml(REASON_LABELS[m.reason] || m.reason)}${m.office_name ? " &middot; " + escapeHtml(m.office_name) : ""}${m.note ? " &middot; " + escapeHtml(m.note) : ""} &middot; ${formatDateTime(m.created_at)}${m.created_by ? " &middot; " + escapeHtml(m.created_by) : ""}</div>
      </div>
      <div class="list-row-amount ${positive ? "movement-positive" : "movement-negative"}">${sign}${m.change_qty}</div>
    `;
    listEl.appendChild(row);
  }
}

async function refresh() {
  const params = new URLSearchParams();
  if (skuEl.value) params.set("sku", skuEl.value);
  if (officeEl.value) params.set("office_id", officeEl.value);
  if (fromEl.value) params.set("date_from", fromEl.value);
  if (toEl.value) params.set("date_to", toEl.value);
  const movements = await fetchJSON(`/api/stock-movements?${params.toString()}`);
  render(movements);
}

skuEl.addEventListener("change", refresh);
officeEl.addEventListener("change", refresh);
fromEl.addEventListener("change", refresh);
toEl.addEventListener("change", refresh);

Promise.all([loadProducts(), loadOffices()]).then(refresh);
