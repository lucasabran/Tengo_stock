const LOW_STOCK_THRESHOLD = 3;

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const categoryFilterEl = document.getElementById("filter-category");
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
const fCategory = document.getElementById("f-category");
const categoryList = document.getElementById("category-list");
const fPrice = document.getElementById("f-price");
const fQuantity = document.getElementById("f-quantity");
const fDescription = document.getElementById("f-description");

const stockEntryDialog = document.getElementById("stock-entry-dialog");
const stockEntryForm = document.getElementById("stock-entry-form");
const stockEntryProduct = document.getElementById("stock-entry-product");
const stockEntryError = document.getElementById("stock-entry-error");
const stockEntryCancel = document.getElementById("stock-entry-cancel");
const seQuantity = document.getElementById("se-quantity");
const seReason = document.getElementById("se-reason");
const seNote = document.getElementById("se-note");

let editingSku = null;
let stockEntrySku = null;

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

async function fetchProducts(q = "", category = "") {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (category) params.set("category", category);
  return fetchJSON(`/api/products?${params.toString()}`);
}

function render(products) {
  listEl.innerHTML = "";
  if (products.length === 0) {
    listEl.innerHTML = '<div class="empty"><svg viewBox="0 0 24 24" width="40" height="40" aria-hidden="true"><path d="M3 7l9-4 9 4v10l-9 4-9-4V7z M3 7l9 4 9-4 M12 11v10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg><p>No hay productos cargados todavia.</p></div>';
    return;
  }
  for (const p of products) {
    const card = document.createElement("div");
    card.className = "card";
    const low = p.quantity <= LOW_STOCK_THRESHOLD;
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(p.name)}</div>
          <div class="card-sku">SKU: ${escapeHtml(p.sku)}${p.category ? ` &middot; ${escapeHtml(p.category)}` : ""}</div>
        </div>
        <div class="card-price">${money(p.price)}</div>
      </div>
      ${p.description ? `<div class="card-desc">${escapeHtml(p.description)}</div>` : ""}
      <div class="card-bottom">
        <div class="qty ${low ? "low" : ""}">Stock: ${p.quantity}</div>
        <div class="card-actions">
          <button data-action="minus">-1</button>
          <button data-action="plus">+1</button>
          <button data-action="load">Cargar stock</button>
          <button data-action="edit">Editar</button>
          <button data-action="delete">Eliminar</button>
        </div>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openEdit(p));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => removeProduct(p));
    card.querySelector('[data-action="plus"]').addEventListener("click", () => addStock(p.sku, 1));
    card.querySelector('[data-action="minus"]').addEventListener("click", () => addStock(p.sku, -1));
    card.querySelector('[data-action="load"]').addEventListener("click", () => openStockEntry(p));
    listEl.appendChild(card);
  }
}

async function refresh() {
  const products = await fetchProducts(searchEl.value.trim(), categoryFilterEl.value);
  render(products);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
categoryFilterEl.addEventListener("change", refresh);

function openCreate() {
  editingSku = null;
  formTitle.textContent = "Nuevo producto";
  form.reset();
  fSku.disabled = false;
  fCategory.value = "General";
  hideError();
  dialog.showModal();
}

function openEdit(p) {
  editingSku = p.sku;
  formTitle.textContent = "Editar producto";
  fSku.value = p.sku;
  fSku.disabled = true;
  fName.value = p.name;
  fCategory.value = p.category || "";
  fPrice.value = p.price;
  fQuantity.value = p.quantity;
  fDescription.value = p.description || "";
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
    sku: fSku.value.trim(),
    name: fName.value.trim(),
    category: fCategory.value.trim(),
    price: parseFloat(fPrice.value),
    quantity: parseInt(fQuantity.value, 10),
    description: fDescription.value.trim(),
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

  dialog.close();
  toast(editingSku ? "Producto actualizado" : "Producto creado", "success");
  loadCategories();
  refresh();
});

async function addStock(sku, amount) {
  await fetchJSON(`/api/products/${encodeURIComponent(sku)}/add-stock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });
  refresh();
}

function openStockEntry(p) {
  stockEntrySku = p.sku;
  stockEntryProduct.textContent = `${p.name} (SKU: ${p.sku})`;
  stockEntryForm.reset();
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

  const originalText = btnImport.textContent;
  btnImport.disabled = true;
  btnImport.textContent = "Importando...";

  try {
    const data = await fetchJSON("/api/products/import", { method: "POST", body: formData });
    let msg = `Listo: ${data.created} productos nuevos, ${data.updated} actualizados.`;
    if (data.errors.length) {
      msg += `\n\n${data.errors.length} fila(s) con problemas:\n` + data.errors.slice(0, 10).join("\n");
      toast(msg, "error", 9000);
    } else {
      toast(msg, "success", 6000);
    }
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

loadCategories().then(refresh);
