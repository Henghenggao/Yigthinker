// Yigthinker Dashboard — Single-Page Conversation App
// Connects to Gateway WebSocket at /ws using the same protocol as TUI.

(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────────
  const state = {
    ws: null,
    token: localStorage.getItem("yig_token") || "",
    sessionKey: localStorage.getItem("yig_session") || "default",
    sessions: [],
    vars: [],
    messages: [],       // {role, content, toolCards: [...]}
    streaming: false,
    streamBuffer: "",
    connected: false,
    authenticated: false,
  };

  // ── Markdown rendering (lightweight) ───────────────────────────────────────
  function renderMarkdown(text) {
    // Escape HTML
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
      return '<pre><code class="lang-' + lang + '">' + code.trim() + "</code></pre>";
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // Italic
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    // Headers
    html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");

    // Tables (simple)
    html = html.replace(
      /(?:^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)*))/gm,
      function (_, headerRow, sepRow, bodyRows) {
        var headers = headerRow.split("|").filter(function (c) { return c.trim(); });
        var rows = bodyRows.trim().split("\n");
        var table = "<table><thead><tr>";
        headers.forEach(function (h) { table += "<th>" + h.trim() + "</th>"; });
        table += "</tr></thead><tbody>";
        rows.forEach(function (row) {
          var cells = row.split("|").filter(function (c) { return c.trim(); });
          table += "<tr>";
          cells.forEach(function (c) { table += "<td>" + c.trim() + "</td>"; });
          table += "</tr>";
        });
        table += "</tbody></table>";
        return table;
      }
    );

    // Line breaks (double newline = paragraph)
    html = html.replace(/\n\n/g, "</p><p>");
    html = "<p>" + html + "</p>";
    html = html.replace(/<p><(h[234]|pre|table)/g, "<$1");
    html = html.replace(/<\/(h[234]|pre|table)><\/p>/g, "</$1>");

    return html;
  }

  // ── DOM helpers ────────────────────────────────────────────────────────────
  function $(sel) { return document.querySelector(sel); }
  function show(el) { el.style.display = ""; }
  function hide(el) { el.style.display = "none"; }

  // ── Auth Screen ────────────────────────────────────────────────────────────
  function showAuthScreen() {
    var app = $("#app");
    app.innerHTML =
      '<div class="auth-screen">' +
        '<h2>Yigthinker</h2>' +
        '<p>Enter your gateway token to connect.</p>' +
        '<input id="token-input" type="password" placeholder="Paste gateway token..." />' +
        '<button id="token-submit">Connect</button>' +
        '<div id="auth-error" class="auth-error"></div>' +
        '<div style="margin-top:24px; max-width:400px; text-align:left; font-size:13px; color:var(--text-secondary); line-height:1.6;">' +
          '<p style="font-weight:600; margin-bottom:8px;">First time? Run this in your terminal:</p>' +
          '<pre style="background:var(--bg-input); padding:8px 12px; border-radius:4px; font-family:var(--font-mono); font-size:12px; margin-bottom:12px;">yigthinker quickstart</pre>' +
          '<p style="color:var(--text-muted); font-size:12px;">Or find your token at <code style="background:var(--bg-input); padding:1px 4px; border-radius:2px; font-family:var(--font-mono);">~/.yigthinker/gateway.token</code></p>' +
        '</div>' +
      "</div>";

    var input = $("#token-input");
    input.value = state.token;
    input.focus();

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { submitToken(); }
    });
    $("#token-submit").addEventListener("click", submitToken);
  }

  function submitToken() {
    var token = $("#token-input").value.trim();
    if (!token) return;
    state.token = token;
    localStorage.setItem("yig_token", token);
    connect();
  }

  // ── Main App UI ────────────────────────────────────────────────────────────
  function renderApp() {
    var app = $("#app");
    app.innerHTML =
      // Header
      '<header class="header" role="banner">' +
        '<span class="header-brand">Yigthinker</span>' +
        '<div class="header-controls">' +
          '<span class="status-dot connecting" id="status-dot"></span>' +
          '<select id="session-select" title="Session"></select>' +
          '<button id="btn-new-session" title="New session">+ New</button>' +
          '<button id="btn-db-connect" title="Database connection">DB</button>' +
          '<button id="btn-theme" title="Toggle theme">Theme</button>' +
        "</div>" +
      "</header>" +

      // Main
      '<div class="main-content">' +
        // Conversation
        '<div class="conversation-panel" role="main">' +
          '<div class="chat-log" id="chat-log" aria-live="polite"></div>' +
          '<div class="input-bar">' +
            '<textarea id="user-input" rows="1" placeholder="Ask a question about your data..." aria-label="Message input"></textarea>' +
            '<button id="send-btn" title="Send">Send</button>' +
          "</div>" +
        "</div>" +
        // Context panel
        '<aside class="context-panel" role="complementary">' +
          '<div class="context-panel-header">Context</div>' +
          '<div class="context-section" id="vars-section">' +
            '<div class="context-section-title">DataFrames</div>' +
            '<div id="vars-list"><span class="empty-state">No data loaded yet</span></div>' +
          "</div>" +
          '<div class="context-section" id="connections-section">' +
            '<div class="context-section-title">Connections</div>' +
            '<div id="connections-list"><span class="empty-state">No DB connected</span></div>' +
          "</div>" +
        "</aside>" +
      "</div>" +

      // Status bar
      '<div class="status-bar">' +
        '<span id="status-text">Connecting...</span>' +
        '<span id="status-stats"></span>' +
      "</div>";

    // Event listeners
    $("#send-btn").addEventListener("click", sendMessage);
    var input = $("#user-input");
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    input.addEventListener("input", autoGrow);

    $("#btn-new-session").addEventListener("click", newSession);
    $("#btn-db-connect").addEventListener("click", showDbModal);
    $("#btn-theme").addEventListener("click", toggleTheme);
    $("#session-select").addEventListener("change", function () {
      switchSession(this.value);
    });

    showWelcome();
    updateStatus();
  }

  function autoGrow() {
    var el = $("#user-input");
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }

  // ── Welcome Screen ─────────────────────────────────────────────────────────
  function showWelcome() {
    if (state.messages.length > 0) return;
    var log = $("#chat-log");
    log.innerHTML =
      '<div class="welcome-screen">' +
        '<div class="welcome-title">Yigthinker</div>' +
        '<div class="welcome-subtitle">Ask questions about your data in plain language.</div>' +
        '<div class="sample-questions">' +
          '<div class="sample-question" data-q="Show me revenue by region for Q2">Show me revenue by region for Q2</div>' +
          '<div class="sample-question" data-q="Find anomalies in accounts payable">Find anomalies in accounts payable</div>' +
          '<div class="sample-question" data-q="Forecast next quarter\'s revenue">Forecast next quarter\'s revenue</div>' +
          '<div class="sample-question" data-q="Compare this quarter vs last year">Compare this quarter vs last year</div>' +
        "</div>" +
      "</div>";

    var questions = log.querySelectorAll(".sample-question");
    questions.forEach(function (q) {
      q.addEventListener("click", function () {
        var text = this.getAttribute("data-q");
        $("#user-input").value = text;
        sendMessage();
      });
    });
  }

  // ── Chat Rendering ─────────────────────────────────────────────────────────
  function appendMessage(role, content) {
    state.messages.push({ role: role, content: content });
    renderMessage(role, content);
    updateStatusStats();
  }

  function renderMessage(role, content) {
    var log = $("#chat-log");
    // Clear welcome screen on first message
    if (log.querySelector(".welcome-screen")) {
      log.innerHTML = "";
    }

    var div = document.createElement("div");
    div.className = "message " + role;

    if (role === "assistant") {
      div.innerHTML = renderMarkdown(content);
      // Check for chart_json in content and render Plotly
      tryRenderCharts(div, content);
    } else {
      div.textContent = content;
    }

    log.appendChild(div);
    scrollToBottom();
  }

  function startStreaming() {
    state.streaming = true;
    state.streamBuffer = "";
    var log = $("#chat-log");

    if (log.querySelector(".welcome-screen")) {
      log.innerHTML = "";
    }

    var div = document.createElement("div");
    div.className = "message assistant";
    div.id = "streaming-msg";
    div.innerHTML = '<span class="streaming-cursor"></span>';
    log.appendChild(div);
    scrollToBottom();

    setInputEnabled(false);
  }

  function appendStreamToken(text) {
    state.streamBuffer += text;
    var div = $("#streaming-msg");
    if (!div) return;
    div.innerHTML = renderMarkdown(state.streamBuffer) + '<span class="streaming-cursor"></span>';
    scrollToBottom();
  }

  function finishStreaming(fullText) {
    state.streaming = false;
    var text = fullText || state.streamBuffer;
    state.streamBuffer = "";

    var div = $("#streaming-msg");
    if (div) {
      div.removeAttribute("id");
      div.innerHTML = renderMarkdown(text);
      tryRenderCharts(div, text);
    }

    state.messages.push({ role: "assistant", content: text });
    setInputEnabled(true);
    scrollToBottom();
    updateStatusStats();
  }

  function scrollToBottom() {
    var log = $("#chat-log");
    log.scrollTop = log.scrollHeight;
  }

  function setInputEnabled(enabled) {
    var input = $("#user-input");
    var btn = $("#send-btn");
    if (input) input.disabled = !enabled;
    if (btn) btn.disabled = !enabled;
    if (enabled && input) input.focus();
  }

  // ── Tool Cards ─────────────────────────────────────────────────────────────
  function renderToolCard(toolName, toolInput, toolId) {
    var log = $("#chat-log");
    if (log.querySelector(".welcome-screen")) {
      log.innerHTML = "";
    }

    var card = document.createElement("div");
    card.className = "tool-card";
    card.id = "tool-" + toolId;
    card.innerHTML =
      '<div class="tool-card-header" role="button" tabindex="0" aria-expanded="false">' +
        '<span class="tool-card-icon">&#9881;</span>' +
        '<span class="tool-card-name">' + escapeHtml(toolName) + "</span>" +
        '<span class="tool-card-status running"></span>' +
        '<span class="tool-card-chevron">&#9654;</span>' +
      "</div>" +
      '<div class="tool-card-body">' + escapeHtml(JSON.stringify(toolInput, null, 2)) + "</div>";

    var header = card.querySelector(".tool-card-header");
    header.addEventListener("click", function () {
      card.classList.toggle("expanded");
      header.setAttribute("aria-expanded", card.classList.contains("expanded"));
    });
    header.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        header.click();
      }
    });

    log.appendChild(card);
    scrollToBottom();
  }

  function updateToolCard(toolId, content, isError) {
    var card = $("#tool-" + toolId);
    if (!card) return;

    var status = card.querySelector(".tool-card-status");
    status.classList.remove("running");
    status.classList.add(isError ? "error" : "done");

    var body = card.querySelector(".tool-card-body");
    body.textContent = typeof content === "string" ? content : JSON.stringify(content, null, 2);
  }

  // ── Plotly Charts ──────────────────────────────────────────────────────────
  function tryRenderCharts(div, text) {
    // Look for chart_json patterns in tool results
    // Charts come through as tool_result content with JSON
    // The main path is via renderToolResult which checks for chart data
  }

  function renderChart(container, chartJson) {
    if (typeof Plotly === "undefined") return;
    try {
      var spec = typeof chartJson === "string" ? JSON.parse(chartJson) : chartJson;
      var chartDiv = document.createElement("div");
      chartDiv.className = "chart-container";
      container.appendChild(chartDiv);

      var layout = Object.assign({}, spec.layout || {}, {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, system-ui, sans-serif", size: 12 },
        margin: { t: 40, r: 20, b: 40, l: 50 },
        autosize: true,
      });

      Plotly.newPlot(chartDiv, spec.data || [], layout, {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
      });
    } catch (e) {
      console.warn("Failed to render chart:", e);
    }
  }

  // ── Vars Panel ─────────────────────────────────────────────────────────────
  function updateVarsPanel(vars) {
    state.vars = vars;
    var list = $("#vars-list");
    if (!list) return;

    if (!vars || vars.length === 0) {
      list.innerHTML = '<span class="empty-state">No data loaded yet</span>';
      return;
    }

    list.innerHTML = vars.map(function (v) {
      var shape = v.shape ? "(" + v.shape.join(" x ") + ")" : "";
      return (
        '<div class="var-item">' +
          '<span class="var-name">' + escapeHtml(v.name) + "</span>" +
          '<span class="var-shape">' + escapeHtml(shape) + "</span>" +
        "</div>"
      );
    }).join("");
  }

  // ── Session Management ─────────────────────────────────────────────────────
  function updateSessionList(sessions) {
    state.sessions = sessions;
    var select = $("#session-select");
    if (!select) return;

    select.innerHTML = sessions.map(function (s) {
      var key = s.key || s;
      var selected = key === state.sessionKey ? " selected" : "";
      return '<option value="' + escapeHtml(key) + '"' + selected + ">" + escapeHtml(key) + "</option>";
    }).join("");
  }

  function switchSession(key) {
    if (key === state.sessionKey) return;
    state.sessionKey = key;
    localStorage.setItem("yig_session", key);
    state.messages = [];

    // Detach from old, attach to new
    wsSend({ type: "detach", session_key: state.sessionKey });
    wsSend({ type: "attach", session_key: key });

    var log = $("#chat-log");
    if (log) log.innerHTML = "";
    showWelcome();
    updateStatusStats();
  }

  function newSession() {
    var key = "session-" + Date.now().toString(36);
    state.sessionKey = key;
    localStorage.setItem("yig_session", key);
    state.messages = [];

    wsSend({ type: "attach", session_key: key });

    var log = $("#chat-log");
    if (log) log.innerHTML = "";
    showWelcome();
    updateStatusStats();

    // Add to select
    var select = $("#session-select");
    if (select) {
      var opt = document.createElement("option");
      opt.value = key;
      opt.textContent = key;
      opt.selected = true;
      select.appendChild(opt);
    }
  }

  // ── DB Connection Modal ────────────────────────────────────────────────────
  function showDbModal() {
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.id = "db-modal";
    backdrop.innerHTML =
      '<div class="modal">' +
        "<h3>Database Connection</h3>" +
        '<label for="db-name">Connection Name</label>' +
        '<input id="db-name" placeholder="e.g. oracle-prod" />' +
        '<label for="db-type">Database Type</label>' +
        '<select id="db-type">' +
          '<option value="sqlite">SQLite</option>' +
          '<option value="postgresql">PostgreSQL</option>' +
          '<option value="mysql">MySQL</option>' +
          '<option value="oracle">Oracle</option>' +
        "</select>" +
        '<label for="db-host">Host</label>' +
        '<input id="db-host" placeholder="localhost" />' +
        '<label for="db-port">Port</label>' +
        '<input id="db-port" placeholder="5432" />' +
        '<label for="db-database">Database / Service Name</label>' +
        '<input id="db-database" placeholder="mydb" />' +
        '<label for="db-user">Username</label>' +
        '<input id="db-user" placeholder="user" />' +
        '<label for="db-pass">Password</label>' +
        '<input id="db-pass" type="password" placeholder="password" />' +
        '<div class="modal-buttons">' +
          '<button class="btn-secondary" id="db-cancel">Cancel</button>' +
          '<button class="btn-primary" id="db-test">Test & Connect</button>' +
        "</div>" +
      "</div>";

    document.body.appendChild(backdrop);

    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) closeDbModal();
    });
    $("#db-cancel").addEventListener("click", closeDbModal);
    $("#db-test").addEventListener("click", testAndConnect);

    // SQLite mode: hide host/port/user/pass
    $("#db-type").addEventListener("change", function () {
      var isSqlite = this.value === "sqlite";
      ["db-host", "db-port", "db-user", "db-pass"].forEach(function (id) {
        var el = document.getElementById(id);
        var label = document.querySelector('label[for="' + id + '"]');
        var vis = isSqlite ? "none" : "";
        if (label) label.style.display = vis;
        el.style.display = vis;
      });
      if (isSqlite) {
        $("#db-database").placeholder = "path/to/database.db";
      } else {
        $("#db-database").placeholder = "mydb";
      }
    });
    // Trigger initial state
    $("#db-type").dispatchEvent(new Event("change"));
  }

  function closeDbModal() {
    var modal = $("#db-modal");
    if (modal) modal.remove();
  }

  function testAndConnect() {
    var name = $("#db-name").value.trim();
    var dbType = $("#db-type").value;
    var database = $("#db-database").value.trim();

    if (!name || !database) return;

    // Send connection command as user input to the agent
    var cmd;
    if (dbType === "sqlite") {
      cmd = "Connect to SQLite database at " + database + " and name it " + name;
    } else {
      var host = $("#db-host").value.trim() || "localhost";
      var port = $("#db-port").value.trim();
      var user = $("#db-user").value.trim();
      cmd = "Connect to " + dbType + " database " + database +
        " on " + host + (port ? ":" + port : "") +
        (user ? " as user " + user : "") +
        " and name the connection " + name;
    }

    closeDbModal();
    $("#user-input").value = cmd;
    sendMessage();
  }

  // ── Theme Toggle ───────────────────────────────────────────────────────────
  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-theme");
    var next = current === "dark" ? "light" : "dark";
    if (next === "light") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
    }
    localStorage.setItem("yig_theme", next);
  }

  function loadTheme() {
    var saved = localStorage.getItem("yig_theme");
    if (saved === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }

  // ── Status Updates ─────────────────────────────────────────────────────────
  function updateStatus() {
    var dot = $("#status-dot");
    var text = $("#status-text");
    if (!dot || !text) return;

    dot.className = "status-dot " + (state.connected ? "connected" : "connecting");
    text.textContent = state.connected ? "Connected" : "Connecting...";
  }

  function updateStatusStats() {
    var stats = $("#status-stats");
    if (!stats) return;
    var msgCount = state.messages.length;
    var varCount = state.vars.length;
    stats.textContent = "Session: " + state.sessionKey + " | " + msgCount + " msgs | " + varCount + " vars";
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────
  function connect() {
    var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    var wsUrl = protocol + "//" + window.location.host + "/ws";

    state.ws = new WebSocket(wsUrl);
    renderApp();

    state.ws.onopen = function () {
      // Send auth
      wsSend({ type: "auth", token: state.token });
    };

    state.ws.onmessage = function (event) {
      var msg;
      try {
        msg = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      handleMessage(msg);
    };

    state.ws.onclose = function (event) {
      state.connected = false;
      state.authenticated = false;
      updateStatus();

      if (event.code === 4401) {
        // Bad token
        localStorage.removeItem("yig_token");
        state.token = "";
        showAuthScreen();
        return;
      }

      if (event.code === 4403) {
        // Origin rejected
        var text = $("#status-text");
        if (text) text.textContent = "Connection rejected: cross-origin not allowed";
        return;
      }

      // Reconnect after delay
      setTimeout(function () {
        if (!state.authenticated) {
          connect();
        }
      }, 3000);
    };

    state.ws.onerror = function () {
      state.connected = false;
      updateStatus();
    };
  }

  function wsSend(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify(obj));
    }
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case "auth_result":
        if (msg.ok) {
          state.connected = true;
          state.authenticated = true;
          updateStatus();
          // Attach to session
          wsSend({ type: "attach", session_key: state.sessionKey });
        } else {
          localStorage.removeItem("yig_token");
          state.token = "";
          showAuthScreen();
        }
        break;

      case "token":
        if (!state.streaming) startStreaming();
        appendStreamToken(msg.text);
        break;

      case "tool_call":
        renderToolCard(msg.tool_name, msg.tool_input || {}, msg.tool_id || "");
        break;

      case "tool_result":
        updateToolCard(msg.tool_id || "", msg.content || "", msg.is_error || false);
        // Check if content contains chart JSON
        if (msg.content && !msg.is_error) {
          tryRenderToolResultChart(msg.content);
        }
        break;

      case "response_done":
        finishStreaming(msg.full_text);
        break;

      case "vars_update":
        updateVarsPanel(msg.vars || []);
        updateStatusStats();
        break;

      case "session_list":
        updateSessionList(msg.sessions || []);
        break;

      case "error":
        if (state.streaming) {
          finishStreaming(state.streamBuffer + "\n\n[Error: " + msg.message + "]");
        } else {
          appendMessage("assistant", "[Error: " + msg.message + "]");
        }
        break;
    }
  }

  function tryRenderToolResultChart(content) {
    try {
      var data = typeof content === "string" ? JSON.parse(content) : content;
      if (data && data.data && Array.isArray(data.data)) {
        // This looks like Plotly chart JSON
        var log = $("#chat-log");
        var chartWrapper = document.createElement("div");
        chartWrapper.className = "message assistant";
        log.appendChild(chartWrapper);
        renderChart(chartWrapper, data);
        scrollToBottom();
      }
    } catch (e) {
      // Not JSON or not a chart, that's fine
    }
  }

  // ── Send Message ───────────────────────────────────────────────────────────
  function sendMessage() {
    var input = $("#user-input");
    var text = input.value.trim();
    if (!text || state.streaming) return;

    appendMessage("user", text);
    wsSend({
      type: "user_input",
      text: text,
      request_id: "req-" + Date.now().toString(36),
    });

    input.value = "";
    input.style.height = "auto";
  }

  // ── Utilities ──────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Init ───────────────────────────────────────────────────────────────────
  loadTheme();

  if (!state.token) {
    showAuthScreen();
  } else {
    connect();
  }
})();
