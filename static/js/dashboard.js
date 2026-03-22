const socket = io();
let currentSymbol = "BTCUSDT";
let appState = { signals: [], bias: {}, order_blocks: {}, fvgs: {}, stats: {}, last_update: null };

// ── WebSocket ────────────────────────────────────────────────────────────────

socket.on("connect", () => {
  document.getElementById("last-update").textContent = "Bağlandı";
});

socket.on("disconnect", () => {
  document.getElementById("last-update").textContent = "Bağlantı kesildi";
});

socket.on("update", (data) => {
  appState = { ...appState, ...data };
  renderAll();
  document.getElementById("last-update").textContent = "Son: " + (data.last_update || "--");
});

socket.on("symbol_analysis", (data) => {
  renderAnalysisDetail(data);
});

// ── Navigation ───────────────────────────────────────────────────────────────

function showPage(name) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  document.getElementById("page-" + name).classList.add("active");
  document.getElementById("page-title").textContent = {
    dashboard: "Dashboard",
    signals: "Sinyaller",
    analysis: "Analiz",
    trades: "Trade Geçmişi"
  }[name];
  event.target.closest(".nav-item").classList.add("active");
}

function selectSymbol(sym) {
  currentSymbol = sym;
  document.querySelectorAll(".sym-btn").forEach(b => {
    b.classList.toggle("active", b.textContent === sym.replace("USDT", ""));
  });
  document.getElementById("ob-symbol").textContent = sym;
  document.getElementById("an-symbol").textContent = sym;
  renderOBList();
  renderFVGList();
}

function requestAnalysis() {
  socket.emit("request_analysis", { symbol: currentSymbol });
  document.getElementById("analysis-detail").innerHTML = '<div class="empty-state">Analiz yapılıyor...</div>';
}

// ── Render fonksiyonları ─────────────────────────────────────────────────────

function renderAll() {
  renderMetrics();
  renderSignalsList();
  renderBiasList();
  renderOBList();
  renderScoreBars();
  renderSignalsTable();
  renderBiasTable();
  renderFVGList();
  renderTradeStats();
}

function renderMetrics() {
  const s = appState.stats;
  const signals = appState.signals || [];

  document.getElementById("m-balance").textContent = "$" + (s.balance || 1000).toLocaleString();
  const pnl = s.daily_pnl || 0;
  const pnlEl = document.getElementById("m-pnl");
  pnlEl.textContent = (pnl >= 0 ? "+" : "") + "$" + pnl.toFixed(2);
  pnlEl.className = "metric-value " + (pnl >= 0 ? "green" : "red");

  const wr = s.win_rate || 0;
  document.getElementById("m-winrate").textContent = wr.toFixed(0) + "%";
  document.getElementById("m-winrate-sub").textContent = `${s.wins || 0} / ${s.total_trades || 0} trade`;
  document.getElementById("m-signals").textContent = signals.length;
  document.getElementById("m-pnl-sub").textContent = (s.total_trades || 0) + " trade bugün";
}

function renderSignalsList() {
  const el = document.getElementById("signals-list");
  const signals = appState.signals || [];

  if (!signals.length) {
    el.innerHTML = '<div class="empty-state">Sinyal bekleniyor...</div>';
    return;
  }

  el.innerHTML = signals.slice(-5).reverse().map(s => `
    <div class="sig-row">
      <div class="sig-left">
        <span class="dir ${s.direction === "LONG" ? "long" : "short"}">${s.direction}</span>
        <div>
          <div class="sig-sym">${s.symbol}</div>
          <div class="sig-conf">${(s.reasons || []).join(" · ")}</div>
        </div>
      </div>
      <div class="sig-right">
        <div class="sig-rr">RR 1:${s.rr}</div>
        <div class="sig-time">${s.time || "--"}</div>
      </div>
    </div>
  `).join("");
}

function renderBiasList() {
  const el = document.getElementById("bias-list");
  const bias = appState.bias || {};
  const keys = Object.keys(bias);

  if (!keys.length) {
    el.innerHTML = '<div class="empty-state">Veri yükleniyor...</div>';
    return;
  }

  el.innerHTML = keys.map(sym => {
    const b = bias[sym];
    const badgeCls = b.bias === "bullish" ? "bull" : b.bias === "bearish" ? "bear" : "neutral";
    const badgeText = b.bias === "bullish" ? "Bullish" : b.bias === "bearish" ? "Bearish" : "Nötr";
    return `
      <div class="bias-row">
        <span style="font-weight:600;">${sym.replace("USDT","")}</span>
        <div style="display:flex;align-items:center;gap:6px;">
          <span class="zone-badge">${b.zone || ""}</span>
          <span class="bias-badge ${badgeCls}">${badgeText}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderOBList() {
  const el = document.getElementById("ob-list");
  const obs = (appState.order_blocks || {})[currentSymbol];

  if (!obs) {
    el.innerHTML = '<div class="empty-state">Veri bekleniyor</div>';
    return;
  }

  const bullish = (obs.bullish || []).map(o => `
    <div class="ob-row">
      <div><span class="ob-dot ob-green"></span><span style="font-weight:500;">Bullish OB</span></div>
      <div class="ob-price">${o.bottom} — ${o.top}</div>
    </div>
  `).join("");

  const bearish = (obs.bearish || []).map(o => `
    <div class="ob-row">
      <div><span class="ob-dot ob-red"></span><span style="font-weight:500;">Bearish OB</span></div>
      <div class="ob-price">${o.bottom} — ${o.top}</div>
    </div>
  `).join("");

  el.innerHTML = bullish + bearish || '<div class="empty-state">OB bulunamadı</div>';
}

function renderFVGList() {
  const el = document.getElementById("fvg-list");
  const fvgs = (appState.fvgs || {})[currentSymbol];

  if (!fvgs) {
    el.innerHTML = '<div class="empty-state">Veri bekleniyor</div>';
    return;
  }

  const bullish = (fvgs.bullish || []).map(f => `
    <div class="ob-row">
      <div><span class="ob-dot ob-green"></span><span style="font-weight:500;">Bullish FVG</span></div>
      <div class="ob-price">${f.bottom} — ${f.top}</div>
    </div>
  `).join("");

  const bearish = (fvgs.bearish || []).map(f => `
    <div class="ob-row">
      <div><span class="ob-dot ob-red"></span><span style="font-weight:500;">Bearish FVG</span></div>
      <div class="ob-price">${f.bottom} — ${f.top}</div>
    </div>
  `).join("");

  el.innerHTML = bullish + bearish || '<div class="empty-state">FVG bulunamadı</div>';
}

function renderScoreBars() {
  const signals = appState.signals || [];
  const counts = { 4: 0, 3: 0, 2: 0 };
  signals.forEach(s => { if (counts[s.score] !== undefined) counts[s.score]++; });
  const max = Math.max(...Object.values(counts), 1);

  [4, 3, 2].forEach(n => {
    const bar = document.getElementById("bar-" + n);
    const val = document.getElementById("bv-" + n);
    if (bar) bar.style.width = (counts[n] / max * 100) + "%";
    if (val) val.textContent = counts[n];
  });
}

function renderSignalsTable() {
  const tbody = document.getElementById("signals-tbody");
  const signals = appState.signals || [];

  if (!signals.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Sinyal bekleniyor...</td></tr>';
    return;
  }

  tbody.innerHTML = signals.slice().reverse().map(s => {
    const dots = [1,2,3,4].map(i =>
      `<div class="sdot ${i <= s.score ? 'on' : ''}"></div>`
    ).join("");
    return `
      <tr>
        <td style="font-weight:600;">${s.symbol}</td>
        <td><span class="dir ${s.direction === "LONG" ? "long" : "short"}">${s.direction}</span></td>
        <td>${s.price}</td>
        <td style="color:var(--red)">${s.sl}</td>
        <td style="color:var(--green)">${s.tp}</td>
        <td style="font-weight:600;">1:${s.rr}</td>
        <td><div class="score-dots">${dots}</div></td>
        <td style="color:var(--text2);font-size:11px;">${(s.reasons || []).join(", ")}</td>
        <td style="color:var(--text3)">${s.time || "--"}</td>
      </tr>
    `;
  }).join("");
}

function renderBiasTable() {
  const tbody = document.getElementById("bias-tbody");
  const bias = appState.bias || {};
  const keys = Object.keys(bias);

  if (!keys.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Yükleniyor...</td></tr>';
    return;
  }

  tbody.innerHTML = keys.map(sym => {
    const b = bias[sym];
    const bc = b.bias === "bullish" ? "bull" : b.bias === "bearish" ? "bear" : "neutral";
    const lbc = b.ltf_bias === "bullish" ? "bull" : b.ltf_bias === "bearish" ? "bear" : "neutral";
    return `
      <tr>
        <td style="font-weight:600;">${sym}</td>
        <td>${b.price ? b.price.toLocaleString() : "--"}</td>
        <td><span class="bias-badge ${bc}">${b.bias}</span></td>
        <td><span class="zone-badge">${b.zone || "--"}</span></td>
        <td><span class="bias-badge ${lbc}">${b.ltf_bias || "--"}</span></td>
      </tr>
    `;
  }).join("");
}

function renderAnalysisDetail(data) {
  const el = document.getElementById("analysis-detail");
  if (!data || !data.symbol) {
    el.innerHTML = '<div class="empty-state">Veri alınamadı</div>';
    return;
  }

  const biasCls = data.bias === "bullish" ? "bull" : data.bias === "bearish" ? "bear" : "neutral";

  el.innerHTML = `
    <div class="detail-row">
      <span class="detail-key">Sembol</span>
      <span class="detail-val">${data.symbol}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Mevcut fiyat</span>
      <span class="detail-val">${(data.price || 0).toLocaleString()}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">HTF Bias</span>
      <span class="bias-badge ${biasCls}">${data.bias || "--"}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">LTF Bias</span>
      <span class="detail-val">${data.ltf_bias || "--"}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Zone</span>
      <span class="zone-badge">${data.zone || "--"}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">ATR</span>
      <span class="detail-val">${data.atr || "--"}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Bullish OB sayısı</span>
      <span class="detail-val">${(data.bullish_obs || []).length}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Bearish OB sayısı</span>
      <span class="detail-val">${(data.bearish_obs || []).length}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Bullish FVG</span>
      <span class="detail-val">${(data.bullish_fvgs || []).length}</span>
    </div>
    <div class="detail-row">
      <span class="detail-key">Bearish FVG</span>
      <span class="detail-val">${(data.bearish_fvgs || []).length}</span>
    </div>
    ${data.signal ? `
    <div style="margin-top:12px;padding:10px;background:var(--green-bg);border-radius:8px;">
      <div style="font-weight:600;color:var(--green);margin-bottom:6px;">
        ✓ ${data.signal.direction} sinyali — Score: ${data.signal.score}
      </div>
      <div style="font-size:11px;color:var(--text2);">${(data.signal.reasons || []).join(" · ")}</div>
    </div>` : ""}
  `;

  // FVG listesi de güncelle
  if (data.symbol === currentSymbol && appState.fvgs) {
    appState.fvgs[data.symbol] = {
      bullish: data.bullish_fvgs || [],
      bearish: data.bearish_fvgs || []
    };
    renderFVGList();
  }
}

function renderTradeStats() {
  const s = appState.stats || {};
  document.getElementById("t-total").textContent = s.total_trades || 0;
  document.getElementById("t-wins").textContent = s.wins || 0;
  document.getElementById("t-losses").textContent = s.losses || 0;
  const pnl = s.daily_pnl || 0;
  const pnlEl = document.getElementById("t-pnl");
  pnlEl.textContent = (pnl >= 0 ? "+" : "") + "$" + pnl.toFixed(2);
  pnlEl.className = "metric-value " + (pnl >= 0 ? "green" : "red");
}

// ── Başlangıç ────────────────────────────────────────────────────────────────

fetch("/api/state")
  .then(r => r.json())
  .then(data => {
    appState = { ...appState, ...data };
    renderAll();
  })
  .catch(() => {});
