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
const fAddress = document.getElementById("f-address");
const fCity = document.getElementById("f-city");
const fProvince = document.getElementById("f-province");
const fOffice = document.getElementById("f-office");
const fType = document.getElementById("f-type");
const officeFilterEl = document.getElementById("filter-office");
const typeFilterEl = document.getElementById("filter-type");
const productFilterEl = document.getElementById("filter-product");
const exportLink = document.getElementById("export-link");
let offices = [];

async function loadOffices() {
  offices = (await fetchJSON("/api/offices")).filter((o) => o.active);
  for (const o of offices) {
    officeFilterEl.insertAdjacentHTML("beforeend", `<option value="${o.id}">${escapeHtml(o.name)}</option>`);
    fOffice.insertAdjacentHTML("beforeend", `<option value="${o.id}">${escapeHtml(o.name)}</option>`);
  }
}

function filterParams() {
  const params = new URLSearchParams();
  if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
  if (officeFilterEl.value) params.set("office_id", officeFilterEl.value);
  if (typeFilterEl.value) params.set("customer_type", typeFilterEl.value);
  if (productFilterEl.value.trim()) params.set("product", productFilterEl.value.trim());
  return params.toString();
}

async function showPurchases(c) {
  document.getElementById("purchases-title").textContent = `Compras de ${c.name}`;
  const body = document.getElementById("purchases-body");
  body.innerHTML = "<p class=\"card-sku\">Cargando...</p>";
  document.getElementById("purchases-dialog").showModal();
  const rows = await fetchJSON(`/api/customers/${c.id}/purchases`);
  if (!rows.length) {
    body.innerHTML = "<p class=\"card-sku\">Todavia no compro ningun producto.</p>";
    return;
  }
  body.innerHTML = `<table class="purchases-table"><thead><tr><th>Producto</th><th>Cant.</th><th>Veces</th><th>Total</th><th>Ultima</th></tr></thead><tbody>${rows
    .map((r) => `<tr><td>${escapeHtml(r.product_name)}<div class="card-sku">SKU ${escapeHtml(r.sku)}</div></td><td>${r.quantity}</td><td>${r.purchases}</td><td>${money(r.total, r.currency)}</td><td>${formatDate((r.last_date || "").slice(0, 10))}</td></tr>`)
    .join("")}</tbody></table>`;
}

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
    const contact = [c.phone, c.email].filter(Boolean).map(escapeHtml).join(" &middot; ");
    const place = [c.address, c.city, c.province].filter(Boolean).map(escapeHtml).join(", ");
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(c.name)} ${c.customer_type === "mayorista" ? '<span class="badge badge-type">Mayorista</span>' : ""} ${c.office_name ? `<span class="badge">${escapeHtml(c.office_name)}</span>` : ""}</div>
          ${contact ? `<div class="card-sku">${contact}</div>` : ""}
          ${place ? `<div class="card-sku">${place}</div>` : ""}
        </div>
        <div class="card-price">${c.purchase_count > 0 ? money(c.total_spent) : ""}</div>
      </div>
      ${c.purchase_count > 0 ? `<div class="card-desc">${c.purchase_count} compra(s)</div>` : ""}
      ${c.note ? `<div class="card-desc">${escapeHtml(c.note)}</div>` : ""}
      <div class="card-bottom">
        <div></div>
        <div class="card-actions">
          <button data-action="purchases">Compras</button>
          ${can("customers.manage") ? '<button data-action="edit">Editar</button><button data-action="delete">Eliminar</button>' : ""}
        </div>
      </div>
    `;
    card.querySelector('[data-action="purchases"]').addEventListener("click", () => showPurchases(c));
    const editBtn = card.querySelector('[data-action="edit"]');
    if (editBtn) editBtn.addEventListener("click", () => openEdit(c));
    const delBtn = card.querySelector('[data-action="delete"]');
    if (delBtn) delBtn.addEventListener("click", () => removeCustomer(c));
    listEl.appendChild(card);
  }
}

async function refresh() {
  exportLink.href = `/api/customers/export.csv?${filterParams()}`;
  render(await fetchJSON(`/api/customers?${filterParams()}`));
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
productFilterEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
officeFilterEl.addEventListener("change", refresh);
typeFilterEl.addEventListener("change", refresh);

function openCreate() {
  editingId = null;
  formTitle.textContent = "Nuevo cliente";
  form.reset();
  fOffice.value = "";
  fType.value = "minorista";
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
  fAddress.value = c.address || "";
  fCity.value = c.city || "";
  fProvince.value = c.province || "";
  fOffice.value = c.office_id ? String(c.office_id) : "";
  fType.value = c.customer_type || "minorista";
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
    address: fAddress.value.trim(),
    city: fCity.value.trim(),
    province: fProvince.value.trim(),
    office_id: fOffice.value || null,
    customer_type: fType.value,
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

loadOffices().then(refresh);
if (!can("customers.manage")) fabAdd.classList.add("hidden");
