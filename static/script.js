const LOW_STOCK_THRESHOLD = 3;

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const officeFilterEl = document.getElementById("filter-office");
const categoryFilterEl = document.getElementById("filter-category");
const conditionFilterEl = document.getElementById("filter-condition");
const sortEl = document.getElementById("filter-sort");
const fabAdd = document.getElementById("fab-add");
const btnImport = document.getElementById("btn-import");
const importFile = document.getElementById("import-file");
const dialog = document.getElementById("form-dialog");
const form = document.getElementById("product-form");
const formTitle = document.getElementById("form-title");
const formError = document.getElementById("form-error");
const cancelBtn = document.getElementById("form-cancel");

const fSku = document.getElementById("f-sku");
const fName = document.getElementById("f-name");
const fCondition = document.getElementById("f-condition");
const fCategory = document.getElementById("f-category");
const categoryList = document.getElementById("category-list");
const fPrice = document.getElementById("f-price");
const fPriceWholesale = document.getElementById("f-price-wholesale");
const fCurrency = document.getElementById("f-currency");
const fOffice = document.getElementById("f-office");
const fQuantity = document.getElementById("f-quantity");
const fDescription = document.getElementById("f-description");
const fMinStock = document.getElementById("f-min-stock");
const fPhoto = document.getElementById("f-photo");
const photoPreview = document.getElementById("photo-preview");
const photoRemove = document.getElementById("photo-remove");
const btnRenameSku = document.getElementById("btn-rename-sku");

let removePhoto = false;

const stockEntryDialog = document.getElementById("stock-entry-dialog");
const stockEntryForm = document.getElementById("stock-entry-form");
const stockEntryProduct = document.getElementById("stock-entry-product");
const stockEntryError = document.getElementById("stock-entry-error");
const stockEntryCancel = document.getElementById("stock-entry-cancel");
const seOffice = document.getElementById("se-office");
const seQuantity = document.getElementById("se-quantity");
const seReason = document.getElementById("se-reason");
const seNote = document.getElementById("se-note");

const transferDialog = document.getElementById("transfer-dialog");
const transferForm = document.getElementById("transfer-form");
const trFrom = document.getElementById("tr-from");
const trTo = document.getElementById("tr-to");
const trQuantity = document.getElementById("tr-quantity");
const trNote = document.getElementById("tr-note");
const trAvailable = document.getElementById("tr-available");
const transferError = document.getElementById("transfer-error");

const renameDialog = document.getElementById("rename-dialog");
const renameForm = document.getElementById("rename-form");
const renameError = document.getElementById("rename-error");

let editingSku = null;
let stockEntrySku = null;
let transferProduct = null;
let renameSku = null;
let offices = [];
let products = [];

const fixedOffice = window.USER_OFFICE; // usuarios con una oficina asignada solo operan en ella

function activeOffices() {
  return offices.filter((o) => o.active);
}

function officeName(id) {
  const o = offices.find((x) => x.id === Number(id));
  return o ? o.name : "";
}

function currentOfficeId() {
  if (fixedOffice) return fixedOffice;
  return officeFilterEl.value ? Number(officeFilterEl.value) : null;
}

function fillOfficeSelect(select, selectedId) {
  select.innerHTML = activeOffices().map((o) => `<option value="${o.id}">${escapeHtml(o.name)}</option>`).join("");
  const fallback = selectedId || fixedOffice || (activeOffices()[0] && activeOffices()[0].id);
  if (fallback) select.value = String(fallback);
}

async function loadOffices() {
  offices = await fetchJSON("/api/offices");
  officeFilterEl.innerHTML = "";
  if (fixedOffice) {
    officeFilterEl.innerHTML = `<option value="${fixedOffice}">${escapeHtml(officeName(fixedOffice))}</option>`;
    officeFilterEl.disabled = true;
  } else {
    officeFilterEl.innerHTML =
      '<option value="">Todas las oficinas (consolidado)</option>' +
      activeOffices().map((o) => `<option value="${o.id}">${escapeHtml(o.name)}</option>`).join("");
  }
  if (fixedOffice) {
    document.getElementById("f-office-label").classList.add("hidden");
    document.getElementById("se-office-label").classList.add("hidden");
  }
}

async function loadCategories() {
  const categories = await fetchJSON("/api/categories");
  const currentFilter = categoryFilterEl.value;
  categoryFilterEl.innerHTML = '<option value="">Todas las categorias</option>';
  categoryList.innerHTML = "";
  for (const c of categories) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    categoryFilterEl.appendChild(opt);

    const dataOpt = document.createElement("option");
    dataOpt.value = c;
    categoryList.appendChild(dataOpt);
  }
  categoryFilterEl.value = currentFilter;
}

async function fetchProducts() {
  const params = new URLSearchParams();
  if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
  if (categoryFilterEl.value) params.set("category", categoryFilterEl.value);
  if (conditionFilterEl.value) params.set("condition", conditionFilterEl.value);
  if (currentOfficeId()) params.set("office_id", currentOfficeId());
  params.set("sort", sortEl.value);
  return fetchJSON(`/api/products?${params.toString()}`);
}

function stockLine(p) {
  const viewing = currentOfficeId();
  let text = `Stock: ${p.quantity}`;
  if (viewing) text += ` en ${escapeHtml(officeName(viewing))}`;
  const min = p.min_stock > 0 ? ` <span class="card-sku">(minimo ${p.min_stock})</span>` : "";
  let detail = "";
  if (!viewing && p.stock_by_office && activeOffices().length > 1) {
    const parts = p.stock_by_office.map((s) => `${escapeHtml(s.office_name)} ${s.quantity}`);
    if (parts.length) detail = `<div class="card-sku">${parts.join(" &middot; ")}</div>`;
  }
  return { text: text + min, detail };
}

function render(list) {
  products = list;
  listEl.innerHTML = "";
  if (list.length === 0) {
    listEl.innerHTML = '<div class="empty"><svg viewBox="0 0 24 24" width="40" height="40" aria-hidden="true"><path d="M3 7l9-4 9 4v10l-9 4-9-4V7z M3 7l9 4 9-4 M12 11v10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg><p>No hay productos para mostrar.</p></div>';
    return;
  }
  const canEdit = can("stock.edit");
  const viewing = currentOfficeId();
  for (const p of list) {
    const card = document.createElement("div");
    card.className = "card";
    const low = p.quantity <= (p.min_stock > 0 ? p.min_stock : LOW_STOCK_THRESHOLD);
    const s = stockLine(p);
    const badge = p.condition && p.condition !== "Nuevo" ? `<span class="badge badge-cond">${escapeHtml(p.condition)}</span>` : "";
    card.innerHTML = `
      <div class="card-top">
        ${p.photo_url ? `<img class="card-photo" src="${escapeHtml(p.photo_url)}" alt="" loading="lazy">` : ""}
        <div class="card-info">
          <div class="card-name">${escapeHtml(p.name)} ${badge}</div>
          <div class="card-sku">SKU: ${escapeHtml(p.sku)}${p.category ? ` &middot; ${escapeHtml(p.category)}` : ""}</div>
        </div>
        <div class="card-price">${money(p.price, p.currency)}${p.price_wholesale > 0 ? `<div class="card-sku">Mayorista ${money(p.price_wholesale, p.currency)}</div>` : ""}</div>
      </div>
      ${p.description ? `<div class="card-desc">${escapeHtml(p.description)}</div>` : ""}
      <div class="card-bottom">
        <div>
          <div class="qty ${low ? "low" : ""}">${s.text}</div>
          ${s.detail}
        </div>
        <div class="card-actions">
          ${canEdit && viewing ? '<button data-action="minus">-1</button><button data-action="plus">+1</button>' : ""}
          ${canEdit ? '<button data-action="load">Cargar stock</button>' : ""}
          ${can("stock.transfer") && activeOffices().length > 1 ? '<button data-action="transfer">Transferir</button>' : ""}
          ${canEdit ? '<button data-action="edit">Editar</button>' : ""}
          ${can("stock.delete") ? '<button data-action="delete">Eliminar</button>' : ""}
        </div>
      </div>
    `;
    const on = (action, fn) => {
      const el = card.querySelector(`[data-action="${action}"]`);
      if (el) el.addEventListener("click", fn);
    };
    on("edit", () => openEdit(p));
    on("delete", () => removeProduct(p));
    on("plus", () => addStock(p.sku, 1));
    on("minus", () => addStock(p.sku, -1));
    on("load", () => openStockEntry(p));
    on("transfer", () => openTransfer(p));
    listEl.appendChild(card);
  }
}

async function refresh() {
  render(await fetchProducts());
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
for (const el of [officeFilterEl, categoryFilterEl, conditionFilterEl, sortEl]) el.addEventListener("change", refresh);

// ---------------------------------------------------------------- producto
function officeQuantity(p, officeId) {
  if (fixedOffice) return p.quantity;
  const row = (p.stock_by_office || []).find((s) => s.office_id === Number(officeId));
  return row ? row.quantity : 0;
}

function openCreate() {
  editingSku = null;
  formTitle.textContent = "Nuevo producto";
  form.reset();
  fSku.disabled = false;
  btnRenameSku.classList.add("hidden");
  fCondition.value = "Nuevo";
  fCategory.value = "General";
  fCurrency.value = "ARS";
  fPriceWholesale.value = 0;
  fMinStock.value = 0;
  fillOfficeSelect(fOffice, currentOfficeId());
  setPhotoPreview("");
  hideError();
  dialog.showModal();
}

function openEdit(p) {
  editingSku = p.sku;
  formTitle.textContent = "Editar producto";
  fSku.value = p.sku;
  fSku.disabled = true;
  btnRenameSku.classList.toggle("hidden", !can("stock.rename"));
  fName.value = p.name;
  fCondition.value = p.condition || "Nuevo";
  fCategory.value = p.category || "";
  fCurrency.value = p.currency || "ARS";
  fPrice.value = p.price;
  fPriceWholesale.value = p.price_wholesale || 0;
  fillOfficeSelect(fOffice, currentOfficeId());
  fQuantity.value = officeQuantity(p, fOffice.value);
  fDescription.value = p.description || "";
  fMinStock.value = p.min_stock || 0;
  setPhotoPreview(p.photo_url || "");
  hideError();
  dialog.showModal();
}

// Al cambiar de oficina dentro del formulario de edicion se muestra el stock de esa oficina
fOffice.addEventListener("change", () => {
  if (!editingSku) return;
  const p = products.find((x) => x.sku === editingSku);
  if (p) fQuantity.value = officeQuantity(p, fOffice.value);
});

function setPhotoPreview(url) {
  removePhoto = false;
  fPhoto.value = "";
  if (url) {
    photoPreview.src = url;
    photoPreview.classList.remove("hidden");
    photoRemove.classList.remove("hidden");
  } else {
    photoPreview.removeAttribute("src");
    photoPreview.classList.add("hidden");
    photoRemove.classList.add("hidden");
  }
}

fPhoto.addEventListener("change", () => {
  const file = fPhoto.files[0];
  removePhoto = false;
  if (!file) return;
  photoPreview.src = URL.createObjectURL(file);
  photoPreview.classList.remove("hidden");
  photoRemove.classList.remove("hidden");
});

photoRemove.addEventListener("click", () => {
  fPhoto.value = "";
  photoPreview.removeAttribute("src");
  photoPreview.classList.add("hidden");
  photoRemove.classList.add("hidden");
  removePhoto = true;
});

// Reduce la foto en el navegador (max 1200px, JPEG) antes de subirla
function downscaleImage(file, maxSide = 1200, quality = 0.82) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("No se pudo procesar la foto"))), "image/jpeg", quality);
    };
    img.onerror = () => reject(new Error("No se pudo leer la foto"));
    img.src = url;
  });
}

async function syncPhoto(sku) {
  const file = fPhoto.files[0];
  if (file) {
    const blob = await downscaleImage(file);
    const fd = new FormData();
    fd.append("photo", blob, "foto.jpg");
    await fetchJSON(`/api/products/${encodeURIComponent(sku)}/photo`, { method: "POST", body: fd });
  } else if (removePhoto && editingSku) {
    await fetchJSON(`/api/products/${encodeURIComponent(sku)}/photo`, { method: "DELETE" });
  }
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
    sku: fSku.value.trim(),
    name: fName.value.trim(),
    condition: fCondition.value,
    category: fCategory.value.trim(),
    currency: fCurrency.value,
    price: parseFloat(fPrice.value),
    price_wholesale: parseFloat(fPriceWholesale.value) || 0,
    quantity: parseInt(fQuantity.value, 10),
    office_id: Number(fOffice.value) || null,
    description: fDescription.value.trim(),
    min_stock: parseInt(fMinStock.value, 10) || 0,
  };

  try {
    if (editingSku) {
      await fetchJSON(`/api/products/${encodeURIComponent(editingSku)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJSON("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
  } catch (err) {
    showError(errorMessage(err));
    return;
  }

  try {
    await syncPhoto(payload.sku);
  } catch (err) {
    toast("El producto se guardo pero la foto no: " + errorMessage(err), "error", 7000);
  }

  dialog.close();
  toast(editingSku ? "Producto actualizado" : "Producto creado", "success");
  loadCategories();
  refresh();
});

// ---------------------------------------------------------------- cambiar SKU
btnRenameSku.addEventListener("click", () => {
  renameSku = editingSku;
  document.getElementById("rn-old").value = editingSku;
  document.getElementById("rn-new").value = "";
  renameError.classList.add("hidden");
  dialog.close();
  renameDialog.showModal();
});
document.getElementById("rename-cancel").addEventListener("click", () => renameDialog.close());

renameForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  renameError.classList.add("hidden");
  try {
    await fetchJSON(`/api/products/${encodeURIComponent(renameSku)}/sku`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_sku: document.getElementById("rn-new").value.trim() }),
    });
  } catch (err) {
    renameError.textContent = errorMessage(err);
    renameError.classList.remove("hidden");
    return;
  }
  renameDialog.close();
  toast("SKU cambiado", "success");
  refresh();
});

// ---------------------------------------------------------------- stock
async function addStock(sku, amount) {
  try {
    await fetchJSON(`/api/products/${encodeURIComponent(sku)}/add-stock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, office_id: currentOfficeId() }),
    });
  } catch (err) {
    toast(errorMessage(err), "error");
    return;
  }
  refresh();
}

function openStockEntry(p) {
  stockEntrySku = p.sku;
  stockEntryProduct.textContent = `${p.name} (SKU: ${p.sku})`;
  stockEntryForm.reset();
  fillOfficeSelect(seOffice, currentOfficeId());
  stockEntryError.classList.add("hidden");
  stockEntryDialog.showModal();
}

stockEntryCancel.addEventListener("click", () => stockEntryDialog.close());

stockEntryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  stockEntryError.classList.add("hidden");
  try {
    await fetchJSON(`/api/products/${encodeURIComponent(stockEntrySku)}/add-stock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: parseInt(seQuantity.value, 10),
        reason: seReason.value,
        note: seNote.value.trim(),
        office_id: Number(seOffice.value) || null,
      }),
    });
  } catch (err) {
    stockEntryError.textContent = errorMessage(err);
    stockEntryError.classList.remove("hidden");
    return;
  }
  stockEntryDialog.close();
  toast("Stock cargado", "success");
  refresh();
});

// ---------------------------------------------------------------- transferencias
function updateTransferAvailable() {
  if (!transferProduct) return;
  const row = (transferProduct.stock_by_office || []).find((s) => s.office_id === Number(trFrom.value));
  trAvailable.textContent = `Disponible en ${officeName(trFrom.value)}: ${row ? row.quantity : 0}`;
}

function openTransfer(p) {
  transferProduct = p;
  document.getElementById("transfer-product").textContent = `${p.name} (SKU: ${p.sku})`;
  transferForm.reset();
  fillOfficeSelect(trFrom, currentOfficeId());
  fillOfficeSelect(trTo, null);
  const other = activeOffices().find((o) => o.id !== Number(trFrom.value));
  if (other) trTo.value = String(other.id);
  updateTransferAvailable();
  transferError.classList.add("hidden");
  transferDialog.showModal();
}
trFrom.addEventListener("change", updateTransferAvailable);
document.getElementById("transfer-cancel").addEventListener("click", () => transferDialog.close());

transferForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  transferError.classList.add("hidden");
  try {
    await fetchJSON("/api/stock-transfers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sku: transferProduct.sku,
        from_office_id: Number(trFrom.value),
        to_office_id: Number(trTo.value),
        quantity: parseInt(trQuantity.value, 10),
        note: trNote.value.trim(),
      }),
    });
  } catch (err) {
    transferError.textContent = errorMessage(err);
    transferError.classList.remove("hidden");
    return;
  }
  transferDialog.close();
  toast("Transferencia realizada", "success");
  refresh();
});

// ---------------------------------------------------------------- eliminar e importar
async function removeProduct(p) {
  if (!(await confirmDialog(`Eliminar ${p.name} (SKU ${p.sku})?`))) return;
  try {
    await fetchJSON(`/api/products/${encodeURIComponent(p.sku)}`, { method: "DELETE" });
  } catch (err) {
    toast(errorMessage(err), "error");
    return;
  }
  toast("Producto eliminado", "success");
  refresh();
}

btnImport.addEventListener("click", () => importFile.click());

importFile.addEventListener("change", async () => {
  if (!importFile.files.length) return;
  const formData = new FormData();
  formData.append("file", importFile.files[0]);
  if (currentOfficeId()) formData.append("office_id", currentOfficeId());

  const originalText = btnImport.textContent;
  btnImport.disabled = true;
  btnImport.textContent = "Importando...";

  try {
    const data = await fetchJSON("/api/products/import", { method: "POST", body: formData });
    showImportResult(
      "Importacion de productos",
      {
        created: data.created,
        updated: data.updated,
        error_count: data.errors.length,
        errors: data.errors.slice(0, 40),
        more_errors: Math.max(data.errors.length - 40, 0),
      },
      "productos nuevos"
    );
    loadCategories();
    refresh();
  } catch (err) {
    toast("Error al importar: " + errorMessage(err), "error", 9000);
  } finally {
    btnImport.disabled = false;
    btnImport.textContent = originalText;
    importFile.value = "";
  }
});

if (can("stock.import")) {
  setupBulkImport({
    button: "btn-import-entries",
    fileInput: "import-entries-file",
    url: "/api/stock-entries/import",
    title: "Ingresos de stock",
    noun: "movimientos de stock",
    onDone: refresh,
  });
}

// Mostrar solo lo que el rol permite
if (!can("stock.edit")) fabAdd.classList.add("hidden");
if (!can("stock.import")) document.querySelectorAll(".import-row").forEach((el) => el.classList.add("hidden"));

loadOffices().then(() => Promise.all([loadCategories(), refresh()]));
