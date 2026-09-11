const salePickerEl = document.getElementById("sale-picker");
const saleSearchEl = document.getElementById("sale-search");
const saleResultsEl = document.getElementById("sale-results");
const returnFormSection = document.getElementById("return-form-section");
const selectedSaleInfo = document.getElementById("selected-sale-info");
const returnItemsBody = document.getElementById("return-items-body");
const returnForm = document.getElementById("return-form");
const formError = document.getElementById("form-error");

let currentSale = null;
let lines = []; // {sale_item_id, sku, name, sold, alreadyReturned, toReturn}

async function selectSale(saleId) {
  currentSale = await fetchJSON(`/api/sales/${saleId}`);
  salePickerEl.classList.add("hidden");
  returnFormSection.classList.remove("hidden");

  selectedSaleInfo.innerHTML = `
    <div class="card-top">
      <div>
        <div class="card-name">${escapeHtml(currentSale.number)} &middot; ${escapeHtml(currentSale.channel_name)}</div>
        <div class="card-sku">${escapeHtml(currentSale.customer_name || "Sin cliente")} &middot; ${formatDateTime(currentSale.created_at)}</div>
      </div>
      <button type="button" id="btn-change-sale">Cambiar venta</button>
    </div>
  `;
  document.getElementById("btn-change-sale").addEventListener("click", () => {
    returnFormSection.classList.add("hidden");
    salePickerEl.classList.remove("hidden");
    currentSale = null;
    lines = [];
  });

  lines = currentSale.items
    .filter((i) => i.quantity - i.already_returned > 0)
    .map((i) => ({
      sale_item_id: i.id,
      sku: i.sku,
      name: i.product_name,
      sold: i.quantity,
      alreadyReturned: i.already_returned,
      toReturn: 0,
    }));

  renderItems();
}

function renderItems() {
  returnItemsBody.innerHTML = "";
  if (!lines.length) {
    returnItemsBody.innerHTML = '<tr><td colspan="4">Esta venta no tiene items disponibles para devolver.</td></tr>';
    return;
  }
  lines.forEach((line, idx) => {
    const available = line.sold - line.alreadyReturned;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(line.name)}<div class="card-sku">SKU: ${escapeHtml(line.sku)}</div></td>
      <td>${line.sold}</td>
      <td>${line.alreadyReturned}</td>
      <td>
        <div class="qty-stepper">
          <button type="button" class="qty-minus" data-idx="${idx}">-</button>
          <input type="number" min="0" max="${available}" value="0" class="return-qty-input" data-idx="${idx}">
          <button type="button" class="qty-plus" data-idx="${idx}">+</button>
        </div>
      </td>
    `;
    returnItemsBody.appendChild(tr);
  });

  function setQty(idx, value) {
    const available = lines[idx].sold - lines[idx].alreadyReturned;
    lines[idx].toReturn = Math.max(0, Math.min(value, available));
    returnItemsBody.querySelector(`.return-qty-input[data-idx="${idx}"]`).value = lines[idx].toReturn;
  }

  returnItemsBody.querySelectorAll(".return-qty-input").forEach((input) => {
    input.addEventListener("input", () => {
      const idx = Number(input.dataset.idx);
      setQty(idx, Number(input.value) || 0);
    });
  });
  returnItemsBody.querySelectorAll(".qty-plus").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.idx);
      setQty(idx, lines[idx].toReturn + 1);
    });
  });
  returnItemsBody.querySelectorAll(".qty-minus").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.idx);
      setQty(idx, lines[idx].toReturn - 1);
    });
  });
}

let searchTimer;
saleSearchEl.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = saleSearchEl.value.trim();
  searchTimer = setTimeout(async () => {
    const sales = await fetchJSON(q ? `/api/sales?q=${encodeURIComponent(q)}` : "/api/sales");
    renderSaleResults(sales.slice(0, 15));
  }, 250);
});

function renderSaleResults(sales) {
  saleResultsEl.innerHTML = "";
  if (!sales.length) {
    saleResultsEl.innerHTML = '<div class="empty">Sin resultados.</div>';
    return;
  }
  for (const s of sales) {
    const row = document.createElement("div");
    row.className = "product-result-row";
    row.innerHTML = `
      <span>${escapeHtml(s.number)} &middot; ${escapeHtml(s.customer_name || "Sin cliente")}<br>
        <span class="card-sku">${money(s.total)} &middot; ${formatDateTime(s.created_at)}</span></span>
      <button type="button" class="btn-secondary">Elegir</button>
    `;
    row.addEventListener("click", () => selectSale(s.id));
    saleResultsEl.appendChild(row);
  }
}

returnForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.classList.add("hidden");

  const items = lines.filter((l) => l.toReturn > 0).map((l) => ({ sale_item_id: l.sale_item_id, quantity: l.toReturn }));
  if (!items.length) {
    formError.textContent = "Indica al menos una cantidad a devolver.";
    formError.classList.remove("hidden");
    return;
  }

  try {
    await fetchJSON("/api/returns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sale_id: currentSale.id,
        reason: document.getElementById("f-reason").value,
        note: document.getElementById("f-note").value.trim(),
        items,
      }),
    });
    window.location.href = "/devoluciones";
  } catch (err) {
    formError.textContent = errorMessage(err);
    formError.classList.remove("hidden");
  }
});

(async () => {
  const params = new URLSearchParams(window.location.search);
  const preselectedSaleId = params.get("sale_id");
  if (preselectedSaleId) {
    selectSale(preselectedSaleId);
  } else {
    const sales = await fetchJSON("/api/sales").then((s) => s.slice(0, 15)).catch(() => []);
    renderSaleResults(sales);
  }
})();
