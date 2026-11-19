const stateText = document.getElementById("state-text");
const officeSel = document.getElementById("tn-office");
const sinceInput = document.getElementById("tn-since");
const sinceLabel = document.getElementById("since-label");
const btnToggle = document.getElementById("btn-toggle");
const btnSync = document.getElementById("btn-sync");
const configError = document.getElementById("config-error");
let current = null;

const JSON_HEADERS = { "Content-Type": "application/json" };

function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

function renderState(s) {
  current = s;
  let html;
  if (!s.configured) {
    html = `<div class="card-name">Falta conectar la tienda</div>
      <div class="card-desc">En Render > Environment hay que cargar <b>TN_STORE_ID</b> y <b>TN_ACCESS_TOKEN</b> (la clave de la app de Tienda Nube). Despues de guardarlas el servidor se reinicia solo y se puede activar desde aca.</div>`;
  } else if (s.enabled) {
    html = `<div class="card-name">Sincronizacion activa <span class="badge badge-owner">Activa</span></div>
      <div class="card-desc">Se revisa la tienda cada 10 minutos.</div>
      <div class="card-desc">Importa pedidos pagados desde: <b>${fmtDate(s.since)}</b></div>
      <div class="card-desc">Ultima revision: <b>${s.last_sync ? fmtDate(s.last_sync) : "todavia no se hizo"}</b></div>
      <div class="card-desc"><b>${s.imported}</b> venta(s) importadas &middot; <b>${s.review}</b> para revisar</div>`;
  } else {
    html = `<div class="card-name">Sincronizacion apagada</div>
      <div class="card-desc">Al activarla solo se importan los pedidos pagados desde la fecha que elijas (por defecto, desde ese momento), para no descontar dos veces el stock que ya cargaron a mano.</div>`;
  }
  if (s.last_error) html += `<div class="error">Ultimo error: ${escapeHtml(s.last_error)}</div>`;
  stateText.innerHTML = html;

  officeSel.innerHTML = s.offices.map((o) => `<option value="${o.id}">${escapeHtml(o.name)}</option>`).join("");
  if (s.office_id) officeSel.value = s.office_id;
  sinceLabel.classList.toggle("hidden", s.enabled);
  btnToggle.textContent = s.enabled ? "Desactivar" : "Activar";
  btnToggle.disabled = !s.configured && !s.enabled;
  btnSync.classList.toggle("hidden", !s.enabled);
}

function lineRow(order, line) {
  const base = line.resolved ? "" : (line.tn_sku || "").replace(/-G[1-9]\d*$/i, "");
  return `<div class="list-row-sub">
      ${escapeHtml(String(line.quantity))} x ${escapeHtml(line.name)} &middot; ${line.tn_sku.startsWith("id:") ? "producto sin SKU en la tienda" : "SKU tienda: <b>" + escapeHtml(line.tn_sku || "(sin SKU)") + "</b>"}${line.resolved ? " &#10003;" : ""}
      ${base ? `<form class="inline-map" data-tn="${escapeHtml(base)}" style="display:inline-flex;gap:.3rem;margin-left:.4rem">
        <input class="sys-search" list="sys-products" placeholder="Buscar producto del sistema" size="22" required autocomplete="off">
        <button type="submit" class="btn-secondary">Asociar</button></form>` : ""}
    </div>`;
}

function renderReview(orders) {
  const el = document.getElementById("review-list");
  document.getElementById("review-count").textContent = orders.length ? `(${orders.length})` : "";
  el.innerHTML = orders.length ? "" : '<div class="card-desc">No hay nada para revisar.</div>';
  for (const o of orders) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="list-row-title">Pedido #${o.number} <span class="badge badge-warn">Revisar</span>
        <span class="card-sku">${escapeHtml(o.customer)} &middot; ${money(o.total)} &middot; pago ${fmtDate(o.paid_at)}</span></div>
      <div class="list-row-sub">${escapeHtml(o.reason)}</div>
      ${(o.lines || []).map((l) => lineRow(o, l)).join("")}
      <div class="form-actions">
        <button type="button" class="btn-secondary" data-act="ignore">Ya esta cargado a mano</button>
      </div>`;
    card.querySelector('[data-act="ignore"]').addEventListener("click", async () => {
      if (!confirm("Se marca como resuelto y NO se descuenta stock. ¿Seguro?")) return;
      await fetchJSON(`/api/tiendanube/orders/${o.tn_id}/ignore`, { method: "POST", headers: JSON_HEADERS, body: "{}" });
      toast("Pedido marcado", "success");
      load();
    });
    card.querySelectorAll("form.inline-map").forEach((f) =>
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          const r = await fetchJSON("/api/tiendanube/map", {
            method: "POST",
            headers: JSON_HEADERS,
            body: JSON.stringify({ tn_sku: f.dataset.tn, sku: skuFromChoice(f.querySelector("input").value) }),
          });
          toast(`Asociado. Se importaron ${r.imported} pedido(s).`, "success");
        } catch (err) {
          toast(errorMessage(err), "error");
        }
        load();
      })
    );
    el.appendChild(card);
  }
  if (orders.length) {
    const retry = document.createElement("div");
    retry.className = "form-actions";
    retry.innerHTML = '<button type="button" class="btn-secondary">Reintentar todos (si cargaste stock)</button>';
    retry.querySelector("button").addEventListener("click", async () => {
      const r = await fetchJSON("/api/tiendanube/retry", { method: "POST", headers: JSON_HEADERS, body: "{}" });
      toast(`Importados ${r.imported}, siguen para revisar ${r.review}`, "success");
      load();
    });
    el.appendChild(retry);
  }
}

function renderFlags(orders) {
  const el = document.getElementById("flag-list");
  el.innerHTML = orders.length ? "" : '<div class="card-desc">Sin avisos.</div>';
  for (const o of orders) {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `<div><div class="list-row-title">Pedido #${o.number} <span class="badge badge-off">Cancelado</span></div>
      <div class="list-row-sub">${escapeHtml(o.flag)}</div></div>
      <div class="row-actions"><a class="btn-secondary" href="/ventas/${o.sale_id}">Ver venta</a>
      <button type="button" class="btn-secondary">Ya lo resolvi</button></div>`;
    row.querySelector("button").addEventListener("click", async () => {
      await fetchJSON(`/api/tiendanube/orders/${o.tn_id}/ack`, { method: "POST", headers: JSON_HEADERS, body: "{}" });
      load();
    });
    el.appendChild(row);
  }
}

function renderRecent(orders) {
  const el = document.getElementById("recent-list");
  el.innerHTML = orders.length ? "" : '<div class="card-desc">Todavia no se importo ninguna venta.</div>';
  for (const o of orders) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/ventas/${o.sale_id}`;
    row.innerHTML = `<div><div class="list-row-title">Pedido #${o.number} &rarr; ${escapeHtml(o.sale_number)}</div>
      <div class="list-row-sub">${escapeHtml(o.customer)} &middot; ${fmtDate(o.paid_at)}</div></div>
      <div class="list-row-amount">${money(o.total)}</div>`;
    el.appendChild(row);
  }
}

async function load() {
  const s = await fetchJSON("/api/tiendanube/status");
  renderState(s);
  renderReview(s.review_orders);
  renderFlags(s.flagged_orders);
  renderRecent(s.recent_orders);
}

btnToggle.addEventListener("click", async () => {
  configError.classList.add("hidden");
  const enabling = !current.enabled;
  try {
    await fetchJSON("/api/tiendanube/config", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ enabled: enabling, office_id: officeSel.value, since: enabling ? sinceInput.value : "" }),
    });
  } catch (err) {
    configError.textContent = errorMessage(err);
    configError.classList.remove("hidden");
    return;
  }
  toast(enabling ? "Sincronizacion activada" : "Sincronizacion desactivada", "success");
  load();
});

officeSel.addEventListener("change", async () => {
  if (!current || !current.enabled) return;
  await fetchJSON("/api/tiendanube/config", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ enabled: true, office_id: officeSel.value }),
  });
  toast("Oficina actualizada", "success");
});

btnSync.addEventListener("click", async () => {
  try {
    await fetchJSON("/api/tiendanube/sync", { method: "POST", headers: JSON_HEADERS, body: "{}" });
    toast("Sincronizando...", "info");
    setTimeout(load, 5000);
  } catch (err) {
    toast(errorMessage(err), "error");
  }
});

load();


// --- Buscador de productos del sistema (para asociar)
const sysList = document.createElement("datalist");
sysList.id = "sys-products";
document.body.appendChild(sysList);
let sysTimer = null;

function skuFromChoice(text) {
  const t = text.trim();
  const i = t.indexOf(" - ");
  return i > 0 ? t.slice(0, i).trim() : t;
}

document.addEventListener("input", (e) => {
  if (!e.target.classList || !e.target.classList.contains("sys-search")) return;
  const q = e.target.value.trim();
  clearTimeout(sysTimer);
  if (q.length < 2 || q.includes(" - ")) return;
  sysTimer = setTimeout(async () => {
    try {
      const rows = await fetchJSON("/api/products?q=" + encodeURIComponent(q));
      sysList.innerHTML = rows.slice(0, 15).map((p) => `<option value="${escapeHtml(p.sku + " - " + p.name)}"></option>`).join("");
    } catch (err) { /* sin sugerencias */ }
  }, 250);
});

// --- Catalogo de la tienda
const catState = document.getElementById("catalog-state");
const catBox = document.getElementById("catalog");
const btnFetch = document.getElementById("btn-catalog-fetch");
let catalog = null;
let catPoll = null;

function stockText(e) {
  return e.unlimited_stock ? "stock sin limite" : `${e.stock} u.`;
}

function renderCatalog(c) {
  catalog = c;
  const when = c.fetched_at ? new Date(c.fetched_at).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : null;
  catState.textContent = c.running ? "Trayendo el catalogo de la tienda..." : c.error ? "Error: " + c.error : when ? "Ultima vez traido: " + when : "Todavia no se trajo.";
  btnFetch.disabled = c.running;
  catBox.classList.toggle("hidden", !c.total);
  if (!c.total) return;
  document.getElementById("catalog-summary").innerHTML = `<div class="card-name">${c.total} productos en la tienda</div>
    <div class="card-desc"><b>${c.existing_count}</b> ya estan en el sistema &middot; <b>${c.suggested.length}</b> parecen ser uno que ya existe &middot; <b>${c.new.length}</b> no se encontraron.</div>`;

  document.getElementById("sug-count").textContent = `(${c.suggested.length})`;
  const sl = document.getElementById("sug-list");
  sl.innerHTML = "";
  for (const e of c.suggested) {
    const row = document.createElement("div");
    row.className = "list-row";
    row.dataset.key = e.key;
    row.innerHTML = `<div><div class="list-row-title">${escapeHtml(e.name)}</div>
      <div class="list-row-sub">Tienda: ${escapeHtml(e.tn_sku || "sin SKU")} &middot; ${stockText(e)}<br>
      Sistema: <b>${escapeHtml(e.suggestion.sku)}</b> - ${escapeHtml(e.suggestion.name)}</div></div>
      <div class="row-actions"><select>
        <option value="skip">Omitir</option><option value="map">Asociar</option><option value="create">Crear</option></select></div>`;
    sl.appendChild(row);
  }
  document.getElementById("sug-block").classList.toggle("hidden", !c.suggested.length);

  document.getElementById("new-count").textContent = `(${c.new.length})`;
  renderNew();
}

function renderNew() {
  const filter = document.getElementById("new-filter").value.trim().toLowerCase();
  const nl = document.getElementById("new-list");
  const checked = new Set([...nl.querySelectorAll("input:checked")].map((i) => i.value));
  nl.innerHTML = "";
  for (const e of catalog.new) {
    const hay = (e.name + " " + (e.tn_sku || "")).toLowerCase();
    if (filter && !hay.includes(filter)) continue;
    const row = document.createElement("label");
    row.className = "list-row check-row";
    const warn = e.shared_sku ? `<div class="error">&#9888; El SKU esta repetido en otro producto de la tienda (${escapeHtml(e.shared_with || "")}). Corregilo en Tienda Nube: no se crea solo.</div>` : "";
    row.innerHTML = `<input type="checkbox" value="${escapeHtml(e.key)}" ${checked.has(e.key) ? "checked" : ""} ${e.shared_sku ? "disabled" : ""}>
      <div><div class="list-row-title">${escapeHtml(e.name)}</div>
      <div class="list-row-sub">${escapeHtml(e.tn_sku || "sin SKU")} &middot; ${money(e.price)} &middot; ${stockText(e)} &middot; ${escapeHtml(e.category || "sin categoria")}</div>${warn}</div>`;
    nl.appendChild(row);
  }
}

async function loadCatalog() {
  const c = await fetchJSON("/api/tiendanube/catalog");
  renderCatalog(c);
  if (c.running && !catPoll) {
    catPoll = setInterval(async () => {
      const x = await fetchJSON("/api/tiendanube/catalog");
      if (!x.running) { clearInterval(catPoll); catPoll = null; renderCatalog(x); }
    }, 3000);
  }
}

btnFetch.addEventListener("click", async () => {
  try {
    await fetchJSON("/api/tiendanube/catalog/fetch", { method: "POST", headers: JSON_HEADERS, body: "{}" });
  } catch (err) {
    toast(errorMessage(err), "error");
    return;
  }
  catState.textContent = "Trayendo el catalogo de la tienda...";
  btnFetch.disabled = true;
  setTimeout(loadCatalog, 1500);
});

document.getElementById("new-filter").addEventListener("input", renderNew);
document.getElementById("new-check").addEventListener("click", () =>
  document.querySelectorAll("#new-list input").forEach((i) => (i.checked = true)));
document.getElementById("new-uncheck").addEventListener("click", () =>
  document.querySelectorAll("#new-list input").forEach((i) => (i.checked = false)));
document.getElementById("sug-all").addEventListener("click", () =>
  document.querySelectorAll("#sug-list select").forEach((s) => (s.value = "map")));

document.getElementById("btn-apply").addEventListener("click", async () => {
  const err = document.getElementById("apply-error");
  err.classList.add("hidden");
  const create = [...document.querySelectorAll("#new-list input:checked")].map((i) => i.value);
  const maps = [];
  for (const row of document.querySelectorAll("#sug-list .list-row")) {
    const choice = row.querySelector("select").value;
    const e = catalog.suggested.find((x) => x.key === row.dataset.key);
    if (choice === "map") maps.push({ key: e.key, sku: e.suggestion.sku });
    if (choice === "create") create.push(e.key);
  }
  if (!create.length && !maps.length) {
    err.textContent = "No elegiste nada para aplicar.";
    err.classList.remove("hidden");
    return;
  }
  const loadStock = document.getElementById("load-stock").checked;
  const msg = `Se van a crear ${create.length} producto(s)${create.length && loadStock ? " con el stock de la tienda en la oficina elegida" : ""} y asociar ${maps.length}. ¿Aplicar?`;
  if (!confirm(msg)) return;
  try {
    const r = await fetchJSON("/api/tiendanube/catalog/apply", {
      method: "POST", headers: JSON_HEADERS,
      body: JSON.stringify({ create, maps, office_id: officeSel.value, load_stock: loadStock }),
    });
    const extra = r.skipped.length ? ` (${r.skipped.length} omitidos: ${r.skipped.slice(0, 2).map((s) => s.reason).join("; ")})` : "";
    toast(`Creados ${r.created}, asociados ${r.mapped}${extra}`, "success", 8000);
  } catch (e2) {
    err.textContent = errorMessage(e2);
    err.classList.remove("hidden");
    return;
  }
  load();
  loadCatalog();
});

loadCatalog();
