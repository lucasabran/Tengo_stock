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
      <div class="card-desc">Se revisa la tienda cada 10 minutos. Importa pedidos pagados desde ${fmtDate(s.since)}.
      Ultima revision: ${fmtDate(s.last_sync)}. ${s.imported} venta(s) importadas, ${s.review} para revisar.</div>`;
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
        <input placeholder="SKU en el sistema" size="14" required>
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
            body: JSON.stringify({ tn_sku: f.dataset.tn, sku: f.querySelector("input").value.trim() }),
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
