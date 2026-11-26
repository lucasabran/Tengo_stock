const JSON_HEADERS = { "Content-Type": "application/json" };
const REP = {
  "5_green": ["Verde", "#2e9e4f"], "4_light_green": ["Verde claro", "#8bc34a"], "3_yellow": ["Amarilla", "#f2b600"],
  "2_orange": ["Naranja", "#f57c00"], "1_red": ["Roja", "#d32f2f"],
};
const SHIP = {
  pending: "Pendiente", handling: "Preparando", ready_to_ship: "Para despachar", shipped: "En camino",
  delivered: "Entregado", not_delivered: "No entregado", cancelled: "Cancelado", returned: "Devuelto",
};
const SUBSHIP = { ready_to_print: "etiqueta sin imprimir", printed: "etiqueta impresa", in_hub: "en centro", waiting_for_carrier: "esperando al correo" };
const ORDER = { paid: "Pagada", cancelled: "Cancelada", confirmed: "Confirmada", payment_required: "Sin pagar", payment_in_process: "Pago en proceso", partially_refunded: "Reembolso parcial", pending_cancel: "Cancelándose" };
const ACTION = { send_message_to_mediator: "mandar mensaje a la mediación", send_message_to_complainant: "responder al comprador", refund: "reembolsar", open_dispute: "pedir mediación", allow_return: "aceptar devolución", send_potential_shipping: "informar envío" };
let overview = null;

const fmt = (iso) => (iso ? formatDateTime(iso) : "-");
const saleLink = (id) => `https://www.mercadolibre.com.ar/ventas/${id}/detalle`;
const accountBadge = (name) => `<span class="badge">${escapeHtml(name)}</span>`;

function ago(iso) {
  const h = (Date.now() - new Date(iso)) / 36e5;
  if (isNaN(h)) return "";
  if (h < 1) return `hace ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} días`;
}

function untilText(iso) {
  const h = (new Date(iso) - Date.now()) / 36e5;
  if (isNaN(h)) return "";
  if (h < 0) return "VENCIDO";
  if (h < 48) return `vence en ${Math.round(h)} h`;
  return `vence en ${Math.round(h / 24)} días`;
}

// --- pestañas ----------------------------------------------------------------------------
const loaders = { resumen: loadOverview, preguntas: loadQuestions, mensajes: loadMessages, reclamos: loadClaims, ventas: loadOrders };
let currentTab = "resumen";
document.querySelectorAll("#ml-tabs .tab").forEach((b) =>
  b.addEventListener("click", () => {
    currentTab = b.dataset.tab;
    document.querySelectorAll("#ml-tabs .tab").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== currentTab));
    try { localStorage.setItem("ml-tab", currentTab); } catch (e) {}
    loaders[currentTab]();
  })
);

function fillAccountFilters() {
  for (const id of ["q-account", "o-account"]) {
    const sel = document.getElementById(id);
    const prev = sel.value;
    sel.innerHTML = `<option value="">Todas las cuentas</option>` +
      overview.accounts.map((a) => `<option value="${a.user_id}">${escapeHtml(a.name)}</option>`).join("");
    sel.value = prev;
  }
}

// --- resumen -----------------------------------------------------------------------------
async function loadOverview() {
  overview = await fetchJSON("/api/ml/overview");
  fillAccountFilters();
  const alert = document.getElementById("ml-alert");
  alert.innerHTML = overview.configured ? "" :
    `<div class="card"><div class="card-name">Falta conectar la app de Mercado Libre</div>
     <div class="card-desc">En Render &gt; Environment hay que cargar <b>ML_CLIENT_ID</b>, <b>ML_CLIENT_SECRET</b> y <b>ML_REDIRECT_URI</b>. Después se conectan las cuentas desde acá.</div></div>`;
  document.getElementById("manage-card").classList.toggle("hidden", !overview.can_manage || !overview.configured);

  const tot = (k) => overview.accounts.reduce((s, a) => s + a[k], 0);
  const count = (id, n) => (document.getElementById(id).innerHTML = n ? `<span class="badge badge-warn">${n}</span>` : "");
  count("n-preguntas", tot("questions"));
  count("n-mensajes", tot("messages"));
  count("n-reclamos", tot("claims"));

  const el = document.getElementById("accounts");
  if (!overview.accounts.length) {
    el.innerHTML = `<div class="card-desc">Todavía no hay cuentas conectadas.</div>`;
    return;
  }
  el.innerHTML = `<div class="card tools-card"><div class="card-desc">
      <b>${overview.accounts.length}</b> cuentas &middot; <b>${tot("sales_today")}</b> ventas hoy &middot;
      <b>${tot("sales_week")}</b> en 7 días (${money(tot("total_week"))}) &middot; <b>${tot("to_ship")}</b> por despachar</div></div>`;
  for (const a of overview.accounts) {
    const [repName, repColor] = REP[a.reputation.level_id] || ["Sin color", "#999"];
    const real = a.reputation.real_level && a.reputation.protection_end_date
      ? ` &middot; real: ${escapeHtml(a.reputation.real_level)} (protegida hasta ${formatDate(a.reputation.protection_end_date.slice(0, 10))})` : "";
    const m = a.reputation.metrics || {};
    const pct = (x) => (x && x.rate != null ? `${(x.rate * 100).toFixed(1)}%` : "-");
    const status = a.status === "reconectar" ? `<span class="badge badge-off">Volver a conectar</span>`
      : a.status === "error" ? `<span class="badge badge-warn">Con error</span>` : "";
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="list-row-title"><span style="display:inline-block;width:.8rem;height:.8rem;border-radius:50%;background:${repColor};vertical-align:middle"></span>
        ${escapeHtml(a.name)} ${a.alias ? `<span class="card-sku">${escapeHtml(a.nickname)}</span>` : ""} ${status}</div>
      <div class="list-row-sub">Reputación ${repName}${real} &middot; reclamos ${pct(m.claims)} &middot; demoras ${pct(m.delayed_handling_time)} &middot; cancelaciones ${pct(m.cancellations)}</div>
      <div class="card-desc">
        ${a.questions ? `<b>${a.questions}</b> preguntas sin responder &middot; ` : ""}
        ${a.messages ? `<b>${a.messages}</b> mensajes sin leer &middot; ` : ""}
        ${a.claims ? `<b>${a.claims}</b> reclamos abiertos &middot; ` : ""}
        ${a.to_ship ? `<b>${a.to_ship}</b> por despachar &middot; ` : ""}
        ${a.sales_today} ventas hoy &middot; ${a.sales_week} en 7 días (${money(a.total_week)})</div>
      ${a.last_error ? `<div class="error">${escapeHtml(a.last_error)}</div>` : ""}
      ${a.status === "reconectar" ? `<div class="card-desc">Generá un link nuevo abajo y abrilo con la sesión de esta cuenta: se reconecta sin perder nada.</div>` : ""}
      <div class="list-row-sub">Actualizada ${a.last_sync ? ago(a.last_sync) : "todavía no"}</div>
      ${overview.can_manage ? `<div class="form-actions">
        <button type="button" class="btn-secondary" data-act="alias">Cambiar nombre</button>
        <button type="button" class="btn-secondary" data-act="delete">Desconectar</button></div>` : ""}`;
    card.querySelector('[data-act="alias"]')?.addEventListener("click", async () => {
      const alias = prompt("Nombre para reconocer esta cuenta:", a.alias || a.nickname);
      if (alias === null) return;
      await fetchJSON(`/api/ml/accounts/${a.user_id}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ alias }) });
      loadOverview();
    });
    card.querySelector('[data-act="delete"]')?.addEventListener("click", async () => {
      if (!(await confirmDialog(`Se deja de ver la cuenta ${a.name} y se borran sus datos del panel (no toca nada en Mercado Libre). ¿Seguro?`))) return;
      await fetchJSON(`/api/ml/accounts/${a.user_id}/delete`, { method: "POST", headers: JSON_HEADERS, body: "{}" });
      toast("Cuenta desconectada", "success");
      loadOverview();
    });
    el.appendChild(card);
  }
}

document.getElementById("link-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const r = await fetchJSON("/api/ml/link", { method: "POST", headers: JSON_HEADERS,
      body: JSON.stringify({ alias: document.getElementById("link-alias").value }) });
    document.getElementById("link-url").value = r.url;
    document.getElementById("link-out").classList.remove("hidden");
  } catch (err) {
    toast(errorMessage(err), "error");
  }
});
document.getElementById("link-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(document.getElementById("link-url").value);
    toast("Link copiado", "success");
  } catch (e) {
    document.getElementById("link-url").select();
  }
});
document.getElementById("btn-sync").addEventListener("click", async () => {
  try {
    await fetchJSON("/api/ml/sync", { method: "POST", headers: JSON_HEADERS, body: "{}" });
    toast("Actualizando todas las cuentas. Tarda alrededor de un minuto.", "info");
    setTimeout(loadOverview, 30000);
  } catch (err) {
    toast(errorMessage(err), "error");
  }
});

// --- preguntas ---------------------------------------------------------------------------
async function loadQuestions() {
  const data = await fetchJSON("/api/ml/questions");
  const filter = document.getElementById("q-account").value;
  const list = data.pending.filter((q) => !filter || String(q.user_id) === filter);
  const el = document.getElementById("questions");
  el.innerHTML = list.length ? "" : `<div class="card-desc">No hay preguntas sin responder. 🎉</div>`;
  const canAnswer = overview && overview.can_answer;
  for (const q of list) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="list-row-sub">${accountBadge(q.account)} ${ago(q.date_created)} &middot;
        ${q.item_link ? `<a href="${escapeHtml(q.item_link)}" target="_blank" rel="noopener">${escapeHtml(q.item_title || q.item_id)}</a>` : escapeHtml(q.item_title || q.item_id)}</div>
      <div class="list-row-title" style="margin:.4rem 0">${escapeHtml(q.text)}</div>
      ${canAnswer ? `<form class="answer-form">
        <textarea rows="3" maxlength="2000" required placeholder="Escribí la respuesta" style="width:100%"></textarea>
        <div class="form-actions"><button type="submit" class="btn-primary">Responder</button></div></form>` : ""}`;
    card.querySelector("form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.target.querySelector("button");
      btn.disabled = true;
      try {
        await fetchJSON(`/api/ml/questions/${q.id}/answer`, { method: "POST", headers: JSON_HEADERS,
          body: JSON.stringify({ text: e.target.querySelector("textarea").value }) });
        toast("Respondida", "success");
        card.remove();
        loadOverview();
      } catch (err) {
        toast(errorMessage(err), "error", 8000);
        btn.disabled = false;
      }
    });
    el.appendChild(card);
  }
  document.getElementById("answered").innerHTML = data.answered.map((q) => `
    <div class="list-row"><div><div class="list-row-sub">${accountBadge(q.account)} ${escapeHtml(q.item_title || "")} &middot; ${fmt(q.answered_at)} &middot; ${escapeHtml(q.answered_by)}</div>
    <div>${escapeHtml(q.text)}</div><div class="list-row-sub">↳ ${escapeHtml(q.answer)}</div></div></div>`).join("") ||
    `<div class="card-desc">Todavía no se respondió ninguna desde el panel.</div>`;
}
document.getElementById("q-account").addEventListener("change", loadQuestions);

// --- mensajes ----------------------------------------------------------------------------
async function loadMessages() {
  const data = await fetchJSON("/api/ml/messages");
  const el = document.getElementById("conversations");
  el.innerHTML = data.conversations.length ? "" : `<div class="card-desc">No hay mensajes sin leer.</div>`;
  for (const c of data.conversations) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="list-row-sub">${accountBadge(c.account)} ${c.last_date ? ago(c.last_date) : ""} &middot;
        <a href="${saleLink(c.pack_id)}" target="_blank" rel="noopener">Venta ${c.pack_id}</a> ${c.items ? "&middot; " + escapeHtml(c.items) : ""}</div>
      <div class="list-row-title" style="margin:.4rem 0">${escapeHtml(c.last_text || "(sin texto)")}</div>
      <div class="thread hidden"></div>
      <div class="form-actions"><button type="button" class="btn-secondary" data-act="open">Ver conversación</button></div>
      ${overview && overview.can_answer ? `<form class="reply-form">
        <textarea rows="2" maxlength="350" required placeholder="Respuesta (máx. 350 caracteres)" style="width:100%"></textarea>
        <div class="form-actions"><button type="submit" class="btn-primary">Enviar</button></div></form>` : ""}`;
    card.querySelector('[data-act="open"]').addEventListener("click", async (e) => {
      const thread = card.querySelector(".thread");
      e.target.disabled = true;
      try {
        const r = await fetchJSON(`/api/ml/messages/${c.user_id}/${c.pack_id}`);
        thread.innerHTML = r.messages.map((m) => `<div class="list-row-sub" style="text-align:${m.from_me ? "right" : "left"}">
          <b>${m.from_me ? "Vendedor" : "Comprador"}</b> ${fmt(m.date)}<br>${escapeHtml(m.text)}</div>`).join("");
        thread.classList.remove("hidden");
        e.target.remove();
      } catch (err) {
        toast(errorMessage(err), "error");
        e.target.disabled = false;
      }
    });
    card.querySelector("form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.target.querySelector("button");
      btn.disabled = true;
      try {
        await fetchJSON(`/api/ml/messages/${c.user_id}/${c.pack_id}/reply`, { method: "POST", headers: JSON_HEADERS,
          body: JSON.stringify({ text: e.target.querySelector("textarea").value }) });
        toast("Mensaje enviado", "success");
        card.remove();
        loadOverview();
      } catch (err) {
        toast(errorMessage(err), "error", 8000);
        btn.disabled = false;
      }
    });
    el.appendChild(card);
  }
}

// --- reclamos ----------------------------------------------------------------------------
async function loadClaims() {
  const data = await fetchJSON("/api/ml/claims");
  document.getElementById("claims").innerHTML = data.claims.map((c) => {
    const due = c.due_date ? untilText(c.due_date) : "";
    const urgent = c.due_date && (new Date(c.due_date) - Date.now()) / 36e5 < 48;
    return `<div class="card">
      <div class="list-row-title">${accountBadge(c.account)} ${c.stage === "dispute" ? "Mediación" : "Reclamo"} ${c.id}
        ${due ? `<span class="badge ${urgent ? "badge-off" : "badge-warn"}">${due}</span>` : ""}</div>
      <div class="list-row-sub">${escapeHtml(c.items || "")} &middot; abierto ${fmt(c.date_created)} &middot; motivo ${escapeHtml(c.reason_id)}</div>
      ${c.action ? `<div class="card-desc">Hay que: <b>${escapeHtml(ACTION[c.action] || c.action)}</b>${c.due_date ? " antes del " + fmt(c.due_date) : ""}</div>` : ""}
      <div class="form-actions"><a class="btn-secondary" href="${saleLink(c.order_id)}" target="_blank" rel="noopener">Abrir la venta en Mercado Libre</a></div>
    </div>`;
  }).join("") || `<div class="card-desc">No hay reclamos abiertos.</div>`;
}

// --- ventas ------------------------------------------------------------------------------
async function loadOrders() {
  const acc = document.getElementById("o-account").value;
  const days = document.getElementById("o-days").value;
  const onlyPending = document.getElementById("o-ship").value === "pend";
  const data = await fetchJSON(`/api/ml/orders?days=${days}${acc ? "&account=" + acc : ""}`);
  let orders = data.orders;
  if (onlyPending) orders = orders.filter((o) => o.status === "paid" && ["ready_to_ship", "pending", "handling"].includes(o.ship_status));
  const paid = orders.filter((o) => o.status === "paid");
  document.getElementById("orders-summary").innerHTML = `<div class="card-desc"><b>${paid.length}</b> ventas pagadas por
    <b>${money(paid.reduce((s, o) => s + o.total, 0))}</b> &middot; ${paid.reduce((s, o) => s + o.units, 0)} unidades
    ${orders.length > paid.length ? `&middot; ${orders.length - paid.length} canceladas o sin pagar` : ""}</div>`;
  document.getElementById("orders").innerHTML = orders.map((o) => `
    <div class="list-row"><div>
      <div class="list-row-title">${escapeHtml(o.items)}</div>
      <div class="list-row-sub">${accountBadge(o.account)} ${fmt(o.date_created)} &middot; ${escapeHtml(o.buyer)} &middot;
        <a href="${saleLink(o.pack_id || o.id)}" target="_blank" rel="noopener">${o.id}</a></div>
      <div class="list-row-sub">${escapeHtml(ORDER[o.status] || o.status)}${o.ship_status ? " &middot; envío: " + escapeHtml(SHIP[o.ship_status] || o.ship_status) +
        (SUBSHIP[o.ship_substatus] ? ` (${SUBSHIP[o.ship_substatus]})` : "") : (o.shipping_id ? "" : " &middot; sin envío de Mercado Libre")}</div>
    </div><div class="list-row-amount">${money(o.total)}</div></div>`).join("") || `<div class="card-desc">No hay ventas en ese período.</div>`;
}
["o-account", "o-days", "o-ship"].forEach((id) => document.getElementById(id).addEventListener("change", loadOrders));

// --- arranque ----------------------------------------------------------------------------
(async () => {
  await loadOverview();
  let saved = "resumen";
  try { saved = localStorage.getItem("ml-tab") || "resumen"; } catch (e) {}
  if (saved !== "resumen") document.querySelector(`#ml-tabs .tab[data-tab="${saved}"]`)?.click();
  setInterval(() => {
    // no recargar mientras alguien está escribiendo una respuesta (se perdería el texto)
    const typing = [...document.querySelectorAll("textarea")].some((t) => t.value.trim() || t === document.activeElement);
    if (typing) return;
    loadOverview();
    if (currentTab !== "resumen" && currentTab !== "ventas") loaders[currentTab]();
  }, 120000);
})();
