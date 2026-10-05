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
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `
      <a class="list-row-link" href="/ventas/${r.sale_id}">
        <div class="list-row-title">Venta ${escapeHtml(r.sale_number)}</div>
        <div class="list-row-sub">${escapeHtml(REASON_LABELS[r.reason] || r.reason || "Sin motivo")} &middot; ${formatDateTime(r.created_at)}</div>
      </a>
      ${can("returns.delete") ? '<button type="button" class="btn-danger" data-act="delete">Eliminar</button>' : ""}
    `;
    const del = row.querySelector('[data-act="delete"]');
    if (del) {
      del.addEventListener("click", async () => {
        if (!(await confirmDialog("Eliminar esta devolucion? El stock devuelto vuelve a descontarse. No se puede deshacer."))) return;
        try {
          await fetchJSON(`/api/returns/${r.id}`, { method: "DELETE" });
        } catch (err) {
          toast(errorMessage(err), "error", 8000);
          return;
        }
        toast("Devolucion eliminada", "success");
        refresh();
      });
    }
    listEl.appendChild(row);
  }
}

refresh();
