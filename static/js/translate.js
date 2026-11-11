/* Arabic UI: English course text is translated under the original (Google Translate through /translate). */
(function () {
  var cfg = window.STUDYMATE_TR; if (!cfg) return;
  function mostlyArabic(t) { var a = (t.match(/[\u0600-\u06ff]/g) || []).length, l = (t.match(/[A-Za-z\u0600-\u06ff]/g) || []).length; return a > 0.5 * l; }
  document.querySelectorAll('[data-tr]').forEach(function (el) {
    var text = el.innerText.trim(); if (!text || mostlyArabic(text)) return;
    var box = document.createElement('div'); box.className = 'tr-out small'; box.dir = 'rtl';
    box.style.cssText = 'margin-top:6px;padding:8px 10px;border-inline-start:3px solid var(--teal);background:rgba(0,150,136,.07);border-radius:6px';
    box.textContent = cfg.loading; el.insertAdjacentElement('afterend', box);
    fetch(cfg.url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: text})})
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) { box.innerHTML = '<b></b><div></div>'; box.firstChild.textContent = cfg.label + ': '; box.lastChild.textContent = d.text; } else { box.textContent = cfg.failed; box.style.opacity = .6; } })
      .catch(function () { box.textContent = cfg.failed; box.style.opacity = .6; });
  });
})();
