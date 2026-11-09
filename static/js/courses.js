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
  /* start page: the course is a drop-down with live search (value goes to the hidden field) */
  var pk = document.getElementById("coursePick");
  if (pk) {
    var pb = pk.querySelector(".pick-btn"), pp = pk.querySelector(".pick-panel"), pi = pp.querySelector("input"),
        pl = [].slice.call(pp.querySelectorAll("li")), pn = pp.querySelector(".combo-none"),
        hid = pk.querySelector("input[type=hidden]");
    function pclose() { pp.hidden = true; pb.setAttribute("aria-expanded", "false"); }
    function pick(li) {
      hid.value = li.getAttribute("data-code");
      pk.querySelector(".pick-label").textContent = li.getAttribute("data-title");
      pl.forEach(function (x) { x.classList.toggle("on", x === li); });
      pclose();
    }
    pb.addEventListener("click", function () {
      var open = pp.hidden; pp.hidden = !open; pb.setAttribute("aria-expanded", String(open));
      if (open) { pi.value = ""; filter(pi, pl, pn); pi.focus(); }
    });
    pi.addEventListener("input", function () { filter(pi, pl, pn); });
    pi.addEventListener("keydown", function (e) {
      if (e.key === "Escape") pclose();
      if (e.key === "Enter") { e.preventDefault(); var f = pl.filter(function (l) { return !l.hidden; })[0]; if (f) pick(f); }
    });
    pl.forEach(function (li) { li.addEventListener("click", function () { pick(li); }); });
    document.addEventListener("click", function (e) { if (!pk.contains(e.target)) pclose(); });
  }
  /* (old) live search above course cards */
  var s = document.getElementById("courseSearch");
  if (s) {
    var cards = [].slice.call(document.querySelectorAll(".course-card")), n = document.getElementById("courseNone");
    s.addEventListener("input", function () { filter(s, cards, n); });
    s.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  }
})();
