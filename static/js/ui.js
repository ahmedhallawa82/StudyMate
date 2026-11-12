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
  if (d) {
    var loc = document.documentElement.lang === 'ar' ? 'ar-EG' : 'en-GB';
    var tick = function () {
      try {
        var n = new Date();
        d.textContent = n.toLocaleDateString(loc, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'}) + ' · ' +
                        n.toLocaleTimeString(loc, {hour: '2-digit', minute: '2-digit', second: '2-digit'});
      } catch (e) {}
    };
    tick(); setInterval(tick, 1000);
  }
})();


/* course dropdown */
(function () {
  document.querySelectorAll('[data-cmenu]').forEach(function (m) {
    var btn = m.querySelector('.cmenu-btn'), panel = m.querySelector('.cmenu-panel'), q = m.querySelector('.cmenu-search');
    function set(open) { panel.hidden = !open; m.classList.toggle('open', open); btn.setAttribute('aria-expanded', open ? 'true' : 'false'); if (open && q) q.focus(); }
    btn.addEventListener('click', function (e) { e.stopPropagation(); set(panel.hidden); });
    document.addEventListener('click', function (e) { if (!m.contains(e.target)) set(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
    if (q) q.addEventListener('input', function () {
      var v = q.value.trim().toLowerCase();
      m.querySelectorAll('.cmenu-item').forEach(function (a) { a.style.display = (!v || a.dataset.name.indexOf(v) > -1) ? '' : 'none'; });
    });
  });
})();


/* upload progress: every form with a file field shows a progress bar, then "reading the file" while the server works */
(function () {
  var L = document.documentElement.lang === 'ar'
    ? {up: 'جاري رفع الملف…', read: 'اكتمل الرفع، جاري قراءة الملف…', keep: 'من فضلك متقفلش الصفحة.', err: 'فشل الرفع. جرّب تاني.', file: 'ملف'}
    : {up: 'Uploading…', read: 'Upload finished, reading the file…', keep: 'Please keep this page open.', err: 'Upload failed. Please try again.', file: 'file'};
  document.querySelectorAll('form[enctype="multipart/form-data"]').forEach(function (f) {
    if (f.hasAttribute('data-noprogress') || !window.XMLHttpRequest || !window.FormData) return;
    f.addEventListener('submit', function (e) {
      var files = f.querySelectorAll('input[type=file]'), has = false;
      files.forEach(function (i) { if (i.files && i.files.length) has = true; });
      if (!has || (f.checkValidity && !f.checkValidity())) return;
      e.preventDefault();
      var box = document.createElement('div'); box.className = 'up-overlay'; box.setAttribute('role', 'status');
      box.innerHTML = '<div class="up-card"><div class="up-spin"></div><b class="up-t"></b><div class="up-bar"><i></i></div><small class="up-p"></small><small>' + L.keep + '</small></div>';
      document.body.appendChild(box);
      var t = box.querySelector('.up-t'), bar = box.querySelector('i'), pct = box.querySelector('.up-p');
      t.textContent = L.up;
      f.querySelectorAll('button[type=submit]').forEach(function (b) { b.disabled = true; });
      var fd = new FormData(f);
      if (e.submitter && e.submitter.name) fd.append(e.submitter.name, e.submitter.value);
      var x = new XMLHttpRequest();
      x.open((f.getAttribute('method') || 'post').toUpperCase(), f.getAttribute('action') || location.href);   // not f.action: a field named "action" shadows it
      x.upload.onprogress = function (ev) {
        if (!ev.lengthComputable) return;
        var p = Math.round(ev.loaded / ev.total * 100); bar.style.width = p + '%';
        pct.textContent = p + '%  (' + (ev.loaded / 1048576).toFixed(1) + ' / ' + (ev.total / 1048576).toFixed(1) + ' MB)';
        if (p >= 100) t.textContent = L.read;
      };
      x.onload = function () {
        try { history.replaceState(null, '', x.responseURL || location.href); } catch (er) {}
        document.open(); document.write(x.responseText); document.close();
      };
      x.onerror = function () { box.remove(); f.querySelectorAll('button[type=submit]').forEach(function (b) { b.disabled = false; }); alert(L.err); };
      x.send(fd);
    });
  });
})();
