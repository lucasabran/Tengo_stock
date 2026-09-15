const pageTitle = document.getElementById("page-title");
const summaryEl = document.getElementById("summary");
const ledgerBody = document.getElementById("ledger-body");
const ledgerEmpty = document.getElementById("ledger-empty");

const btnNewMovement = document.getElementById("btn-new-movement");
const movementDialog = document.getElementById("movement-dialog");
const movementForm = document.getElementById("movement-form");
const movementError = document.getElementById("movement-error");
const movementCancel = document.getElementById("movement-cancel");

function balanceCard(label, stats, currency) {
  if (!stats.charged) return "";
  const cls = stats.balance > 0 ? "movement-negative" : "movement-positive";
  return `
    <div class="card">
      <div class="card-top">
        <div>
          <div class="card-name">${label}</div>
          <div class="card-sku">Vendido a cuenta: ${money(stats.charged, currency)} &middot; Pagado: ${money(stats.paid, currency)}</div>
        </div>
        <div class="card-price ${cls}">${money(stats.balance, currency)}</div>
      </div>
    </div>
  `;
}

async function load() {
  let account;
  try {
    account = await fetchJSON(`/api/accounts/${window.CUSTOMER_ID}`);
  } catch (err) {
    summaryEl.innerHTML = `<div class="empty">${escapeHtml(errorMessage(err))}</div>`;
    return;
  }

  pageTitle.textContent = account.customer_name;

  summaryEl.innerHTML =
    balanceCard("Cuenta en pesos", account.ars, "ARS") + balanceCard("Cuenta en dolares", account.usd, "USD");
  if (!account.ars.charged && !account.usd.charged) {
    summaryEl.innerHTML = '<div class="empty">Este cliente todavia no tiene ventas a cuenta corriente.</div>';
  }

  ledgerBody.innerHTML = "";
  if (!account.ledger.length) {
    ledgerEmpty.classList.remove("hidden");
  } else {
    ledgerEmpty.classList.add("hidden");
    for (const item of account.ledger) {
      const tr = document.createElement("tr");
      const signed = item.type === "charge" ? item.amount : -item.amount;
      tr.innerHTML = `
        <td>${formatDateTime(item.date)}</td>
        <td>${escapeHtml(item.label)} <span class="card-sku">(${item.currency === "USD" ? "USD" : "Pesos"})</span>${item.note ? `<div class="card-sku">${escapeHtml(item.note)}</div>` : ""}</td>
        <td class="${signed > 0 ? "movement-negative" : "movement-positive"}">${signed > 0 ? "+" : ""}${money(signed, item.currency)}</td>
      `;
      ledgerBody.appendChild(tr);
    }
  }
}

btnNewMovement.addEventListener("click", () => {
  movementForm.reset();
  movementError.classList.add("hidden");
  movementDialog.showModal();
});
movementCancel.addEventListener("click", () => movementDialog.close());

movementForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  movementError.classList.add("hidden");
  try {
    await fetchJSON(`/api/accounts/${window.CUSTOMER_ID}/movements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: document.getElementById("m-type").value,
        amount: parseFloat(document.getElementById("m-amount").value),
        currency: document.getElementById("m-currency").value,
        payment_method: document.getElementById("m-method").value,
        note: document.getElementById("m-note").value.trim(),
      }),
    });
  } catch (err) {
    movementError.textContent = errorMessage(err);
    movementError.classList.remove("hidden");
    return;
  }
  movementDialog.close();
  toast("Movimiento registrado", "success");
  load();
});

load();
