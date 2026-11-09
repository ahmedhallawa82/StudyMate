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
  /* same live search above the course cards on the start page */
  var s = document.getElementById("courseSearch");
  if (s) {
    var cards = [].slice.call(document.querySelectorAll(".course-card")), n = document.getElementById("courseNone");
    s.addEventListener("input", function () { filter(s, cards, n); });
    s.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  }
})();
