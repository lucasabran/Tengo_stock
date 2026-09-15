const listEl = document.getElementById("list");

function balanceHtml(balance, currency) {
  if (!balance) return "";
  const cls = balance > 0 ? "movement-negative" : "movement-positive";
  return `<div class="list-row-amount ${cls}">${money(balance, currency)}</div>`;
}

function render(accounts) {
  listEl.innerHTML = "";
  if (!accounts.length) {
    listEl.innerHTML = '<div class="empty">Todavia no hay ventas a cuenta corriente.</div>';
    return;
  }
  for (const a of accounts) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/cuentas/${a.customer_id}`;
    const parts = [];
    if (a.ars.charged > 0) parts.push(`Pesos: vendido ${money(a.ars.charged)} &middot; pagado ${money(a.ars.paid)}`);
    if (a.usd.charged > 0) parts.push(`Dolares: vendido ${money(a.usd.charged, "USD")} &middot; pagado ${money(a.usd.paid, "USD")}`);
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

refresh();
