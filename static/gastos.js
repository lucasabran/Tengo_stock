const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const exportLink = document.getElementById("export-link");
const fabAdd = document.getElementById("fab-add");
const dialog = document.getElementById("form-dialog");
const form = document.getElementById("expense-form");
const formTitle = document.getElementById("form-title");
const formError = document.getElementById("form-error");
const cancelBtn = document.getElementById("form-cancel");

const fCategory = document.getElementById("f-category");
const fAmount = document.getElementById("f-amount");
const fDate = document.getElementById("f-date");
const fVendor = document.getElementById("f-vendor");
const fNote = document.getElementById("f-note");

let editingId = null;

function render(expenses) {
  listEl.innerHTML = "";
  if (!expenses.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay gastos cargados.</div>';
    return;
  }
  for (const e of expenses) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-name">${escapeHtml(e.category)}</div>
          <div class="card-sku">${formatDate(e.expense_date)}${e.vendor ? " &middot; " + escapeHtml(e.vendor) : ""}</div>
        </div>
        <div class="card-price">${money(e.amount)}</div>
      </div>
      ${e.note ? `<div class="card-desc">${escapeHtml(e.note)}</div>` : ""}
      <div class="card-bottom">
        <div></div>
        <div class="card-actions">
          <button data-action="edit">Editar</button>
          <button data-action="delete">Eliminar</button>
        </div>
      </div>
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openEdit(e));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => removeExpense(e));
    listEl.appendChild(card);
  }
}

async function refresh() {
  const q = searchEl.value.trim();
  exportLink.href = q ? `/api/expenses/export.csv?q=${encodeURIComponent(q)}` : "/api/expenses/export.csv";
  const expenses = await fetchJSON(q ? `/api/expenses?q=${encodeURIComponent(q)}` : "/api/expenses");
  render(expenses);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});

function openCreate() {
  editingId = null;
  formTitle.textContent = "Nuevo gasto";
  form.reset();
  fDate.value = new Date().toISOString().slice(0, 10);
  hideError();
  dialog.showModal();
}

function openEdit(e) {
  editingId = e.id;
  formTitle.textContent = "Editar gasto";
  fCategory.value = e.category;
  fAmount.value = e.amount;
  fDate.value = e.expense_date;
  fVendor.value = e.vendor || "";
  fNote.value = e.note || "";
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
    category: fCategory.value,
    amount: parseFloat(fAmount.value),
    expense_date: fDate.value,
    vendor: fVendor.value.trim(),
    note: fNote.value.trim(),
  };

  try {
    if (editingId) {
      await fetchJSON(`/api/expenses/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJSON("/api/expenses", {
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
  toast(editingId ? "Gasto actualizado" : "Gasto registrado", "success");
  refresh();
});

async function removeExpense(e) {
  if (!(await confirmDialog(`Eliminar el gasto "${e.category}" de ${money(e.amount)}?`))) return;
  await fetchJSON(`/api/expenses/${e.id}`, { method: "DELETE" });
  toast("Gasto eliminado", "success");
  refresh();
}

refresh();
