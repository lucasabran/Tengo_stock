const tilesArsEl = document.getElementById("tiles-ars");
const tilesUsdEl = document.getElementById("tiles-usd");
const usdSection = document.getElementById("usd-section");
const recentEl = document.getElementById("recent-sales");
const sparklineArsEl = document.getElementById("sparkline-ars");
const sparklineUsdEl = document.getElementById("sparkline-usd");
const topProductsEl = document.getElementById("top-products");
const lowStockEl = document.getElementById("low-stock");

function tile(label, value, opts = {}) {
  const div = document.createElement("div");
  div.className = "tile" + (opts.warn ? " tile-warn" : "");
  div.innerHTML = `<div class="tile-label">${escapeHtml(label)}</div><div class="tile-value">${value}</div>`;
  if (opts.href) {
    const a = document.createElement("a");
    a.href = opts.href;
    a.className = "tile-link";
    a.appendChild(div);
    return a;
  }
  return div;
}

function renderSparkline(container, days, currency) {
  const max = Math.max(1, ...days.map((d) => d.total));
  const width = 700;
  const height = 120;
  const barGap = 12;
  const barWidth = (width - barGap * (days.length - 1)) / days.length;

  const bars = days
    .map((d, i) => {
      const barHeight = Math.max(2, (d.total / max) * (height - 24));
      const x = i * (barWidth + barGap);
      const y = height - barHeight;
      const label = new Date(d.date + "T00:00:00").toLocaleDateString("es-AR", { weekday: "short" });
      return `
        <g>
          <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="${currency === "USD" ? "var(--success)" : "var(--accent)"}"></rect>
          <text x="${x + barWidth / 2}" y="${height + 16}" text-anchor="middle" class="sparkline-label">${label}</text>
        </g>
      `;
    })
    .join("");

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height + 24}" preserveAspectRatio="xMidYMid meet" class="sparkline-svg">${bars}</svg>
  `;
}

function renderTopProducts(products) {
  if (!products.length) {
    topProductsEl.innerHTML = '<div class="empty">Todavia no hay ventas para mostrar.</div>';
    return;
  }
  topProductsEl.innerHTML = products
    .map(
      (p) => `
        <div class="list-row">
          <div>
            <div class="list-row-title">${escapeHtml(p.name)}</div>
            <div class="list-row-sub">SKU: ${escapeHtml(p.sku)}</div>
          </div>
          <div class="list-row-amount">${p.quantity} u.</div>
        </div>
      `
    )
    .join("");
}

function renderLowStock(products) {
  if (!products.length) {
    lowStockEl.innerHTML = '<div class="empty">Todo el stock esta en buen nivel.</div>';
    return;
  }
  lowStockEl.innerHTML = products
    .map(
      (p) => `
        <a class="list-row" href="/stock">
          <div>
            <div class="list-row-title">${escapeHtml(p.name)}</div>
            <div class="list-row-sub">SKU: ${escapeHtml(p.sku)}</div>
          </div>
          <div class="list-row-amount movement-negative">${p.quantity} u.</div>
        </a>
      `
    )
    .join("");
}

async function load() {
  let data;
  try {
    data = await fetchJSON("/api/dashboard/summary");
  } catch (err) {
    tilesArsEl.innerHTML = `<div class="empty">${escapeHtml(errorMessage(err))}</div>`;
    return;
  }

  const ars = data.ars;
  tilesArsEl.innerHTML = "";
  tilesArsEl.appendChild(tile("Ventas de hoy", `${money(ars.sales_today_total)} <span class="tile-sub">(${ars.sales_today_count})</span>`));
  tilesArsEl.appendChild(tile("Ventas del mes", money(ars.sales_month_total)));
  tilesArsEl.appendChild(tile("Gastos del mes", money(ars.expenses_month_total)));
  tilesArsEl.appendChild(tile("Balance del mes", money(ars.balance_month), { warn: ars.balance_month < 0 }));
  tilesArsEl.appendChild(tile("Stock bajo", data.low_stock_count, { warn: data.low_stock_count > 0, href: "/stock" }));
  renderSparkline(sparklineArsEl, ars.sales_last_7_days, "ARS");

  const usd = data.usd;
  const hasUsdActivity =
    usd.sales_today_total > 0 || usd.sales_month_total > 0 || usd.sales_last_7_days.some((d) => d.total > 0);
  usdSection.classList.toggle("hidden", !hasUsdActivity);
  if (hasUsdActivity) {
    tilesUsdEl.innerHTML = "";
    tilesUsdEl.appendChild(tile("Ventas de hoy", `${money(usd.sales_today_total, "USD")} <span class="tile-sub">(${usd.sales_today_count})</span>`));
    tilesUsdEl.appendChild(tile("Ventas del mes", money(usd.sales_month_total, "USD")));
    renderSparkline(sparklineUsdEl, usd.sales_last_7_days, "USD");
  }

  renderTopProducts(data.top_products);
  renderLowStock(data.low_stock_products);

  if (!data.recent_sales.length) {
    recentEl.innerHTML = '<div class="empty">Todavia no hay ventas registradas.</div>';
    return;
  }
  recentEl.innerHTML = "";
  for (const s of data.recent_sales) {
    const row = document.createElement("a");
    row.className = "list-row";
    row.href = `/ventas/${s.id}`;
    row.innerHTML = `
      <div>
        <div class="list-row-title">${escapeHtml(s.number)} &middot; ${escapeHtml(s.channel_name)}</div>
        <div class="list-row-sub">${escapeHtml(s.customer_name || "Sin cliente")} &middot; ${formatDateTime(s.created_at)}</div>
      </div>
      <div class="list-row-amount">${money(s.total, s.currency)}</div>
    `;
    recentEl.appendChild(row);
  }
}

load();
