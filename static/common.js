function money(n) {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS" }).format(n || 0);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  if (!res.ok) {
    const err = new Error((data && data.error) || `Error ${res.status}`);
    err.data = data;
    err.status = res.status;
    throw err;
  }
  return data;
}

function errorMessage(err) {
  let msg = err.message || "Ocurrio un error";
  if (err.data && Array.isArray(err.data.details) && err.data.details.length) {
    msg += "\n\n" + err.data.details.join("\n");
  }
  return msg;
}

function ensureToastContainer() {
  let el = document.getElementById("toast-container");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-container";
    document.body.appendChild(el);
  }
  return el;
}

function toast(message, type = "info", timeout = 4000) {
  const container = ensureToastContainer();
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("toast-show"));
  setTimeout(() => {
    el.classList.remove("toast-show");
    setTimeout(() => el.remove(), 200);
  }, timeout);
}

function ensureConfirmDialog() {
  let dialog = document.getElementById("confirm-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "confirm-dialog";
    dialog.innerHTML = `
      <form method="dialog" class="confirm-dialog-form">
        <p id="confirm-dialog-message"></p>
        <div class="form-actions">
          <button type="button" id="confirm-dialog-cancel">Cancelar</button>
          <button type="submit" id="confirm-dialog-ok" value="ok">Confirmar</button>
        </div>
      </form>
    `;
    document.body.appendChild(dialog);
    dialog.querySelector("#confirm-dialog-cancel").addEventListener("click", () => dialog.close());
  }
  return dialog;
}

function confirmDialog(message) {
  const dialog = ensureConfirmDialog();
  dialog.querySelector("#confirm-dialog-message").textContent = message;
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "ok"),
      { once: true }
    );
  });
}
