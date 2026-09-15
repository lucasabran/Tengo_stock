const listEl = document.getElementById("list");

const REASON_LABELS = {
  no_funciona: "No funciona",
  arrepentimiento: "Arrepentimiento",
  cambio: "Cambio",
  error_de_carga: "Error de carga",
  otro: "Otro",
};

async function refresh() {
  const returns = await fetchJSON("/api/returns");
  listEl.innerHTML = "";
  if (!returns.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay devoluciones registradas.</div>';
    return;
  }
  for (const r of returns) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/ventas/${r.sale_id}`;
    row.innerHTML = `
      <div>
        <div class="list-row-title">Venta ${escapeHtml(r.sale_number)}</div>
        <div class="list-row-sub">${escapeHtml(REASON_LABELS[r.reason] || r.reason || "Sin motivo")} &middot; ${formatDateTime(r.created_at)}</div>
      </div>
    `;
    listEl.appendChild(row);
  }
}

refresh();
