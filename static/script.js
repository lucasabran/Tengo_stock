const LOW_STOCK_THRESHOLD = 3;

const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
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
const fPrice = document.getElementById("f-price");
const fQuantity = document.getElementById("f-quantity");
const fDescription = document.getElementById("f-description");

let editingSku = null;

function money(n) {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS" }).format(n);
}

async function fetchProducts(q = "") {
  const url = q ? `/api/products?q=${encodeURIComponent(q)}` : "/api/products";
  const res = await fetch(url);
  return res.json();
}

function render(products) {
  listEl.innerHTML = "";
  if (products.length === 0) {
    listEl.innerHTML = '<div class="empty">No hay productos cargados todavia.</div>';
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
          <div class="card-sku">SKU: ${escapeHtml(p.sku)}</div>
        </div>
        <div class="card-price">${money(p.price)}</div>
      </div>
      ${p.description ? `<div class="card-desc">${escapeHtml(p.description)}</div>` : ""}
      <div class="card-bottom">
        <div class="qty ${low ? "low" : ""}">Stock: ${p.quantity}</div>
        <div class="card-actions">
          <button data-action="minus">-1</button>
          <button data-action="plus">+1</button>
          <button data-action="edit">Editar</button>
          <button data-action="delete">Eliminar</button>
        </div>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openEdit(p));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => removeProduct(p));
    card.querySelector('[data-action="plus"]').addEventListener("click", () => addStock(p.sku, 1));
    card.querySelector('[data-action="minus"]').addEventListener("click", () => addStock(p.sku, -1));
    listEl.appendChild(card);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

async function refresh() {
  const products = await fetchProducts(searchEl.value.trim());
  render(products);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});

function openCreate() {
  editingSku = null;
  formTitle.textContent = "Nuevo producto";
  form.reset();
  fSku.disabled = false;
  hideError();
  dialog.showModal();
}

function openEdit(p) {
  editingSku = p.sku;
  formTitle.textContent = "Editar producto";
  fSku.value = p.sku;
  fSku.disabled = true;
  fName.value = p.name;
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
    price: parseFloat(fPrice.value),
    quantity: parseInt(fQuantity.value, 10),
    description: fDescription.value.trim(),
  };

  let res;
  if (editingSku) {
    res = await fetch(`/api/products/${encodeURIComponent(editingSku)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } else {
    res = await fetch("/api/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    showError(data.error || "Ocurrio un error");
    return;
  }

  dialog.close();
  refresh();
});

async function addStock(sku, amount) {
  await fetch(`/api/products/${encodeURIComponent(sku)}/add-stock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });
  refresh();
}

async function removeProduct(p) {
  if (!confirm(`Eliminar ${p.name} (SKU ${p.sku})?`)) return;
  await fetch(`/api/products/${encodeURIComponent(p.sku)}`, { method: "DELETE" });
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
    const res = await fetch("/api/products/import", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Ocurrio un error al importar");
    } else {
      let msg = `Listo: ${data.created} productos nuevos, ${data.updated} actualizados.`;
      if (data.errors.length) {
        msg += `\n\n${data.errors.length} fila(s) con problemas:\n` + data.errors.slice(0, 10).join("\n");
      }
      alert(msg);
      refresh();
    }
  } catch (err) {
    alert("Error al importar: " + err.message);
  } finally {
    btnImport.disabled = false;
    btnImport.textContent = originalText;
    importFile.value = "";
  }
});

refresh();
