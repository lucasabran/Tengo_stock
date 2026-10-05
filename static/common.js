function money(n, currency = "ARS") {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: currency === "USD" ? "USD" : "ARS" }).format(n || 0);
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
  if (res.status === 401) {
    window.location.href = "/login";
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

function can(perm) {
  return (window.PERMS || []).includes(perm);
}

function ensureResultDialog() {
  let dialog = document.getElementById("import-result-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "import-result-dialog";
    dialog.innerHTML = `
      <form method="dialog" class="confirm-dialog-form">
        <h2 id="import-result-title"></h2>
        <div id="import-result-body"></div>
        <div class="form-actions"><button type="submit" value="ok">Cerrar</button></div>
      </form>
    `;
    document.body.appendChild(dialog);
  }
  return dialog;
}

function showImportResult(title, data, noun) {
  const dialog = ensureResultDialog();
  dialog.querySelector("#import-result-title").textContent = title;
  let html = `<p class="import-ok">Se cargaron <strong>${data.created}</strong> ${noun}.</p>`;
  if (data.created_channels && data.created_channels.length) {
    html += `<p class="card-sku">Canales nuevos creados: ${data.created_channels.map(escapeHtml).join(", ")}</p>`;
  }
  if (data.created_customers && data.created_customers.length) {
    html += `<p class="card-sku">Clientes nuevos creados: ${data.created_customers.length}</p>`;
  }
  if (data.error_count) {
    html += `<p class="import-bad"><strong>${data.error_count}</strong> con problemas (esas NO se cargaron):</p><ul class="import-errors">`;
    html += data.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("");
    if (data.more_errors) html += `<li>... y ${data.more_errors} mas</li>`;
    html += "</ul><p class=\"card-sku\">Corregi esas filas en el Excel y volve a importar solo esas.</p>";
  }
  dialog.querySelector("#import-result-body").innerHTML = html;
  dialog.showModal();
}

// Conecta un boton + input file a un endpoint de importacion masiva
function setupBulkImport({ button, fileInput, url, title, noun, extraFields, onDone }) {
  const btn = document.getElementById(button);
  const input = document.getElementById(fileInput);
  if (!btn || !input) return;
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    fd.append("file", input.files[0]);
    if (extraFields) for (const [k, v] of Object.entries(extraFields())) fd.append(k, v);
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Importando...";
    try {
      const data = await fetchJSON(url, { method: "POST", body: fd });
      showImportResult(title, data, noun);
      if (onDone) onDone(data);
    } catch (err) {
      toast("Error al importar: " + errorMessage(err), "error", 9000);
    } finally {
      btn.disabled = false;
      btn.textContent = original;
      input.value = "";
    }
  });
}
