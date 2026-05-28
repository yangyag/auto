from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["ops"])


OPS_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>auto API 점검</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --line: #d9dee7;
      --text: #161b22;
      --muted: #637083;
      --accent: #1769aa;
      --ok: #167a3a;
      --warn: #9a6700;
      --bad: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.45;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--surface);
      padding: 18px 20px;
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 17px; letter-spacing: 0; }
    p { margin: 6px 0; color: var(--muted); }
    section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 10px;
    }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      color: var(--text);
      background: #fff;
    }
    button {
      border: 1px solid #14558a;
      background: var(--accent);
      color: #fff;
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      cursor: pointer;
      min-height: 40px;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
      border-color: var(--accent);
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 13px;
      background: #edf1f7;
      color: var(--muted);
    }
    .status.ok { background: #e8f5ec; color: var(--ok); }
    .status.warn { background: #fff7df; color: var(--warn); }
    .status.bad { background: #fdecec; color: var(--bad); }
    .facts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .fact {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 72px;
      background: #fbfcfe;
    }
    .fact span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .fact strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 18px;
      font-weight: 650;
    }
    .table-wrap {
      margin-top: 12px;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    table {
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }
    th {
      color: var(--muted);
      font-weight: 650;
      background: #f8fafc;
    }
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2),
    th:last-child, td:last-child {
      text-align: left;
    }
    tr:last-child td { border-bottom: 0; }
    tr.holding { background: #f7fcf8; }
    .slot-status {
      display: inline-flex;
      min-width: 44px;
      justify-content: center;
      border-radius: 999px;
      padding: 2px 7px;
      color: var(--muted);
      background: #edf1f7;
    }
    .slot-status.holding {
      color: var(--ok);
      background: #e8f5ec;
    }
    pre {
      margin: 0;
      min-height: 220px;
      max-height: 520px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #0f1720;
      color: #e6edf3;
      font-size: 13px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    @media (max-width: 640px) {
      main { padding: 12px; }
      header { padding: 14px 12px; }
      h1 { font-size: 21px; }
      button { width: 100%; }
      .actions { align-items: stretch; }
    }
  </style>
</head>
<body>
  <header>
    <h1>auto API 점검</h1>
    <p>모바일 API를 같은 FastAPI 서버에서 바로 확인하는 읽기 전용 화면입니다.</p>
  </header>
  <main>
    <section>
      <h2>접속 정보</h2>
      <div class="grid">
        <label>API 기본 주소
          <input id="baseUrl" autocomplete="off">
        </label>
        <label>아이디
          <input id="username" autocomplete="username" placeholder="admin">
        </label>
        <label>비밀번호
          <input id="password" type="password" autocomplete="current-password">
        </label>
        <label>TOTP 코드
          <input id="totpCode" inputmode="numeric" autocomplete="one-time-code" placeholder="선택 사항">
        </label>
      </div>
      <div class="actions">
        <button id="loginBtn" type="button">로그인</button>
        <button id="logoutBtn" class="secondary" type="button">토큰 지우기</button>
        <button id="healthBtn" class="secondary" type="button">상태 확인</button>
        <span id="authStatus" class="status">로그인 전</span>
      </div>
    </section>

    <section>
      <h2>빠른 조회</h2>
      <div class="actions">
        <button data-path="/v1/bot/status" type="button">봇 상태</button>
        <button data-path="/v1/grid/summary" type="button">그리드 요약</button>
        <button data-path="/v1/grid/state" type="button">그리드 전체</button>
        <button data-path="/v1/market/price" type="button">현재가</button>
        <button data-path="/v1/orders/pending" type="button">미체결 주문</button>
        <button data-path="/v1/monitor/open-sells" type="button">매도 대기</button>
        <button data-path="/v1/config" type="button">설정</button>
      </div>
      <div class="actions" style="margin-top: 10px;">
        <label style="max-width: 180px; margin: 0;">손익 기간
          <select id="pnlPeriod">
            <option value="d">오늘</option>
            <option value="w">이번 주</option>
            <option value="m">이번 달</option>
            <option value="y">올해</option>
            <option value="all">전체</option>
          </select>
        </label>
        <button id="pnlBtn" type="button">실현손익</button>
      </div>
      <div id="facts" class="facts"></div>
      <div id="gridTableWrap" class="table-wrap" hidden></div>
      <div id="monitorTableWrap" class="table-wrap" hidden></div>
    </section>

    <section>
      <h2>응답</h2>
      <pre id="output">아직 요청하지 않았습니다.</pre>
    </section>
  </main>

  <script>
    const baseUrlInput = document.getElementById("baseUrl");
    const usernameInput = document.getElementById("username");
    const passwordInput = document.getElementById("password");
    const totpInput = document.getElementById("totpCode");
    const output = document.getElementById("output");
    const authStatus = document.getElementById("authStatus");
    const facts = document.getElementById("facts");
    const gridTableWrap = document.getElementById("gridTableWrap");
    const monitorTableWrap = document.getElementById("monitorTableWrap");

    baseUrlInput.value = window.location.origin;
    usernameInput.value = window.localStorage.getItem("autoOpsUsername") || "admin";

    function token() {
      return window.sessionStorage.getItem("autoOpsAccessToken") || "";
    }

    function setStatus(text, kind) {
      authStatus.textContent = text;
      authStatus.className = "status" + (kind ? " " + kind : "");
    }

    function show(value) {
      output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function showFacts(items) {
      facts.innerHTML = "";
      for (const item of items) {
        const node = document.createElement("div");
        node.className = "fact";
        const label = document.createElement("span");
        label.textContent = item.label;
        const value = document.createElement("strong");
        value.textContent = item.value == null ? "-" : String(item.value);
        node.append(label, value);
        facts.appendChild(node);
      }
    }

    function clearGridTable() {
      gridTableWrap.hidden = true;
      gridTableWrap.innerHTML = "";
    }

    function clearMonitorTable() {
      monitorTableWrap.hidden = true;
      monitorTableWrap.innerHTML = "";
    }

    function valueOrDash(value) {
      return value == null || value === "" ? "-" : String(value);
    }

    function formatKrw(value) {
      if (value == null || value === "") {
        return "-";
      }
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return String(value);
      }
      return new Intl.NumberFormat("ko-KR", {maximumFractionDigits: 0}).format(number);
    }

    function slotStatusLabel(status) {
      if (status === "holding") {
        return "보유";
      }
      if (status === "empty") {
        return "대기";
      }
      return valueOrDash(status);
    }

    function pendingOrderText(order, baseCurrency = "BTC") {
      if (!order) {
        return "-";
      }
      const rawSide = String(order.side || "").toLowerCase();
      const side = rawSide === "buy" ? "매수" : rawSide === "sell" ? "매도" : valueOrDash(order.side);
      const status = order.status || "open";
      const amount = order.spend_amount ? formatKrw(order.spend_amount) + " KRW" : valueOrDash(order.quantity) + " " + baseCurrency;
      return side + " " + status + " " + amount;
    }

    function appendCell(row, text, className) {
      const cell = document.createElement("td");
      if (className) {
        cell.className = className;
      }
      cell.textContent = text;
      row.appendChild(cell);
    }

    function renderMonitorTable(data) {
      const rows = data.rows || [];
      monitorTableWrap.innerHTML = "";
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      const market = data.market || "KRW-BTC";
      const baseCurrency = market.includes("-") ? market.split("-")[1].toUpperCase() : market.toUpperCase();
      const headers = [
        "슬롯", `수량(${baseCurrency})`, "매수원가", "매도지정가",
        "현재가", "미실현손익", "도달까지"
      ];
      for (const header of headers) {
        const cell = document.createElement("th");
        cell.textContent = header;
        headerRow.appendChild(cell);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      for (const row of rows) {
        const tr = document.createElement("tr");
        appendCell(tr, valueOrDash(row.slot_index));
        appendCell(tr, valueOrDash(row.qty));
        appendCell(tr, formatKrw(row.buy_unit_cost));
        appendCell(tr, formatKrw(row.sell_limit_price));
        appendCell(tr, formatKrw(row.current_price));

        const pnlCell = document.createElement("td");
        const unrealized = row.unrealized_at_current;
        if (unrealized == null) {
          pnlCell.textContent = "-";
        } else {
          pnlCell.textContent = formatKrw(unrealized);
          pnlCell.style.color = Number(unrealized) >= 0 ? "#167a3a" : "#b42318";
        }
        tr.appendChild(pnlCell);

        const gapKrW = row.gap_to_fill_krw;
        const gapCell = document.createElement("td");
        if (gapKrW == null) {
          gapCell.textContent = "-";
        } else {
          const gapNum = Number(gapKrW);
          if (gapNum > 0) {
            gapCell.textContent = formatKrw(gapKrW) + " 남음";
          } else if (gapNum === 0) {
            gapCell.textContent = "근접";
          } else {
            gapCell.textContent = "즉시체결 가능 (" + formatKrw(Math.abs(gapNum)) + ")";
          }
        }
        tr.appendChild(gapCell);

        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      monitorTableWrap.appendChild(table);
      monitorTableWrap.hidden = false;
    }

    function renderGridTable(data) {
      const slots = data.slots || [];
      gridTableWrap.innerHTML = "";
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      const symbol = data.symbol || "KRW-BTC";
      const baseCurrency = symbol.includes("-") ? symbol.split("-")[1].toUpperCase() : symbol.toUpperCase();
      const headers = [
        "슬롯", "상태", "매수가", `계획 ${baseCurrency}`, "계획 매수(KRW)",
        `보유 ${baseCurrency}`, "보유 원가(KRW)", "매도가", "유효 매도가", "미체결"
      ];
      for (const header of headers) {
        const cell = document.createElement("th");
        cell.textContent = header;
        headerRow.appendChild(cell);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      for (const slot of slots) {
        const row = document.createElement("tr");
        row.className = slot.status === "holding" ? "holding" : "";
        appendCell(row, valueOrDash(slot.slot_index));

        const statusCell = document.createElement("td");
        const statusBadge = document.createElement("span");
        statusBadge.className = "slot-status" + (slot.status === "holding" ? " holding" : "");
        statusBadge.textContent = slotStatusLabel(slot.status);
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);

        appendCell(row, formatKrw(slot.buy_price));
        appendCell(row, valueOrDash(slot.planned_qty));
        appendCell(row, formatKrw(slot.planned_buy_krw));
        appendCell(row, valueOrDash(slot.held_qty));
        appendCell(row, formatKrw(slot.inventory_cost_krw));
        appendCell(row, formatKrw(slot.sell_price));
        appendCell(row, formatKrw(slot.effective_sell_price));
        appendCell(row, pendingOrderText(slot.pending_order, baseCurrency));
        tbody.appendChild(row);
      }
      table.appendChild(tbody);
      gridTableWrap.appendChild(table);
      gridTableWrap.hidden = false;
    }

    async function request(path, options = {}) {
      const base = baseUrlInput.value.replace(/\\/$/, "");
      const headers = Object.assign({"Content-Type": "application/json"}, options.headers || {});
      if (options.auth !== false && token()) {
        headers.Authorization = "Bearer " + token();
      }
      const response = await fetch(base + path, Object.assign({}, options, {headers}));
      const text = await response.text();
      let data = text;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (_) {
        data = text;
      }
      if (!response.ok) {
        const message = typeof data === "string" ? data : JSON.stringify(data, null, 2);
        throw new Error("HTTP " + response.status + "\\n" + message);
      }
      return data;
    }

    async function run(name, callback) {
      clearGridTable();
      clearMonitorTable();
      show(name + "...");
      try {
        const data = await callback();
        show(data);
        return data;
      } catch (error) {
        show(error.message || String(error));
        throw error;
      }
    }

    document.getElementById("loginBtn").addEventListener("click", async () => {
      await run("로그인", async () => {
        const payload = {
          username: usernameInput.value,
          password: passwordInput.value,
          totp_code: totpInput.value || null
        };
        const data = await request("/v1/auth/login", {
          method: "POST",
          auth: false,
          body: JSON.stringify(payload)
        });
        window.sessionStorage.setItem("autoOpsAccessToken", data.access_token);
        window.sessionStorage.setItem("autoOpsRefreshToken", data.refresh_token);
        window.localStorage.setItem("autoOpsUsername", usernameInput.value);
        setStatus("로그인됨", "ok");
        return Object.assign({}, data, {
          access_token: data.access_token ? "[브라우저 세션에 저장됨]" : null,
          refresh_token: data.refresh_token ? "[브라우저 세션에 저장됨]" : null
        });
      });
    });

    document.getElementById("logoutBtn").addEventListener("click", () => {
      window.sessionStorage.removeItem("autoOpsAccessToken");
      window.sessionStorage.removeItem("autoOpsRefreshToken");
      setStatus("로그인 전", "");
      show("이 브라우저 세션의 토큰을 지웠습니다.");
      showFacts([]);
    });

    document.getElementById("healthBtn").addEventListener("click", () => {
      run("상태 확인", () => request("/health", {auth: false}));
    });

    for (const button of document.querySelectorAll("button[data-path]")) {
      button.addEventListener("click", async () => {
        const data = await run(button.textContent, () => request(button.dataset.path));
        if (button.dataset.path === "/v1/bot/status") {
          showFacts([
            {label: "봇 실행 여부", value: data.is_alive},
            {label: "마켓", value: data.symbol},
            {label: "지연 시간(초)", value: data.lag_seconds},
            {label: "현재가", value: data.current_price}
          ]);
        } else if (button.dataset.path === "/v1/grid/summary") {
          const symbol = data.symbol || "KRW-BTC";
          const baseCurrency = symbol.includes("-") ? symbol.split("-")[1].toUpperCase() : symbol.toUpperCase();
          showFacts([
            {label: "행 수", value: data.row_count},
            {label: "보유 칸 수", value: data.holding_count},
            {label: `보유 ${baseCurrency}`, value: data.total_inventory_btc},
            {label: "보유 원가(KRW)", value: data.current_inventory_cost_krw}
          ]);
        } else if (button.dataset.path === "/v1/grid/state") {
          const slots = data.slots || [];
          const holdingCount = slots.filter((slot) => slot.status === "holding").length;
          showFacts([
            {label: "마켓", value: data.symbol},
            {label: "슬롯 수", value: slots.length},
            {label: "보유 슬롯", value: holdingCount},
            {label: "대기 슬롯", value: slots.length - holdingCount}
          ]);
          renderGridTable(data);
        } else if (button.dataset.path === "/v1/market/price") {
          showFacts([
            {label: "마켓", value: data.symbol},
            {label: "가격", value: data.price},
            {label: "출처", value: data.source},
            {label: "확인 시각", value: data.observed_at}
          ]);
        } else if (button.dataset.path === "/v1/monitor/open-sells") {
          const summary = data.summary || {};
          const diagnostic = data.diagnostic || {};
          showFacts([
            {label: "마켓", value: data.market},
            {label: "현재가", value: formatKrw(data.current_price)},
            {label: "총 주문", value: summary.total_count},
            {label: "매칭/미매칭", value: (summary.matched_count || 0) + " / " + (summary.unmatched_count || 0)},
            {label: "수익권/손실권", value: (summary.profit_count || 0) + " / " + (summary.loss_count || 0)},
            {label: "총 미실현손익", value: formatKrw(summary.total_unrealized_krw)}
          ]);
          renderMonitorTable(data);
        }
      });
    }

    document.getElementById("pnlBtn").addEventListener("click", async () => {
      const period = document.getElementById("pnlPeriod").value;
      const data = await run("실현손익", () => request("/v1/pnl/realized?period=" + encodeURIComponent(period)));
      const first = data.buckets && data.buckets[0] ? data.buckets[0] : {};
      const market = data.market || "KRW-BTC";
      const baseCurrency = market.includes("-") ? market.split("-")[1].toUpperCase() : market.toUpperCase();
      showFacts([
        {label: "기간", value: data.period},
        {label: "구간", value: first.key},
        {label: "실현손익(KRW)", value: first.realized_pnl_krw},
        {label: `매칭 ${baseCurrency}`, value: first.matched_qty_btc}
      ]);
    });

    setStatus(token() ? "세션 토큰 불러옴" : "로그인 전", token() ? "ok" : "");
  </script>
</body>
</html>
"""


@router.get("/ops", response_class=HTMLResponse, include_in_schema=False)
def ops_dashboard() -> HTMLResponse:
    return HTMLResponse(OPS_DASHBOARD_HTML)
