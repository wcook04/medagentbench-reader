/* Theme switch, the six transcripts, the map of instances, the contents highlight and glossary hover cards.
   The page reads completely without this script: glossary terms are ordinary links to the glossary. */
(function () {
  var root = document.documentElement;

  /* ---- day and night */
  var b = document.getElementById("theme");
  function dark() { var s = root.getAttribute("data-theme"); return s ? s === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; }
  function label() { b.textContent = dark() ? "Day" : "Night"; }
  if (b) {
    b.addEventListener("click", function () {
      var next = dark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("medagentbench-reader-theme", next); } catch (e) {}
      label();
    });
    label();
  }

  /* ---- the six runs: one shown at a time; #transcript-3 in the address opens the third */
  var tabs = [].slice.call(document.querySelectorAll('.casetabs [role="tab"]'));
  function pick(t, user) {
    tabs.forEach(function (x) {
      var on = x === t;
      x.setAttribute("aria-selected", on ? "true" : "false");
      x.tabIndex = on ? 0 : -1;
      document.getElementById(x.getAttribute("aria-controls")).hidden = !on;
    });
    if (user) { try { history.replaceState(null, "", "#transcript-" + (tabs.indexOf(t) + 1)); } catch (e) {} }
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { pick(t, true); });
    t.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (d) { var nx = tabs[(i + d + tabs.length) % tabs.length]; pick(nx, true); nx.focus(); }
    });
  });
  function fromHash() {
    var m = /^#transcript-(\d+)$/.exec(location.hash);
    if (m && tabs[m[1] - 1]) {
      pick(tabs[m[1] - 1]);
      var sec = document.getElementById("transcripts");
      if (sec) sec.scrollIntoView();
      return true;
    }
    return false;
  }
  if (tabs.length && !fromHash()) pick(tabs[0]);
  window.addEventListener("hashchange", fromHash);

  /* ---- contents: on a narrow screen the contents box sits after the article, and stays open */
  /* ---- contents: mark the section being read */
  var links = [].slice.call(document.querySelectorAll(".toc a"));
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  var sections = links.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); }).filter(Boolean);
  var activeSection = null;
  function mark() {
    var y = window.scrollY + Math.max(120, window.innerHeight * 0.35), cur = sections[0];
    for (var i = 0; i < sections.length; i++) { if (sections[i].offsetTop <= y) cur = sections[i]; }
    if (cur === activeSection) return;
    if (activeSection) byId[activeSection.id].removeAttribute("aria-current");
    if (cur) byId[cur.id].setAttribute("aria-current", "true");
    activeSection = cur;
  }
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (!ticking) { ticking = true; requestAnimationFrame(function () { ticking = false; mark(); }); }
  }, { passive: true });
  requestAnimationFrame(mark);

  /* ---- glossary hover cards. The definition text is read from the glossary at the foot of the page. */
  var tip = document.createElement("div");
  tip.className = "term-tip";
  tip.setAttribute("role", "tooltip");
  tip.id = "term-tip";
  tip.hidden = true;
  tip.innerHTML = '<div class="term-tip__label"></div><div class="term-tip__text"></div>';
  document.body.appendChild(tip);
  var current = null, hideTimer = null;
  function place(a) {
    var r = a.getBoundingClientRect();
    tip.style.left = "0px"; tip.style.top = "0px";
    var w = tip.offsetWidth, h = tip.offsetHeight, m = 8;
    var left = Math.max(m, Math.min(r.left, window.innerWidth - w - m));
    var above = r.top - h - m;
    var top = above > 60 ? above : Math.min(r.bottom + m, window.innerHeight - h - m);
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  function show(a) {
    var row = document.getElementById("g-" + a.getAttribute("data-term"));
    if (!row) return;
    clearTimeout(hideTimer);
    tip.firstChild.textContent = row.querySelector("dt").textContent;
    tip.lastChild.textContent = row.querySelector("dd").textContent;
    tip.hidden = false;
    current = a;
    a.setAttribute("aria-describedby", "term-tip");
    place(a);
  }
  function hide() {
    if (current) current.removeAttribute("aria-describedby");
    current = null; tip.hidden = true;
  }
  function later() { clearTimeout(hideTimer); hideTimer = setTimeout(hide, 140); }

  /* ---- the map of instances: switch condition, show a square's details, mark the same patient's squares */
  var map = document.querySelector(".map");
  if (map) {
    var sw = [].slice.call(map.querySelectorAll(".map__switch button"));
    var cells = [].slice.call(map.querySelectorAll(".map__cells .c"));
    var detail = map.querySelector(".map__detail");
    var chosen = null;
    var tabStop = cells[0];
    var patients = new Map();
    cells.forEach(function (cell) {
      var patient = cell.dataset.p;
      if (!patients.has(patient)) patients.set(patient, []);
      patients.get(patient).push(cell);
    });
    var highlighted = null;
    var samePatient = function (c) {
      var patient = c ? c.dataset.p : null;
      if (patient === highlighted) return;
      if (highlighted !== null) patients.get(highlighted).forEach(function (cell) { cell.classList.remove("same"); });
      if (patient !== null) patients.get(patient).forEach(function (cell) { cell.classList.add("same"); });
      highlighted = patient;
      map.classList.toggle("hl", patient !== null);
    };
    var describe = function (c) {
      var t = c.getAttribute("data-t"), cut = t.indexOf(". ");
      detail.textContent = "";
      var bEl = document.createElement("b"); bEl.textContent = t.slice(0, cut + 1) + " ";
      detail.appendChild(bEl); detail.appendChild(document.createTextNode(t.slice(cut + 2)));
      var ex = c.getAttribute("data-ex-" + map.getAttribute("data-arm"));
      if (ex !== null) {
        var a = document.createElement("a"); a.href = "#transcript-" + (Number(ex) + 1); a.textContent = "Open this run, step by step";
        detail.appendChild(document.createTextNode(" ")); detail.appendChild(a);
      }
    };
    var choose = function (c) {
      tip.hidden = true; current = null;
      samePatient(c);
      if (chosen === c) return;
      if (chosen) chosen.classList.remove("sel");
      tabStop.tabIndex = -1;
      c.classList.add("sel");
      c.tabIndex = 0;
      chosen = tabStop = c;
      describe(c);
    };
    sw.forEach(function (x) {
      x.addEventListener("click", function () {
        map.setAttribute("data-arm", x.getAttribute("data-arm"));
        sw.forEach(function (y) { y.setAttribute("aria-pressed", y === x ? "true" : "false"); });
        if (chosen) describe(chosen);
      });
    });
    /* three buttons step through the instances, for a reader who cannot or does not want to aim at a small square */
    var passes = function (c) {
      var arm = map.getAttribute("data-arm");
      return c.classList.contains(arm + "0") || c.classList.contains(arm + "1");
    };
    [].slice.call(map.querySelectorAll(".map__nav button")).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var step = btn.getAttribute("data-step"), i = chosen ? cells.indexOf(chosen) : -1, to = null;
        if (step === "fail") {
          for (var k = 1; k <= cells.length; k++) { var q = cells[(i + k + cells.length) % cells.length]; if (!passes(q)) { to = q; break; } }
        } else {
          to = cells[(i + Number(step) + cells.length) % cells.length] || cells[0];
        }
        if (to) choose(to);
      });
    });
    map.addEventListener("mouseover", function (e) {
      var c = e.target.closest && e.target.closest(".map__cells .c");
      if (!c || matchMedia("(hover: none)").matches) return;
      samePatient(c);
      clearTimeout(hideTimer);
      var t = c.getAttribute("data-t"), cut = t.indexOf(". ");
      tip.firstChild.textContent = t.slice(0, cut + 1);
      tip.lastChild.textContent = t.slice(cut + 2);
      tip.hidden = false; current = null; place(c);
    });
    map.addEventListener("mouseout", function (e) {
      if (e.target.closest && e.target.closest(".map__cells .c")) { later(); samePatient(chosen); }
    });
    map.addEventListener("click", function (e) {
      var c = e.target.closest && e.target.closest(".map__cells .c");
      if (c) choose(c);
    });
    map.addEventListener("focusin", function (e) {
      var c = e.target.closest && e.target.closest(".map__cells .c");
      if (c) choose(c);
    });
    /* arrow keys move between squares; up and down go to the nearest square in the row above or below */
    map.addEventListener("keydown", function (e) {
      var c = e.target.closest && e.target.closest(".map__cells .c");
      if (!c) return;
      var i = cells.indexOf(c), to = null;
      if (e.key === "ArrowRight") to = cells[i + 1];
      else if (e.key === "ArrowLeft") to = cells[i - 1];
      else if (e.key === "Home") to = cells[0];
      else if (e.key === "End") to = cells[cells.length - 1];
      else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        var r = c.getBoundingClientRect(), dir = e.key === "ArrowDown" ? 1 : -1, best = null, bestRow = null;
        for (var j = i + dir; j >= 0 && j < cells.length; j += dir) {
          var q = cells[j].getBoundingClientRect();
          if (Math.abs(q.top - r.top) < 2) continue;
          if (bestRow === null) bestRow = q.top;
          if (Math.abs(q.top - bestRow) > 2) break;
          if (best === null || Math.abs(q.left - r.left) < Math.abs(best.getBoundingClientRect().left - r.left)) best = cells[j];
        }
        to = best;
      }
      if (to) { e.preventDefault(); to.focus(); }
    });
  }

  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("a.term");
    if (a) show(a); else if (e.target.closest && e.target.closest(".term-tip")) clearTimeout(hideTimer);
  });
  document.addEventListener("mouseout", function (e) {
    if (e.target.closest && (e.target.closest("a.term") || e.target.closest(".term-tip"))) later();
  });
  document.addEventListener("focusin", function (e) { var a = e.target.closest && e.target.closest("a.term"); if (a) show(a); });
  document.addEventListener("focusout", function (e) { if (e.target.closest && e.target.closest("a.term")) later(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") hide(); });
  window.addEventListener("scroll", function () { if (current) hide(); }, { passive: true });
})();
