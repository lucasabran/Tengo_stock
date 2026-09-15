const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const resultsEl = document.getElementById("customer-results");

function balanceHtml(balance, currency) {
  if (!balance) return "";
  const cls = balance > 0 ? "movement-negative" : "movement-positive";
  return `<div class="list-row-amount ${cls}">${money(balance, currency)}</div>`;
}

function render(accounts) {
  listEl.innerHTML = "";
  if (!accounts.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay cuentas con movimientos.</div>';
    return;
  }
  for (const a of accounts) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/cuentas/${a.customer_id}`;
    const parts = [];
    if (a.ars.charged > 0) parts.push(`Pesos: cargado ${money(a.ars.charged)} &middot; pagado ${money(a.ars.paid)}`);
    if (a.usd.charged > 0) parts.push(`Dolares: cargado ${money(a.usd.charged, "USD")} &middot; pagado ${money(a.usd.paid, "USD")}`);
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(a.customer_name)}</div>
        <div class="list-row-sub">${parts.join(" &middot; ")}</div>
      </div>
      <div>
        ${balanceHtml(a.ars.balance, "ARS")}
        ${balanceHtml(a.usd.balance, "USD")}
      </div>
    `;
    listEl.appendChild(row);
  }
}

async function refresh() {
  const accounts = await fetchJSON("/api/accounts");
  render(accounts);
}

let searchTimer;
searchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = searchEl.value.trim();
  if (!q) {
    resultsEl.classList.add("hidden");
    return;
  }
  searchTimer = setTimeout(async () => {
    const customers = await fetchJSON(`/api/customers?q=${encodeURIComponent(q)}`);
    renderResults(customers);
  }, 250);
});

function renderResults(customers) {
  resultsEl.innerHTML = "";
  if (!customers.length) {
    resultsEl.innerHTML = '<div class="empty">Sin resultados.</div>';
    resultsEl.classList.remove("hidden");
    return;
  }
  for (const c of customers) {
    const row = document.createElement("div");
    row.className = "product-result-row";
    row.innerHTML = `<span>${escapeHtml(c.name)}${c.phone ? ` <span class="card-sku">${escapeHtml(c.phone)}</span>` : ""}</span><button type="button" class="btn-secondary">Ver cuenta</button>`;
    row.addEventListener("click", () => {
      window.location.href = `/cuentas/${c.id}`;
    });
    resultsEl.appendChild(row);
  }
  resultsEl.classList.remove("hidden");
}

refresh();
