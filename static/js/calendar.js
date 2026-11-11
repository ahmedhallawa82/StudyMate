// Month calendar: weeks start on Saturday. Events come from <script id="events"> as JSON.
(function () {
  var C = window.CAL, ev = JSON.parse(document.getElementById('events').textContent || '[]');
  var loc = C.lang === 'ar' ? 'ar-EG' : 'en-GB';
  var cal = document.getElementById('cal'), mSel = document.getElementById('month'), yIn = document.getElementById('year');
  var now = new Date(), cur = new Date(now.getFullYear(), now.getMonth(), 1), sel = iso(now);
  function iso(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  var by = {};
  ev.forEach(function (e) { (by[e.date] = by[e.date] || []).push(e); });
  for (var m = 0; m < 12; m++) { var o = document.createElement('option'); o.value = m; o.textContent = new Date(2024, m, 1).toLocaleDateString(loc, {month: 'long'}); mSel.appendChild(o); }
  function render() {
    mSel.value = cur.getMonth(); yIn.value = cur.getFullYear();
    var html = '';
    for (var i = 0; i < 7; i++) { var wd = new Date(2024, 0, 6 + i); html += '<div class="cal-h">' + wd.toLocaleDateString(loc, {weekday: 'short'}) + '</div>'; }   // 6 Jan 2024 = Saturday
    var first = new Date(cur.getFullYear(), cur.getMonth(), 1), lead = (first.getDay() + 1) % 7;
    var days = new Date(cur.getFullYear(), cur.getMonth() + 1, 0).getDate();
    for (i = 0; i < lead; i++) html += '<div class="cal-d off"></div>';
    for (var d = 1; d <= days; d++) {
      var k = iso(new Date(cur.getFullYear(), cur.getMonth(), d)), list = by[k] || [];
      var dots = '', hasS = list.some(function (e) { return e.kind === 'scheduled'; }), hasA = list.some(function (e) { return e.kind === 'attempt'; });
      if (hasS) dots += '<i class="dot-s"></i>'; if (hasA) dots += '<i class="dot-a"></i>';
      html += '<button type="button" class="cal-d' + (k === iso(now) ? ' today' : '') + (k === sel ? ' sel' : '') + (list.length ? ' has' : '') + '" data-k="' + k + '"><b>' + d + '</b><span>' + dots + '</span></button>';
    }
    cal.innerHTML = html;
    cal.querySelectorAll('.cal-d[data-k]').forEach(function (b) { b.addEventListener('click', function () { sel = b.dataset.k; render(); showDay(); }); });
  }
  function card(e) {
    var del = e.mine ? '<button type="button" class="ev-del" data-id="' + e.id + '">' + esc(C.del) + '</button>' : '';
    var t = '<span class="ev-t k-' + e.kind + '"><b>' + esc(e.title) + '</b><small>' + esc(e.time) + ' · ' + esc(e.course) + (e.sub ? ' · ' + esc(e.sub) : '') + '</small></span>';
    return (e.link ? '<a class="ev" href="' + e.link + '">' + t + '</a>' : '<div class="ev">' + t + del + '</div>');
  }
  function showDay() {
    var d = new Date(sel + 'T12:00:00');
    document.getElementById('dayTitle').textContent = d.toLocaleDateString(loc, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
    var l = (by[sel] || []).slice().sort(function (a, b) { return a.time < b.time ? -1 : 1; });
    document.getElementById('dayList').innerHTML = l.length ? l.map(card).join('') : '<p class="muted small">' + esc(C.none) + '</p>';
    bindDel();
  }
  function bindDel() { document.querySelectorAll('.ev-del').forEach(function (b) { b.addEventListener('click', function () { if (confirm('?')) { document.getElementById('delId').value = b.dataset.id; document.getElementById('delForm').submit(); } }); }); }
  function upcoming() {
    var t = iso(now), l = ev.filter(function (e) { return e.kind === 'scheduled' && e.date >= t; }).sort(function (a, b) { return (a.date + a.time) < (b.date + b.time) ? -1 : 1; }).slice(0, 6);
    document.getElementById('upList').innerHTML = l.length ? l.map(function (e) {
      return '<div class="ev"><span class="ev-t k-scheduled"><b>' + esc(e.title) + '</b><small>' + new Date(e.date + 'T12:00:00').toLocaleDateString(loc, {day: 'numeric', month: 'short'}) + ' ' + esc(e.time) + ' · ' + esc(e.course) + '</small></span></div>';
    }).join('') : '<p class="muted small">' + esc(C.noneUp) + '</p>';
  }
  document.getElementById('prev').onclick = function () { cur = new Date(cur.getFullYear(), cur.getMonth() - 1, 1); render(); };
  document.getElementById('next').onclick = function () { cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1); render(); };
  document.getElementById('calToday').onclick = function () { cur = new Date(now.getFullYear(), now.getMonth(), 1); sel = iso(now); render(); showDay(); };
  mSel.onchange = function () { cur = new Date(cur.getFullYear(), +mSel.value, 1); render(); };
  yIn.onchange = function () { var y = parseInt(yIn.value, 10); if (y > 1999 && y < 2101) { cur = new Date(y, cur.getMonth(), 1); render(); } };
  render(); showDay(); upcoming();
})();
