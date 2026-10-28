const listEl = document.getElementById("list");
const dialog = document.getElementById("office-dialog");
const form = document.getElementById("office-form");
const errorEl = document.getElementById("office-error");
let editingId = null;

function render(offices) {
  listEl.innerHTML = "";
  for (const o of offices) {
    const row = document.createElement("div");
    row.className = "list-row" + (o.active ? "" : " user-inactive");
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(o.name)} ${o.active ? "" : '<span class="badge badge-off">Desactivada</span>'}</div>
        <div class="list-row-sub">${o.products} producto(s) con stock &middot; ${o.units} unidad(es)</div>
      </div>
      <div class="row-actions"><button type="button" class="btn-secondary">Editar</button></div>
    `;
    row.querySelector("button").addEventListener("click", () => openOffice(o));
    listEl.appendChild(row);
  }
}

async function refresh() {
  render(await fetchJSON("/api/offices"));
}

function openOffice(o) {
  editingId = o ? o.id : null;
  errorEl.classList.add("hidden");
  document.getElementById("office-title").textContent = o ? `Editar ${o.name}` : "Nueva oficina";
  document.getElementById("o-name").value = o ? o.name : "";
  document.getElementById("o-active-label").classList.toggle("hidden", !o);
  document.getElementById("o-active").checked = o ? o.active : true;
  dialog.showModal();
}

document.getElementById("btn-new-office").addEventListener("click", () => openOffice(null));
document.getElementById("office-cancel").addEventListener("click", () => dialog.close());

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.classList.add("hidden");
  const body = { name: document.getElementById("o-name").value.trim() };
  if (editingId) body.active = document.getElementById("o-active").checked;
  try {
    await fetchJSON(editingId ? `/api/offices/${editingId}` : "/api/offices", {
      method: editingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    errorEl.textContent = errorMessage(err);
    errorEl.classList.remove("hidden");
    return;
  }
  dialog.close();
  toast("Oficina guardada", "success");
  refresh();
});

refresh();
