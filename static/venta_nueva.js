const channelSelect = document.getElementById("f-channel");
const btnNewChannel = document.getElementById("btn-new-channel");
const channelDialog = document.getElementById("channel-dialog");
const channelForm = document.getElementById("channel-form");
const channelCancel = document.getElementById("channel-cancel");

const customerSelect = document.getElementById("f-customer");
const btnNewCustomer = document.getElementById("btn-new-customer");
const customerDialog = document.getElementById("customer-dialog");
const customerForm = document.getElementById("customer-form");
const customerCancel = document.getElementById("customer-cancel");

const productSearch = document.getElementById("product-search");
const productResults = document.getElementById("product-results");
const cartBody = document.getElementById("cart-body");
const cartEmpty = document.getElementById("cart-empty");

const discountInput = document.getElementById("f-discount");
const totalSubtotalEl = document.getElementById("total-subtotal");
const totalTotalEl = document.getElementById("total-total");

const form = document.getElementById("sale-form");
const formError = document.getElementById("form-error");

let cart = []; // {sku, name, price, quantity, maxStock}

async function loadChannels(selectId) {
  const channels = await fetchJSON("/api/channels?active=1");
  channelSelect.innerHTML = "";
  for (const c of channels) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    channelSelect.appendChild(opt);
  }
  if (selectId) channelSelect.value = selectId;
}

btnNewChannel.addEventListener("click", () => {
  channelForm.reset();
  channelDialog.showModal();
});
channelCancel.addEventListener("click", () => channelDialog.close());

channelForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const created = await fetchJSON("/api/channels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("ch-name").value.trim(),
        type: document.getElementById("ch-type").value,
      }),
    });
    await loadChannels(created.id);
    channelDialog.close();
  } catch (err) {
    toast(errorMessage(err), "error");
  }
});

async function loadCustomers(selectId) {
  const customers = await fetchJSON("/api/customers");
  customerSelect.innerHTML = '<option value="">Sin cliente</option>';
  for (const c of customers) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    customerSelect.appendChild(opt);
  }
  if (selectId) customerSelect.value = selectId;
}

btnNewCustomer.addEventListener("click", () => {
  customerForm.reset();
  customerDialog.showModal();
});
customerCancel.addEventListener("click", () => customerDialog.close());

customerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const created = await fetchJSON("/api/customers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("c-name").value.trim(),
        phone: document.getElementById("c-phone").value.trim(),
        email: document.getElementById("c-email").value.trim(),
      }),
    });
    await loadCustomers(created.id);
    customerDialog.close();
  } catch (err) {
    toast(errorMessage(err), "error");
  }
});

let searchTimer;
productSearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = productSearch.value.trim();
  if (!q) {
    productResults.classList.add("hidden");
    return;
  }
  searchTimer = setTimeout(async () => {
    const products = await fetchJSON(`/api/products?q=${encodeURIComponent(q)}`);
    renderResults(products);
  }, 250);
});

function renderResults(products) {
  productResults.innerHTML = "";
  if (!products.length) {
    productResults.innerHTML = '<div class="empty">Sin resultados.</div>';
    productResults.classList.remove("hidden");
    return;
  }
  for (const p of products) {
    const row = document.createElement("div");
    row.className = "product-result-row";
    row.innerHTML = `
      <span>${escapeHtml(p.name)} <span class="card-sku">SKU: ${escapeHtml(p.sku)}</span><br>
        <span class="card-sku">${money(p.price)} &middot; stock ${p.quantity}</span></span>
      <button type="button" class="btn-secondary">+ Agregar</button>
    `;
    row.addEventListener("click", () => {
      addToCart(p);
      productSearch.value = "";
      productResults.classList.add("hidden");
    });
    productResults.appendChild(row);
  }
  productResults.classList.remove("hidden");
}

function addToCart(product) {
  const existing = cart.find((i) => i.sku === product.sku);
  if (existing) {
    if (existing.quantity < existing.maxStock) existing.quantity += 1;
  } else {
    cart.push({ sku: product.sku, name: product.name, price: product.price, quantity: 1, maxStock: product.quantity });
  }
  renderCart();
}

function renderCart() {
  cartBody.innerHTML = "";
  cartEmpty.classList.toggle("hidden", cart.length > 0);
  cart.forEach((item, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(item.name)}<div class="card-sku">SKU: ${escapeHtml(item.sku)}</div></td>
      <td><input type="number" min="1" max="${item.maxStock}" value="${item.quantity}" class="qty-input" data-idx="${idx}"></td>
      <td><input type="number" min="0" step="0.01" value="${item.price}" class="price-input" data-idx="${idx}"></td>
      <td class="line-total">${money(item.price * item.quantity)}</td>
      <td><button type="button" class="remove-item" data-idx="${idx}">x</button></td>
    `;
    cartBody.appendChild(tr);
  });

  cartBody.querySelectorAll(".qty-input").forEach((input) => {
    input.addEventListener("input", () => {
      const idx = Number(input.dataset.idx);
      cart[idx].quantity = Math.max(1, Math.min(Number(input.value) || 1, cart[idx].maxStock));
      renderCart();
    });
  });
  cartBody.querySelectorAll(".price-input").forEach((input) => {
    input.addEventListener("input", () => {
      const idx = Number(input.dataset.idx);
      cart[idx].price = Math.max(0, Number(input.value) || 0);
      renderTotals();
      const totalCell = cartBody.rows[idx].querySelector(".line-total");
      if (totalCell) totalCell.textContent = money(cart[idx].price * cart[idx].quantity);
    });
  });
  cartBody.querySelectorAll(".remove-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      cart.splice(Number(btn.dataset.idx), 1);
      renderCart();
    });
  });

  renderTotals();
}

function renderTotals() {
  const subtotal = cart.reduce((sum, i) => sum + i.price * i.quantity, 0);
  const discount = Number(discountInput.value) || 0;
  totalSubtotalEl.textContent = money(subtotal);
  totalTotalEl.textContent = money(Math.max(0, subtotal - discount));
}

discountInput.addEventListener("input", renderTotals);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.classList.add("hidden");

  if (!cart.length) {
    formError.textContent = "Agrega al menos un producto.";
    formError.classList.remove("hidden");
    return;
  }

  const payload = {
    channel_id: Number(channelSelect.value),
    customer_id: customerSelect.value || null,
    discount: Number(discountInput.value) || 0,
    payment_method: document.getElementById("f-payment").value,
    note: document.getElementById("f-note").value.trim(),
    items: cart.map((i) => ({ sku: i.sku, quantity: i.quantity, unit_price: i.price })),
  };

  try {
    const sale = await fetchJSON("/api/sales", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    window.location.href = `/ventas/${sale.id}`;
  } catch (err) {
    formError.textContent = errorMessage(err);
    formError.classList.remove("hidden");
  }
});

loadChannels();
loadCustomers();
renderCart();
