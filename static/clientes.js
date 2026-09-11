const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const fabAdd = document.getElementById("fab-add");
const dialog = document.getElementById("form-dialog");
const form = document.getElementById("customer-form");
const formTitle = document.getElementById("form-title");
const formError = document.getElementById("form-error");
const cancelBtn = document.getElementById("form-cancel");

const fName = document.getElementById("f-name");
const fPhone = document.getElementById("f-phone");
const fEmail = document.getElementById("f-email");
const fDoc = document.getElementById("f-doc");
const fNote = document.getElementById("f-note");

let editingId = null;

function render(customers) {
  listEl.innerHTML = "";
  if (!customers.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay clientes cargados.</div>';
    return;
  }
  for (const c of customers) {
    const card = document.createElement("div");
    card.className = "card";
    const contact = [c.phone, c.email].filter(Boolean).join(" &middot; ");
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(c.name)}</div>
          ${contact ? `<div class="card-sku">${contact}</div>` : ""}
        </div>
        <div class="card-price">${c.purchase_count > 0 ? money(c.total_spent) : ""}</div>
      </div>
      ${c.purchase_count > 0 ? `<div class="card-desc">${c.purchase_count} compra(s)</div>` : ""}
      ${c.note ? `<div class="card-desc">${escapeHtml(c.note)}</div>` : ""}
      <div class="card-bottom">
        <div></div>
        <div class="card-actions">
          <button data-action="edit">Editar</button>
          <button data-action="delete">Eliminar</button>
        </div>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openEdit(c));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => removeCustomer(c));
    listEl.appendChild(card);
  }
}

async function refresh() {
  const q = searchEl.value.trim();
  const customers = await fetchJSON(q ? `/api/customers?q=${encodeURIComponent(q)}` : "/api/customers");
  render(customers);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});

function openCreate() {
  editingId = null;
  formTitle.textContent = "Nuevo cliente";
  form.reset();
  hideError();
  dialog.showModal();
}

function openEdit(c) {
  editingId = c.id;
  formTitle.textContent = "Editar cliente";
  fName.value = c.name;
  fPhone.value = c.phone || "";
  fEmail.value = c.email || "";
  fDoc.value = c.doc_number || "";
  fNote.value = c.note || "";
  hideError();
  dialog.showModal();
}

fabAdd.addEventListener("click", openCreate);
cancelBtn.addEventListener("click", () => dialog.close());

function showError(msg) {
  formError.textContent = msg;
  formError.classList.remove("hidden");
}
function hideError() {
  formError.classList.add("hidden");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const payload = {
    name: fName.value.trim(),
    phone: fPhone.value.trim(),
    email: fEmail.value.trim(),
    doc_number: fDoc.value.trim(),
    note: fNote.value.trim(),
  };

  try {
    if (editingId) {
      await fetchJSON(`/api/customers/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJSON("/api/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
  } catch (err) {
    showError(errorMessage(err));
    return;
  }

  dialog.close();
  toast(editingId ? "Cliente actualizado" : "Cliente creado", "success");
  refresh();
});

async function removeCustomer(c) {
  if (!(await confirmDialog(`Eliminar a ${c.name}?`))) return;
  try {
    await fetchJSON(`/api/customers/${c.id}`, { method: "DELETE" });
  } catch (err) {
    toast(errorMessage(err), "error");
    return;
  }
  toast("Cliente eliminado", "success");
  refresh();
}

refresh();
