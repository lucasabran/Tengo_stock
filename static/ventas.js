const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const channelEl = document.getElementById("filter-channel");
const fromEl = document.getElementById("filter-from");
const toEl = document.getElementById("filter-to");
const exportLink = document.getElementById("export-link");
const officeEl = document.getElementById("filter-office");
const typeEl = document.getElementById("filter-type");

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

async function loadChannels() {
  const channels = await fetchJSON("/api/channels");
  for (const c of channels) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    channelEl.appendChild(opt);
  }
}

function render(sales) {
  listEl.innerHTML = "";
  if (!sales.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay ventas registradas.</div>';
    return;
  }
  for (const s of sales) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/ventas/${s.id}`;
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(s.number)} &middot; ${escapeHtml(s.channel_name)}</div>
        <div class="list-row-sub">${escapeHtml(s.customer_name || "Sin cliente")} &middot; ${formatDateTime(s.created_at)}${s.office_name ? " &middot; " + escapeHtml(s.office_name) : ""}${s.sale_type === "mayorista" ? " &middot; Mayorista" : ""}${s.created_by ? " &middot; " + escapeHtml(s.created_by) : ""}</div>
      </div>
      <div class="list-row-amount">${money(s.total, s.currency)}</div>
    `;
    listEl.appendChild(row);
  }
}

async function refresh() {
  const params = new URLSearchParams();
  if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
  if (channelEl.value) params.set("channel_id", channelEl.value);
  if (officeEl.value) params.set("office_id", officeEl.value);
  if (typeEl.value) params.set("sale_type", typeEl.value);
  if (fromEl.value) params.set("date_from", fromEl.value);
  if (toEl.value) params.set("date_to", toEl.value);
  exportLink.href = `/api/sales/export.csv?${params.toString()}`;
  const sales = await fetchJSON(`/api/sales?${params.toString()}`);
  render(sales);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
channelEl.addEventListener("change", refresh);
officeEl.addEventListener("change", refresh);
typeEl.addEventListener("change", refresh);
fromEl.addEventListener("change", refresh);
toEl.addEventListener("change", refresh);

Promise.all([loadChannels(), loadOffices()]).then(refresh);

if (can("sales.import")) {
  setupBulkImport({
    button: "btn-import",
    fileInput: "import-file",
    url: "/api/sales/import",
    title: "Importacion de ventas",
    noun: "ventas",
    extraFields: () => ({ deduct_stock: document.getElementById("deduct-stock").checked ? "1" : "0" }),
    onDone: refresh,
  });
} else {
  document.getElementById("import-row").classList.add("hidden");
}
if (!can("sales.export")) exportLink.classList.add("hidden");
