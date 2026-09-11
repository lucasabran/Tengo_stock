const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const channelEl = document.getElementById("filter-channel");
const fromEl = document.getElementById("filter-from");
const toEl = document.getElementById("filter-to");
const exportLink = document.getElementById("export-link");

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
        <div class="list-row-sub">${escapeHtml(s.customer_name || "Sin cliente")} &middot; ${formatDateTime(s.created_at)}</div>
      </div>
      <div class="list-row-amount">${money(s.total)}</div>
    `;
    listEl.appendChild(row);
  }
}

async function refresh() {
  const params = new URLSearchParams();
  if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
  if (channelEl.value) params.set("channel_id", channelEl.value);
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
fromEl.addEventListener("change", refresh);
toEl.addEventListener("change", refresh);

loadChannels().then(refresh);
