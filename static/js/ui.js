/* Count-up numbers, progress rings and bars of the home page; the date in the interface language. */
(function () {
  // every card / KPI of every page fades in one after the other
  var i = 1;
  document.querySelectorAll('main .card, main .kpi, main .result').forEach(function (el) {
    if (el.classList.contains('fade') || el.closest('.fade') || el.classList.contains('center-box')) return;
    el.classList.add('fade'); el.style.setProperty('--i', Math.min(i++, 6));
  });
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var to = parseInt(el.dataset.count, 10) || 0, t0 = null;
    if (reduce || to === 0) { el.textContent = to; return; }
    function step(ts) { if (!t0) t0 = ts; var k = Math.min(1, (ts - t0) / 900); el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  });
  setTimeout(function () {
    document.querySelectorAll('.ring[data-p]').forEach(function (r) { r.style.setProperty('--p', r.dataset.p); });
    document.querySelectorAll('.fill[data-w]').forEach(function (f) { f.style.width = f.dataset.w + '%'; });
    document.querySelectorAll('.bar i[data-h]').forEach(function (f) { f.style.height = f.dataset.h + '%'; });
  }, 120);
  var d = document.getElementById('today');
  if (d) { try { d.textContent = new Date(d.dataset.iso + 'T12:00:00').toLocaleDateString(document.documentElement.lang === 'ar' ? 'ar-EG' : 'en-GB', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'}); } catch (e) {} }
})();
