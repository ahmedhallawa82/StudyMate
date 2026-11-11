/* Course picker with live search: type a letter and only the matching courses stay in the list. */
(function () {
  function filter(input, items, none) {
    var q = input.value.trim().toLowerCase(), shown = 0;
    items.forEach(function (li) {
      var ok = !q || (li.getAttribute("data-q") || li.textContent.toLowerCase()).indexOf(q) !== -1;
      li.hidden = !ok; if (ok) shown++;
    });
    if (none) none.hidden = shown > 0;
  }
  var box = document.getElementById("courseCombo");
  if (box) {
    var btn = box.querySelector("button"), panel = box.querySelector(".combo-panel"),
        input = box.querySelector("input"), items = [].slice.call(box.querySelectorAll("li")),
        none = box.querySelector(".combo-none");
    function close() { panel.hidden = true; btn.setAttribute("aria-expanded", "false"); }
    btn.addEventListener("click", function () {
      var open = panel.hidden; panel.hidden = !open; btn.setAttribute("aria-expanded", String(open));
      if (open) { input.value = ""; filter(input, items, none); input.focus(); }
    });
    input.addEventListener("input", function () { filter(input, items, none); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
      if (e.key === "Enter") { e.preventDefault(); var f = items.filter(function (l) { return !l.hidden; })[0]; if (f) f.click(); }
    });
    items.forEach(function (li) {
      li.addEventListener("click", function () {
        location.href = box.getAttribute("data-url").replace("__C__", li.getAttribute("data-code")) +
                        "?next=" + encodeURIComponent(location.pathname);
      });
    });
    document.addEventListener("click", function (e) { if (!box.contains(e.target)) close(); });
  }
  /* start page: type straight into the course field; the list below narrows as you type */
  var pk = document.getElementById("coursePick");
  if (pk && pk.querySelector(".pick-panel")) {
    var pi = pk.querySelector(".pick-input"), pp = pk.querySelector(".pick-panel"),
        pl = [].slice.call(pp.querySelectorAll("li")), pn = pp.querySelector(".combo-none"),
        hid = pk.querySelector("input[type=hidden]"), cur = pi.value, hi = -1;
    function vis() { return pl.filter(function (l) { return !l.hidden; }); }
    function mark(i) {
      var v = vis(); hi = Math.max(-1, Math.min(i, v.length - 1));
      pl.forEach(function (l) { l.classList.remove("hi"); });
      if (hi >= 0) { v[hi].classList.add("hi"); v[hi].scrollIntoView({ block: "nearest" }); }
    }
    function popen() { pp.hidden = false; pi.setAttribute("aria-expanded", "true"); }
    function pclose() { pp.hidden = true; pi.setAttribute("aria-expanded", "false"); pi.value = cur; hi = -1; }
    function pick(li) {
      hid.value = li.getAttribute("data-code"); cur = li.getAttribute("data-title");
      pl.forEach(function (x) { x.classList.toggle("on", x === li); });
      pclose();
    }
    pi.addEventListener("focus", function () { pi.select(); pl.forEach(function (l) { l.hidden = false; }); if (pn) pn.hidden = true; popen(); });
    pi.addEventListener("click", function () { popen(); });
    pi.addEventListener("input", function () { popen(); filter(pi, pl, pn); mark(0); });
    pi.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { pclose(); pi.blur(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); popen(); mark(hi + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); mark(hi - 1); }
      else if (e.key === "Enter") { e.preventDefault(); var v = vis(); var f = v[hi >= 0 ? hi : 0]; if (f) pick(f); }
    });
    pl.forEach(function (li) {
      li.addEventListener("mousedown", function (e) { e.preventDefault(); });   /* keep the focus in the field */
      li.addEventListener("click", function () { pick(li); pi.blur(); });
    });
    pk.querySelector(".pick-arrow").addEventListener("click", function () { pi.focus(); });
    document.addEventListener("click", function (e) { if (!pk.contains(e.target) && !pp.hidden) pclose(); });
  }
  /* (old) live search above course cards */
  var s = document.getElementById("courseSearch");
  if (s) {
    var cards = [].slice.call(document.querySelectorAll(".course-card")), n = document.getElementById("courseNone");
    s.addEventListener("input", function () { filter(s, cards, n); });
    s.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  }
})();
