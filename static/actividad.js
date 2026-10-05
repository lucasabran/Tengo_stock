const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const userEl = document.getElementById("filter-user");
const actionEl = document.getElementById("filter-action");

const ACTION_LABELS = {
  login: "Ingreso",
  logout: "Salida",
  login_fallido: "Ingreso fallido",
  login_bloqueado: "Ingreso bloqueado",
  cambio_clave: "Cambio de clave",
  usuario_creado: "Usuario creado",
  usuario_editado: "Usuario editado",
  clave_reseteada: "Clave reseteada",
  rol_creado: "Rol creado",
  rol_editado: "Rol editado",
  rol_eliminado: "Rol eliminado",
  venta_creada: "Venta registrada",
  devolucion_creada: "Devolucion registrada",
  producto_creado: "Producto creado",
  producto_editado: "Producto editado",
  producto_eliminado: "Producto eliminado",
  stock_cargado: "Stock cargado",
  productos_importados: "Importacion de productos",
  foto_subida: "Foto subida",
  foto_eliminada: "Foto eliminada",
  gasto_creado: "Gasto creado",
  gasto_editado: "Gasto editado",
  gasto_eliminado: "Gasto eliminado",
  cliente_creado: "Cliente creado",
  cliente_editado: "Cliente editado",
  cliente_eliminado: "Cliente eliminado",
  canal_creado: "Canal creado",
  canal_editado: "Canal editado",
  movimiento_cuenta: "Movimiento de cuenta corriente",
};

function actionLabel(a) {
  return ACTION_LABELS[a] || a;
}

let filtersLoaded = false;

async function load() {
  const params = new URLSearchParams();
  if (userEl.value) params.set("user", userEl.value);
  if (actionEl.value) params.set("action", actionEl.value);
  if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
  const data = await fetchJSON(`/api/audit?${params.toString()}`);

  if (!filtersLoaded) {
    filtersLoaded = true;
    for (const u of data.users) userEl.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(u)}">${escapeHtml(u)}</option>`);
    for (const a of data.actions) actionEl.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(a)}">${escapeHtml(actionLabel(a))}</option>`);
  }

  listEl.innerHTML = "";
  if (!data.items.length) {
    listEl.innerHTML = '<div class="empty">Sin actividad registrada.</div>';
    return;
  }
  for (const item of data.items) {
    const row = document.createElement("div");
    row.className = "list-row";
    const bad = item.action.includes("fallido") || item.action.includes("bloqueado");
    row.innerHTML = `
      <div>
        <div class="list-row-title ${bad ? "movement-negative" : ""}">${escapeHtml(actionLabel(item.action))}</div>
        <div class="list-row-sub">${escapeHtml(item.detail || "")}${item.entity_id ? ` (${escapeHtml(item.entity)} ${escapeHtml(item.entity_id)})` : ""}</div>
      </div>
      <div class="list-row-amount">
        <div>${escapeHtml(item.username || "-")}</div>
        <div class="card-sku">${formatDateTime(item.created_at)}</div>
      </div>
    `;
    listEl.appendChild(row);
  }
}

let timer;
searchEl.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(load, 300);
});
userEl.addEventListener("change", load);
actionEl.addEventListener("change", load);
load();
