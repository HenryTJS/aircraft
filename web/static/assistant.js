(function () {
  "use strict";

  var GID = "L1-06";
  var DS = "c3";
  var state = { t: 0.95, open: false, busy: false, q: "" };

  function datasetFor(gid) {
    var c1 = ["L1-03", "L1-04", "L1-05", "L1-09", "L1-23"];
    var c2 = ["L1-49", "L1-50", "L1-51", "L1-52", "L1-54", "L1-55", "L1-56", "L1-59", "L1-60"];
    var c3 = ["L1-06", "L1-13", "L1-14", "L1-22", "L1-24"];
    if (/^spec[1-7]$/i.test(gid)) return null;
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
    var q = "";
    if (DS) q += "ds=" + encodeURIComponent(DS) + "&";
    q += "gid=" + encodeURIComponent(GID) + "&t=" + state.t.toFixed(3);
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

  function resolvedNote(obj) {
    var r = obj.resolved;
    if (!r) return "";
    var bits = [];
    if (r.gid) bits.push("试件 " + r.gid);
    if (r.t != null) bits.push("允许寿命 " + pct(r.t));
    if (!bits.length) return "";
    return '<div class="cp-planner">' + esc(bits.join(" · ")) + "</div>";
  }

  function renderRefused(obj) {
    var failed = (obj.failed_checks || []).join(", ");
    status(obj.message || "时间门未通过，系统不签发 claim。", "refused");
    el("shm-copilot-answer").innerHTML =
      resolvedNote(obj) +
      '<div class="cp-card"><b>拒答</b><div class="cp-meta">' +
      "允许寿命 " + pct(obj.t) + "；未签发 claim。" +
      (failed ? "<br>failed checks: " + esc(failed) : "") +
      "</div></div>";
  }

  function renderUnsupported(obj) {
    status("未编译成受支持的查询", "refused");
    el("shm-copilot-answer").innerHTML =
      resolvedNote(obj) +
      '<div class="cp-card"><b>不支持</b><div class="cp-meta">' +
      esc(obj.message || "当前问题不在该 gid 的白名单工具范围内。") +
      "</div></div>";
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

    var html = resolvedNote(obj);
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
      html += '<div class="cp-card"><b>' + esc(c.claim_id) + "</b> " +
        '<span class="cp-value">' + esc(c.value == null ? "n/a" : c.value) +
        esc(c.unit || "") + "</span> " +
        '<span class="cp-badge' + (st === "supported" ? "" : " fail") + '">' +
        esc(st) + "</span>" +
        '<div class="cp-meta">' + esc(allowed) +
        (c.missing_evidence ? " · 未签发" : "") + "</div>" +
        '<details class="cp-fold"><summary>依据</summary>' +
        '<div class="cp-meta">' + esc(c.text || "") + "</div>" +
        '<div class="cp-meta">' + esc((c.evidence_ids || []).join(" + ") || "?") +
        " ← " + esc((c.tool_call_ids || []).join(" + ") || "?") + "</div>" +
        (c.missing_evidence ? '<div class="cp-meta">' + esc(c.missing_evidence) + "</div>" : "") +
        "</details></div>";
    });
    html += "</div>";

    html += '<details class="cp-section cp-fold"><summary>证据与工具链 · ' +
      evs.length + " / " + tools.length + "</summary>";
    evs.forEach(function (e) {
      var c = e.content || {};
      var cov = c.coverage == null ? "n/a" : c.coverage;
      var basis = c.coverage_basis ? " (" + c.coverage_basis + ")" : "";
      html += '<div class="cp-card"><b>' + esc(e.evidence_id) + "</b> " +
        esc(c.metric) + ' = <span class="cp-value">' + esc(c.value) + "</span>" +
        '<div class="cp-meta">coverage ' + esc(cov + basis) + "</div></div>";
    });
    tools.forEach(function (t) {
      html += '<div class="cp-card"><b>' + esc(t.tool_call_id) + "</b> " +
        esc(t.tool_name) + '<div class="cp-meta">' +
        esc(t.elapsed_ms == null ? "n/a" : t.elapsed_ms + " ms") + "</div></div>";
    });
    html += "</details>";

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
    status("计算中…", "");

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

  function applyContext(obj) {
    var r = obj.resolved;
    if (!r || !r.gid) return;
    GID = r.gid;
    DS = datasetFor(GID);
    if (r.t != null) state.t = Math.max(0, Math.min(1, Number(r.t)));
    var title = el("shm-copilot-title");
    if (title) title.textContent = "证据约束分析 · " + GID;
    var qInput = el("shm-copilot-q");
    if (qInput && state.q) qInput.value = state.q;
    var range = el("shm-copilot-range");
    if (range) range.value = state.t;
    var out = el("shm-copilot-t");
    if (out) out.textContent = pct(state.t);
    setT(state.t, false);
    if (DS) selectDashboard();
    updateURL();
  }

  function directAsk() {
    if (state.busy) return;
    var input = el("shm-direct-q");
    var q = input ? input.value.trim() : "";
    if (!q) {
      open(true);
      status("请输入问题，例如：L1-13 先查 AE t85 再查 PZT t85 做一致性判断", "");
      return;
    }
    state.q = q;
    state.busy = true;
    open(true);
    var panelQ = el("shm-copilot-q");
    if (panelQ) panelQ.value = q;
    var btn = el("shm-direct-ask");
    if (btn) btn.disabled = true;
    status("正在解析试件和 t，然后从 raw 重算…", "");

    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gid: GID, question: q })
    }).then(function (r) {
      return r.json().then(function (obj) { return { ok: r.ok, obj: obj }; });
    }).then(function (res) {
      if (!res.ok) {
        status("请求失败：" + (res.obj.detail || res.obj.message || "HTTP error"), "error");
        return;
      }
      applyContext(res.obj);
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

  function renderAsof(obj) {
    var s = obj.state || {};
    var a = obj.asof || {};
    var p = obj.pzt || {};
    var b = obj.boundary || {};
    status("在线前缀 · 截至 cycle " + Number(s.cycle || 0).toLocaleString(), "ok");

    var html = '<div class="cp-answer-text">只读取查询时刻之前的帧；不返回 t85，也不使用全寿命总 hits。</div>';
    html += '<div class="cp-card"><b>当前时刻</b> ' +
      '<span class="cp-value">' + Number(s.cycle || 0).toLocaleString() + " cycle</span>" +
      '<div class="cp-meta">' + esc(a.elapsed_h == null ? "n/a" : a.elapsed_h + " h") +
      " · frame " + esc(s.frame_index == null ? "n/a" : s.frame_index) + "</div></div>";
    if (s.cum_hits != null) {
      html += '<div class="cp-card"><b>累计事件</b> ' +
        '<span class="cp-value">' + Number(s.cum_hits || 0).toLocaleString() + "</span>" +
        '<div class="cp-meta">本帧 ' + Number(s.frame_hits || 0).toLocaleString() +
        " · " + esc(s.hit_rate_h == null ? "n/a" : Number(s.hit_rate_h).toFixed(1)) + " /h</div></div>";
    } else if (s.cum_energy != null) {
      html += '<div class="cp-card"><b>累积能量</b> ' +
        '<span class="cp-value">' + Number(s.cum_energy || 0).toLocaleString() + "</span>" +
        '<div class="cp-meta">本窗 ' + Number(s.frame_energy || 0).toFixed(1) +
        " · CElog " + Number(s.ce_log || 0).toFixed(1) + "</div></div>";
    }
    if (p.cycle != null) {
      html += '<div class="cp-card"><b>PZT 最近状态</b> ' +
        '<span class="cp-value">D ' + esc(Number(p.D).toFixed(3)) + "</span>" +
        '<div class="cp-meta">cycle ' + Number(p.cycle).toLocaleString() +
        " · 落后 " + Number(p.age_cycles || 0).toLocaleString() + " cycle" +
        (p.tof_drift_us == null ? "" : " · ΔTOF " + Number(p.tof_drift_us).toFixed(2) + " µs") +
        "</div></div>";
    }
    html += '<div class="cp-card"><b>边界</b><div class="cp-meta">' +
      esc(b.reason || "prefix only") + "</div></div>";
    el("shm-copilot-answer").innerHTML = html;
  }

  function asofAsk() {
    var ctx = window.SHM_CURRENT ? window.SHM_CURRENT() : null;
    if (!ctx) {
      status("当前看板尚未加载试件", "error");
      return;
    }
    if (ctx.gid !== "L1-13" && ctx.gid !== "016" && ctx.gid !== "main-016") {
      status("当前只有 L1-13 与 main-016 建了在线前缀，其他试件仍是离线回放", "error");
      return;
    }
    var btn = el("shm-asof");
    if (btn) btn.disabled = true;
    status("读取当前前缀…", "");
    fetch("/api/asof?gid=" + encodeURIComponent(ctx.gid) +
          "&cycle=" + encodeURIComponent(ctx.cycle))
      .then(function (r) {
        return r.json().then(function (obj) { return { ok: r.ok, obj: obj }; });
      }).then(function (res) {
        if (!res.ok) {
          status("as-of 失败：" + (res.obj.detail || res.obj.message || "HTTP error"), "error");
          return;
        }
        renderAsof(res.obj);
      }).catch(function (err) {
        status("as-of 失败：" + err, "error");
      }).then(function () {
        if (btn) btn.disabled = false;
      });
  }

  function buildUI() {
    var root = document.createElement("div");
    root.id = "shm-copilot";
    root.innerHTML =
      '<section id="shm-copilot-panel" hidden>' +
        '<div class="cp-head"><div><b id="shm-copilot-title">证据约束分析 · ' + esc(GID) + '</b>' +
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
          '<button id="shm-asof" class="cp-asof">当前时刻状态</button>' +
          '<div id="shm-copilot-status">待核验</div>' +
          '<div id="shm-copilot-answer"></div>' +
        "</div>" +
      "</section>" +
      '<div id="shm-direct-bar">' +
        '<input id="shm-direct-q" maxlength="500" autocomplete="off" ' +
          'placeholder="直接问，例如 L1-13 的 AE/PZT t85 一致性">' +
        '<button id="shm-direct-ask">提问</button>' +
      "</div>" +
      '<button id="shm-copilot-toggle">AI 证据助手</button>';
    document.body.appendChild(root);

    el("shm-copilot-toggle").addEventListener("click", function () { open(); });
    el("shm-copilot-close").addEventListener("click", function () { open(false); });
    el("shm-copilot-ask").addEventListener("click", request);
    var asofBtn = el("shm-asof");
    if (asofBtn) asofBtn.addEventListener("click", asofAsk);
    el("shm-copilot-range").addEventListener("input", function () {
      setT(this.value, false);
    });
    var qInput = el("shm-copilot-q");
    if (qInput) {
      qInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); request(); }
      });
    }
    var direct = el("shm-direct-q");
    if (direct) {
      direct.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); directAsk(); }
      });
    }
    var directBtn = el("shm-direct-ask");
    if (directBtn) directBtn.addEventListener("click", directAsk);
    Array.prototype.forEach.call(document.querySelectorAll(".cp-quick button"), function (b) {
      b.addEventListener("click", function () { setT(this.getAttribute("data-t"), true); });
    });
  }

  function selectDashboard() {
    if (!DS) return;
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

  window.SHM_COPILOT = { setT: setT, ask: request, asof: asofAsk, open: open };
})();
