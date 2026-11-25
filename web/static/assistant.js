(function () {
  "use strict";

  var GID = "L1-06";
  var DS = "c3";
  var state = { t: 0.95, open: false, busy: false, q: "" };

  function datasetFor(gid) {
    var c1 = ["L1-03", "L1-04", "L1-05", "L1-09", "L1-23"];
    var c2 = ["L1-49", "L1-50", "L1-51", "L1-52", "L1-54", "L1-55", "L1-56", "L1-59", "L1-60"];
    var c3 = ["L1-06", "L1-13", "L1-14", "L1-22", "L1-24"];
    if (c1.indexOf(gid) >= 0) return "c1";
    if (c2.indexOf(gid) >= 0) return "c2";
    if (c3.indexOf(gid) >= 0) return "c3";
    return "c4";
  }

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function pct(v) { return Math.round(Number(v) * 100) + "%"; }

  function el(id) { return document.getElementById(id); }

  function updateURL() {
    var q = "ds=" + encodeURIComponent(DS) + "&gid=" + encodeURIComponent(GID) + "&t=" + state.t.toFixed(3);
    if (state.q) q += "&q=" + encodeURIComponent(state.q);
    if (state.open) q += "&assistant=1";
    try { history.replaceState(null, "", "/?" + q); } catch (e) { /* file:// */ }
  }

  function setT(v, ask) {
    state.t = Math.max(0, Math.min(1, Number(v)));
    var range = el("shm-copilot-range");
    if (range) range.value = state.t;
    var out = el("shm-copilot-t");
    if (out) out.textContent = pct(state.t);
    var seek = el("seek");
    if (seek && !seek.disabled) {
      seek.value = String(Math.round(state.t * 1000));
      try { seek.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) { /* older */ }
    }
    updateURL();
    if (ask) request();
  }

  function open(force) {
    state.open = force == null ? !state.open : !!force;
    var panel = el("shm-copilot-panel");
    if (panel) panel.hidden = !state.open;
    var btn = el("shm-copilot-toggle");
    if (btn) btn.textContent = state.open ? "收起证据助手" : "AI 证据助手";
    updateURL();
  }

  function status(text, cls) {
    var box = el("shm-copilot-status");
    if (!box) return;
    box.className = cls || "";
    box.textContent = text;
  }

  function plannerNote(obj) {
    var p = obj.planner || {};
    var src = p.source || "default";
    var model = p.model ? " · " + p.model : "";
    var err = p.error ? '<div class="cp-meta">LLM 回退原因：' + esc(p.error) + "</div>" : "";
    return '<div class="cp-planner">语义编译：' + esc(src) + esc(model) + err + "</div>";
  }

  function renderRefused(obj) {
    var failed = (obj.failed_checks || []).join(", ");
    status(obj.message || "时间门未通过，系统不签发 claim。", "refused");
    el("shm-copilot-answer").innerHTML =
      plannerNote(obj) +
      '<div class="cp-card"><b>拒答</b><div class="cp-meta">' +
      "允许寿命 " + pct(obj.t) + "；未返回任何 claim、evidence 或 tool_call。" +
      (failed ? "<br>failed checks: " + esc(failed) : "") +
      "</div></div>" +
      '<div class="cp-foot">' +
      (obj.gate === "temporal"
        ? "拒答不是模型措辞，而是 verifier 的 temporal gate。"
        : "拒答不是模型措辞，而是 verifier 的边界或工具重跑校验未通过。") +
      "页面上的曲线仍是回顾性展示，不构成在线预测。</div>";
  }

  function renderUnsupported(obj) {
    status("未编译成受支持的查询", "refused");
    el("shm-copilot-answer").innerHTML =
      plannerNote(obj) +
      '<div class="cp-card"><b>不支持</b><div class="cp-meta">' +
      esc(obj.message || "当前问题不在该 gid 的白名单工具范围内。") +
      "</div></div>" +
      '<div class="cp-foot">这不是把问题硬套成模板：planner 只能输出白名单计划，' +
      "越界问题不会生成 claim。</div>";
  }

  function renderOk(obj) {
    var g = obj.graph || {};
    var claims = g.claims || [];
    var evs = g.evidence || [];
    var tools = g.tool_calls || [];
    var ver = g.verification || obj.verification || {};
    var label = obj.status === "partial" ? "部分签发"
      : (obj.status === "insufficient" ? "不签发" : "已核验通过");

    status(label + " · " + (ver.summary || "verification pass"),
      obj.status === "insufficient" ? "refused" : "ok");

    var html = plannerNote(obj);
    html += '<div class="cp-answer-text">' + esc(obj.answer || "") + "</div>";
    if (obj.message) {
      html += '<div class="cp-meta">' + esc(obj.message) + "</div>";
    }
    html += '<div class="cp-section"><h4>CLAIMS</h4>';
    claims.forEach(function (c) {
      var st = c.status || "supported";
      var allowed = c.allowed_lifetime_max == null
        ? "无寿命门"
        : "≤ " + pct(c.allowed_lifetime_max);
      html += '<div class="cp-card"><b>' + esc(c.claim_id) + "</b> " + esc(c.text) +
        '<div class="cp-meta">status ' + esc(st) + " · value " +
        '<span class="cp-value">' + esc(c.value == null ? "n/a" : c.value) +
        esc(c.unit || "") + "</span> · " +
        esc(allowed) + " · tolerance " +
        esc(c.tolerance == null ? "n/a" : c.tolerance) + "</div>" +
        '<div class="cp-meta">chain ' + esc(c.claim_id || "?") + " ← " +
        esc((c.evidence_ids || []).join(" + ") || "?") + " ← " +
        esc((c.tool_call_ids || []).join(" + ") || "?") + "</div>" +
        (c.missing_evidence ? '<div class="cp-meta">未签发原因：' +
          esc(c.missing_evidence) + "</div>" : "") + "</div>";
    });
    html += "</div>";

    html += '<div class="cp-section"><h4>EVIDENCE / TOOL CHAIN</h4>';
    evs.forEach(function (e) {
      var c = e.content || {};
      var cov = c.coverage == null ? "n/a" : c.coverage;
      var basis = c.coverage_basis ? " (" + c.coverage_basis + ")" : "";
      html += '<div class="cp-card"><b>' + esc(e.evidence_id) + "</b> " +
        esc(e.evidence_type) + " · " + esc(c.metric) +
        ' = <span class="cp-value">' + esc(c.value) + "</span>" +
        '<div class="cp-meta">' + esc(c.convention || "") +
        " · coverage " + esc(cov + basis) +
        " · " + esc((e.locator || {}).file || "") + "</div></div>";
    });
    tools.forEach(function (t) {
      html += '<div class="cp-card"><b>' + esc(t.tool_call_id) + "</b> " +
        esc(t.tool_name) + '<div class="cp-meta">arguments ' +
        esc(JSON.stringify(t.arguments || {})) + " · elapsed " +
        esc(t.elapsed_ms == null ? "n/a" : t.elapsed_ms + " ms") + "</div></div>";
    });
    html += '<div class="cp-chain">graph: ' + claims.length + " claims · " +
      evs.length + " evidence · " + tools.length +
      " tool calls · 数值由工具重跑核对，不由模型生成</div></div>";
    html += '<div class="cp-foot">' +
      (obj.gate === "not_applicable"
        ? "该 claim 的轴不是寿命分数，t 只对其他模态生效。"
        : (obj.status === "insufficient" || obj.status === "partial"
          ? "只有 status=supported 的 claim 被签发；insufficient 只返回可核对边界和原因。"
          : "回顾性口径：t 是允许寿命上限，不是在线预测时刻。")) +
      "</div>";

    el("shm-copilot-answer").innerHTML = html;
  }

  function request() {
    if (state.busy) return;
    state.busy = true;
    var qInput = el("shm-copilot-q");
    state.q = qInput ? qInput.value.trim() : "";
    updateURL();
    var btn = el("shm-copilot-ask");
    if (btn) btn.disabled = true;
    status("正在编译问题、从 raw 重算，并让 verifier 重跑工具…", "");

    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gid: GID, t: state.t, question: state.q || null })
    }).then(function (r) {
      return r.json().then(function (obj) { return { ok: r.ok, obj: obj }; });
    }).then(function (res) {
      if (!res.ok) {
        status("请求失败：" + (res.obj.detail || res.obj.message || "HTTP error"), "error");
        return;
      }
      if (res.obj.status === "ok" || res.obj.status === "partial" ||
          res.obj.status === "insufficient") renderOk(res.obj);
      else if (res.obj.status === "refused") renderRefused(res.obj);
      else if (res.obj.status === "unsupported") renderUnsupported(res.obj);
      else status("未知响应：" + JSON.stringify(res.obj), "error");
    }).catch(function (err) {
      status("请求失败：" + err, "error");
    }).then(function () {
      state.busy = false;
      if (btn) btn.disabled = false;
    });
  }

  function buildUI() {
    var root = document.createElement("div");
    root.id = "shm-copilot";
    root.innerHTML =
      '<section id="shm-copilot-panel" hidden>' +
        '<div class="cp-head"><div><b>证据约束分析 · ' + esc(GID) + '</b>' +
          "<small>raw → deterministic tool → verifier → claim</small></div>" +
          '<button class="cp-close" id="shm-copilot-close" aria-label="close">×</button></div>' +
        '<div class="cp-body">' +
          '<div class="cp-row"><label>允许寿命上限 t</label><output id="shm-copilot-t">95%</output></div>' +
          '<input id="shm-copilot-range" type="range" min="0" max="1" step="0.001" value="0.95">' +
          '<div class="cp-scale"><span>0%</span><span>50%</span><span>100%</span></div>' +
          '<div class="cp-q"><label for="shm-copilot-q">问题</label>' +
            '<input id="shm-copilot-q" maxlength="500" ' +
            'placeholder="例：t85 是多少 / FBG 剖面 / DFOS 预警点 / PZT t85"></div>' +
          '<div class="cp-quick"><button data-t="0.62">62% · 拒答</button>' +
            '<button data-t="0.95">95% · 通过</button></div>' +
          '<button id="shm-copilot-ask">核验并回答</button>' +
          '<div id="shm-copilot-status">选择 t，然后核验。' +
            "t=0.62 应被拒，t=0.95 应通过；以 verifier 返回为准。</div>" +
          '<div id="shm-copilot-answer"></div>' +
        "</div>" +
      "</section>" +
      '<button id="shm-copilot-toggle">AI 证据助手</button>';
    document.body.appendChild(root);

    el("shm-copilot-toggle").addEventListener("click", function () { open(); });
    el("shm-copilot-close").addEventListener("click", function () { open(false); });
    el("shm-copilot-ask").addEventListener("click", request);
    el("shm-copilot-range").addEventListener("input", function () {
      setT(this.value, false);
    });
    var qInput = el("shm-copilot-q");
    if (qInput) {
      qInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); request(); }
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll(".cp-quick button"), function (b) {
      b.addEventListener("click", function () { setT(this.getAttribute("data-t"), true); });
    });
  }

  function selectDashboard() {
    var tries = 0;
    function attempt() {
      var ds = el("dsSel"), gid = el("gidSel");
      if (!ds || !gid || !ds.options.length || !gid.options.length) {
        if (tries++ < 40) return setTimeout(attempt, 150);
        return;
      }
      var hasDS = false;
      for (var i = 0; i < ds.options.length; i++) {
        if (ds.options[i].value === DS) { hasDS = true; break; }
      }
      if (!hasDS) { if (tries++ < 40) return setTimeout(attempt, 150); return; }
      if (ds.value !== DS) {
        ds.value = DS;
        ds.dispatchEvent(new Event("change", { bubbles: true }));
      }
      setTimeout(function () {
        var hasGid = false;
        for (var j = 0; j < gid.options.length; j++) {
          if (gid.options[j].value === GID) { hasGid = true; break; }
        }
        if (hasGid && gid.value !== GID) {
          gid.value = GID;
          gid.dispatchEvent(new Event("change", { bubbles: true }));
        }
        // 数据包异步加载，分几次把看板时间游标对齐到面板的 t
        [300, 900, 1800].forEach(function (ms) {
          setTimeout(function () { setT(state.t, false); }, ms);
        });
        updateURL();
      }, 120);
    }
    attempt();
  }

  function init() {
    var params = new URLSearchParams(location.search);
    GID = params.get("gid") || GID;
    DS = params.get("ds") || datasetFor(GID);
    buildUI();
    var t = parseFloat(params.get("t"));
    if (!isNaN(t)) state.t = Math.max(0, Math.min(1, t));
    state.q = (params.get("q") || "").slice(0, 500);
    var qInput = el("shm-copilot-q");
    if (qInput) qInput.value = state.q;
    var range = el("shm-copilot-range");
    if (range) range.value = state.t;
    var out = el("shm-copilot-t");
    if (out) out.textContent = pct(state.t);
    if (params.get("assistant") === "1") open(true);
    selectDashboard();
    updateURL();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.SHM_COPILOT = { setT: setT, ask: request, open: open };
})();
