const groupsEl = document.getElementById("groups");
const summaryEl = document.getElementById("summary");
const SEVERITY_LABEL = { critical: "Urgente", warning: "Revisar", info: "Mejora" };
const SEVERITY_BADGE = { critical: "badge-off", warning: "badge-warn", info: "" };

function renderGroups(data) {
  summaryEl.innerHTML = data.total
    ? `<div class="card-name">${data.total} aviso(s) en ${data.products} producto(s)</div>
       <div class="card-desc">${data.critical} urgente(s). Toca cada grupo para ver los productos.</div>`
    : `<div class="card-name">Todo en orden</div><div class="card-desc">No hay nada para revisar en ${data.products} producto(s).</div>`;

  groupsEl.innerHTML = "";
  for (const g of data.groups) {
    const box = document.createElement("details");
    box.className = "card";
    if (g.severity === "critical") box.open = true;
    const shown = g.items.length < g.count ? `<div class="card-sku">Se muestran los primeros ${g.items.length} de ${g.count}.</div>` : "";
    box.innerHTML = `
      <summary class="list-row-title">
        <span class="badge ${SEVERITY_BADGE[g.severity]}">${SEVERITY_LABEL[g.severity]}</span>
        ${escapeHtml(g.title)} <span class="card-sku">(${g.count})</span>
      </summary>
      ${g.hint ? `<div class="card-sku">${escapeHtml(g.hint)}</div>` : ""}
      <div class="alert-items">
        ${g.items
          .map(
            (i) => `<a class="list-row alert-row" href="/stock?q=${encodeURIComponent(i.sku)}">
              <div><div class="list-row-title">${escapeHtml(i.name)}</div>
              <div class="list-row-sub">SKU ${escapeHtml(i.sku)}${i.detail ? " &middot; " + escapeHtml(i.detail) : ""}</div></div>
            </a>`
          )
          .join("")}
      </div>
      ${shown}`;
    groupsEl.appendChild(box);
  }
}

async function load() {
  renderGroups(await fetchJSON("/api/alerts"));
}

// Reglas de margen (solo con permiso de costos)
const pricingCard = document.getElementById("pricing-card");
const pricingError = document.getElementById("pricing-error");
const pc = {
  fee_percent: document.getElementById("pc-fee"),
  target_margin: document.getElementById("pc-target"),
  min_margin: document.getElementById("pc-min"),
  fixed_cost: document.getElementById("pc-fixed"),
  shipping_cost: document.getElementById("pc-shipping"),
};

async function loadPricing() {
  const cfg = await fetchJSON("/api/pricing-config");
  for (const [key, el] of Object.entries(pc)) el.value = cfg[key];
}

if (can("stock.costs")) {
  pricingCard.classList.remove("hidden");
  loadPricing();
  document.getElementById("pricing-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    pricingError.classList.add("hidden");
    const body = {};
    for (const [key, el] of Object.entries(pc)) body[key] = el.value;
    try {
      await fetchJSON("/api/pricing-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      pricingError.textContent = errorMessage(err);
      pricingError.classList.remove("hidden");
      return;
    }
    toast("Reglas guardadas", "success");
    load();
  });
}

load();
