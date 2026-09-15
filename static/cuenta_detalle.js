const pageTitle = document.getElementById("page-title");
const summaryEl = document.getElementById("summary");
const ledgerBody = document.getElementById("ledger-body");
const ledgerEmpty = document.getElementById("ledger-empty");

const btnNewPayment = document.getElementById("btn-new-payment");
const paymentDialog = document.getElementById("payment-dialog");
const paymentForm = document.getElementById("payment-form");
const paymentError = document.getElementById("payment-error");
const paymentCancel = document.getElementById("payment-cancel");

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

btnNewPayment.addEventListener("click", () => {
  paymentForm.reset();
  paymentError.classList.add("hidden");
  paymentDialog.showModal();
});
paymentCancel.addEventListener("click", () => paymentDialog.close());

paymentForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  paymentError.classList.add("hidden");
  try {
    await fetchJSON(`/api/accounts/${window.CUSTOMER_ID}/payments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        amount: parseFloat(document.getElementById("p-amount").value),
        currency: document.getElementById("p-currency").value,
        payment_method: document.getElementById("p-method").value,
        note: document.getElementById("p-note").value.trim(),
      }),
    });
  } catch (err) {
    paymentError.textContent = errorMessage(err);
    paymentError.classList.remove("hidden");
    return;
  }
  paymentDialog.close();
  toast("Pago registrado", "success");
  load();
});

load();
