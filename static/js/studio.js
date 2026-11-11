/* Study Studio: tabs, flashcards, quiz, table filter, concept map, infographic, read aloud. All data comes from #studioData. */
(function () {
  var D = JSON.parse(document.getElementById('studioData').textContent);
  var K = D.kit, U = D.ui;
  var cur = D.tool || 'quiz';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var fmt = function (s, o) { return s.replace(/\{(\w+)\}/g, function (_, k) { return o[k]; }); };
  var el = function (tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  var css = function (v, d) { return (getComputedStyle(document.documentElement).getPropertyValue(v) || d).trim() || d; };

  window.studioTool = function () { return cur; };

  /* ---------- tabs ---------- */
  function show(tool) {
    cur = tool;
    $$('.st-tile[data-tool]').forEach(function (b) { var on = b.dataset.tool === tool; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); });
    $$('.st-pane').forEach(function (p) { p.hidden = p.dataset.pane !== tool; });
    var u = new URL(location.href); u.searchParams.set('tool', tool); history.replaceState(null, '', u);
    if (tool === 'info') drawInfographic();
    if (tool !== 'listen') stopSpeak();
  }
  $$('.st-tile[data-tool]').forEach(function (b) { b.addEventListener('click', function () { show(b.dataset.tool); }); });

  /* ---------- flashcards ---------- */
  var deck, known, firstTry, flipped, total;
  function flashReset() {
    deck = K.cards.slice(); total = deck.length; known = 0; firstTry = {}; flipped = false; flashDraw();
  }
  function flashDraw() {
    var box = $('#stFlash'); box.innerHTML = '';
    if (!total) { box.appendChild(el('p', 'muted', U.nocards)); return; }
    if (!deck.length) {
      var done = el('div', 'st-done'); done.appendChild(el('div', 'big', '🎉')); done.appendChild(el('h3', '', U.deck_done));
      done.appendChild(el('p', 'muted', fmt(U.known_n, { a: Object.keys(firstTry).filter(function (k) { return firstTry[k]; }).length, b: total })));
      var again = el('button', 'btn', '↺'); again.type = 'button'; again.addEventListener('click', flashReset); done.appendChild(again); box.appendChild(done); return;
    }
    var c = deck[0];
    box.appendChild(el('div', 'muted small', fmt(U.card_of, { i: Math.min(known + 1, total), n: total })));
    var card = el('button', 'st-card' + (flipped ? ' back' : '')); card.type = 'button'; card.dir = 'auto';
    card.appendChild(el('span', 'st-lab', flipped ? U.def : U.term));
    card.appendChild(el('span', 'st-big', flipped ? c.back : c.front));
    if (!flipped && c.ar) card.appendChild(el('span', 'st-ar', c.ar));
    card.appendChild(el('span', 'muted small', (c.lecture ? 'L' + c.lecture + ' · ' : '') + fmt(U.slide, { n: c.slide })));
    card.addEventListener('click', function () { flipped = !flipped; flashDraw(); });
    box.appendChild(card);
    var row = el('div', 'actions');
    var flip = el('button', 'btn ghost', U.flip), learn = el('button', 'btn st-learn', U.learning), kn = el('button', 'btn teal', U.know);
    [flip, learn, kn].forEach(function (b) { b.type = 'button'; row.appendChild(b); });
    flip.addEventListener('click', function () { flipped = !flipped; flashDraw(); });
    learn.addEventListener('click', function () { var x = deck.shift(); if (!(x.front in firstTry)) firstTry[x.front] = false; deck.push(x); flipped = false; flashDraw(); });
    kn.addEventListener('click', function () { var x = deck.shift(); if (!(x.front in firstTry)) firstTry[x.front] = true; known++; flipped = false; flashDraw(); });
    box.appendChild(row);
  }

  /* ---------- quiz ---------- */
  var qi, score, answered;
  function quizReset() { qi = 0; score = 0; answered = false; quizDraw(); }
  function quizDraw() {
    var box = $('#stQuiz'); box.innerHTML = '';
    var Q = K.quiz;
    if (!Q.length) { box.appendChild(el('p', 'muted', U.noquiz)); return; }
    if (qi >= Q.length) {
      var done = el('div', 'st-done'); done.appendChild(el('div', 'big', score >= Q.length * 0.7 ? '🎉' : '💪'));
      done.appendChild(el('h3', '', fmt(U.score, { a: score, b: Q.length })));
      var again = el('button', 'btn', '↺'); again.type = 'button'; again.addEventListener('click', quizReset); done.appendChild(again); box.appendChild(done); return;
    }
    var q = Q[qi];
    box.appendChild(el('div', 'muted small', fmt(U.q_of, { i: qi + 1, n: Q.length, l: q.lecture })));
    box.appendChild(el('div', 'muted small', q.kind === 'term' ? U.q_term : U.q_gap));
    var qt = el('div', 'st-q', q.q); qt.dir = 'ltr'; box.appendChild(qt);
    var opts = el('div', 'st-opts'); box.appendChild(opts);
    var fb = el('div', 'st-fb'); box.appendChild(fb);
    var nextBtn = el('button', 'btn', qi + 1 === Q.length ? U.finish : U.next); nextBtn.type = 'button'; nextBtn.hidden = true; box.appendChild(nextBtn);
    answered = false;
    q.options.forEach(function (o, i) {
      var b = el('button', 'st-opt', o); b.type = 'button'; b.dir = 'ltr';
      b.addEventListener('click', function () {
        if (answered) return; answered = true;
        var ok = i === q.answer; if (ok) score++;
        $$('.st-opt', opts).forEach(function (x, j) { x.disabled = true; if (j === q.answer) x.classList.add('ok'); else if (j === i) x.classList.add('bad'); });
        fb.appendChild(el('b', ok ? 'ok' : 'bad', (ok ? U.right : U.wrong) + ' '));
        fb.appendChild(document.createTextNode(fmt(U.from_slide, { n: q.slide }) + ' '));
        var why = el('span', 'muted', q.why); why.dir = 'ltr'; fb.appendChild(why);
        nextBtn.hidden = false;
      });
      opts.appendChild(b);
    });
    nextBtn.addEventListener('click', function () { qi++; quizDraw(); });
  }

  /* ---------- table filter ---------- */
  var f = $('#stFilter');
  if (f) f.addEventListener('input', function () {
    var v = f.value.toLowerCase();
    $$('#stTable tbody tr').forEach(function (r) { r.hidden = v && r.textContent.toLowerCase().indexOf(v) < 0; });
  });

  /* ---------- concept map ---------- */
  var NS = 'http://www.w3.org/2000/svg';
  function svgEl(n, a) { var e = document.createElementNS(NS, n); Object.keys(a || {}).forEach(function (k) { e.setAttribute(k, a[k]); }); return e; }
  function drawMap() {
    var M = K.map, box = $('#stMap'); box.innerHTML = '';
    var svg = svgEl('svg', { viewBox: '0 0 ' + M.w + ' ' + M.h, role: 'img', 'aria-label': 'concept map', id: 'stMapSvg' });
    var byId = {}; M.nodes.forEach(function (n) { byId[n.id] = n; });
    var teal = css('--teal', '#2f6f6a'), orange = css('--orange', '#e4572e'), line = css('--line', '#dde5e4'), card = css('--card', '#fff'), ink = css('--ink', '#1f2a2a');
    M.links.forEach(function (l) {
      var a = byId[l.a], b = byId[l.b]; if (!a || !b) return;
      svg.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: l.kind === 'prereq' ? orange : teal, 'stroke-opacity': l.kind === 'prereq' ? .7 : .45, 'stroke-width': l.kind === 'main' ? 2.5 : 1.6, 'stroke-dasharray': l.kind === 'prereq' ? '6 5' : '' }));
    });
    M.nodes.forEach(function (n) {
      var g = svgEl('g', { 'class': 'st-node ' + n.kind, tabindex: 0, role: 'button' });
      var h = n.h;
      var fill = n.kind === 'root' ? teal : card, stroke = n.kind === 'term' ? line : teal;
      g.appendChild(svgEl('rect', { x: n.x - n.w / 2, y: n.y - h / 2, width: n.w, height: h, rx: n.kind === 'term' ? 15 : 12, fill: fill, stroke: stroke, 'stroke-width': n.kind === 'topic' ? 2 : 1.5 }));
      var fs = n.kind === 'root' ? 16 : n.kind === 'topic' ? 14 : 13, lh = fs + 6, y0 = n.y - (n.lines.length - 1) * lh / 2 + fs * 0.35;
      var t = svgEl('text', { x: n.x, y: y0, 'text-anchor': 'middle', 'font-size': fs, 'font-weight': n.kind === 'term' ? 500 : 700, fill: n.kind === 'root' ? '#fff' : ink });
      n.lines.forEach(function (ln, i) { var sp = svgEl('tspan', { x: n.x, dy: i ? lh : 0 }); sp.textContent = ln; t.appendChild(sp); });
      g.appendChild(t);
      var pick = function () {
        $$('.st-node.sel', box).forEach(function (x) { x.classList.remove('sel'); }); g.classList.add('sel');
        var info = $('#stMapInfo');
        info.textContent = n.slides && n.slides.length ? fmt(U.map_slides, { s: n.slides.map(function (s) { return 'L' + s[0] + '·S' + s[1]; }).join(', ') }) : U.map_pick;
      };
      g.addEventListener('click', pick); g.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
      svg.appendChild(g);
    });
    box.appendChild(svg);
  }
  function downloadSvgPng() {
    var svg = $('#stMapSvg'); if (!svg) return;
    var clone = svg.cloneNode(true); clone.setAttribute('xmlns', NS);
    var M = K.map, bg = css('--card', '#ffffff');
    clone.setAttribute('width', M.w * 2); clone.setAttribute('height', M.h * 2);
    clone.insertBefore(svgEl('rect', { x: 0, y: 0, width: M.w, height: M.h, fill: bg }), clone.firstChild);
    clone.querySelectorAll('text').forEach(function (t) { t.setAttribute('font-family', 'Segoe UI, Arial, sans-serif'); });
    var url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' }));
    var img = new Image();
    img.onload = function () {
      var c = document.createElement('canvas'); c.width = M.w * 2; c.height = M.h * 2; c.getContext('2d').drawImage(img, 0, 0); URL.revokeObjectURL(url);
      saveCanvas(c, 'mind-map');
    };
    img.src = url;
  }
  function saveCanvas(c, name) {
    var a = document.createElement('a'); a.download = 'studymate-' + name + (K.lecture ? '-L' + K.lecture : '') + '.png'; a.href = c.toDataURL('image/png'); document.body.appendChild(a); a.click(); a.remove();
  }

  /* ---------- infographic (drawn on a canvas, so what you see is what you download) ---------- */
  function wrap(ctx, text, x, y, maxW, lh, maxLines) {
    var words = text.split(/\s+/), line = '', n = 0;
    for (var i = 0; i < words.length; i++) {
      var test = line ? line + ' ' + words[i] : words[i];
      if (ctx.measureText(test).width > maxW && line) {
        if (maxLines && n + 1 >= maxLines) { ctx.fillText(line.replace(/\s+\S*$/, '') + '…', x, y); return y + lh; }
        ctx.fillText(line, x, y); y += lh; n++; line = words[i];
      } else line = test;
    }
    ctx.fillText(line, x, y); return y + lh;
  }
  function rrect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function drawInfographic() {
    var c = $('#stIg'); c.height = 2600; var end = paintInfographic(c); c.height = Math.max(900, end + 40); paintInfographic(c);
  }
  function paintInfographic(c) {
    var ctx = c.getContext('2d'), W = c.width, H = c.height;
    var teal = css('--teal', '#2f6f6a'), soft = css('--teal-soft', '#e8f1f0'), orange = css('--orange', '#e4572e'), ink = css('--ink', '#1f2a2a'), muted = css('--muted', '#5d6b6a'), bg = css('--card', '#ffffff'), line = css('--line', '#dde5e4');
    var FONT = '"Segoe UI", Arial, sans-serif';
    ctx.clearRect(0, 0, W, H); ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = teal; ctx.fillRect(0, 0, W, 230);
    ctx.fillStyle = '#fff'; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left'; ctx.direction = 'ltr';
    ctx.font = '600 24px ' + FONT; ctx.globalAlpha = .85; ctx.fillText(U.course, 60, 80); ctx.globalAlpha = 1;
    ctx.font = '700 52px ' + FONT; wrap(ctx, K.title || U.course, 60, 150, W - 120, 58, 2);
    var stats = [[U.slides_n, K.info.slides], [U.terms_n, K.info.terms], [U.minutes, fmt(U.min, { n: K.info.minutes })]];
    stats.forEach(function (s, i) {
      var w = (W - 120 - 40) / 3, x = 60 + i * (w + 20), y = 262;
      ctx.fillStyle = soft; rrect(ctx, x, y, w, 120, 18); ctx.fill();
      ctx.fillStyle = muted; ctx.font = '600 20px ' + FONT; ctx.fillText(String(s[0]).toUpperCase(), x + 22, y + 40);
      ctx.fillStyle = teal; ctx.font = '700 44px ' + FONT; ctx.fillText(String(s[1]), x + 22, y + 92);
    });
    var y = 450; ctx.fillStyle = ink; ctx.font = '700 30px ' + FONT; ctx.fillText(U.ig_points, 60, y); y += 18;
    K.summary.slice(0, 5).forEach(function (s, i) {
      y += 24; ctx.fillStyle = orange; ctx.beginPath(); ctx.arc(80, y + 2, 17, 0, 7); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.font = '700 18px ' + FONT; ctx.textAlign = 'center'; ctx.fillText(String(i + 1), 80, y + 9); ctx.textAlign = 'left';
      ctx.fillStyle = ink; ctx.font = '400 24px ' + FONT; y = wrap(ctx, s.text, 116, y + 8, W - 190, 32, 3) + 6;
    });
    y += 20; ctx.fillStyle = ink; ctx.font = '700 30px ' + FONT; ctx.fillText(U.ig_terms, 60, y); y += 30;
    var x = 60; ctx.font = '600 22px ' + FONT;
    K.keywords.slice(0, 10).forEach(function (k) {
      var w = ctx.measureText(k).width + 36; if (x + w > W - 60) { x = 60; y += 56; }
      ctx.fillStyle = soft; rrect(ctx, x, y, w, 42, 21); ctx.fill(); ctx.fillStyle = teal; ctx.fillText(k, x + 18, y + 29); x += w + 12;
    });
    y += 90; if (K.info.topics.length) {
      ctx.fillStyle = ink; ctx.font = '700 30px ' + FONT; ctx.fillText(U.ig_topics, 60, y); y += 30; x = 60; ctx.font = '600 22px ' + FONT;
      K.info.topics.slice(0, 8).forEach(function (k) {
        var w = ctx.measureText(k).width + 36; if (x + w > W - 60) { x = 60; y += 56; }
        ctx.strokeStyle = teal; ctx.lineWidth = 2; rrect(ctx, x, y, w, 42, 21); ctx.stroke(); ctx.fillStyle = ink; ctx.fillText(k, x + 18, y + 29); x += w + 12;
      });
    }
    y += 56; ctx.fillStyle = line; ctx.fillRect(60, y, W - 120, 2);
    ctx.fillStyle = muted; ctx.font = '500 20px ' + FONT; ctx.fillText('StudyMate · ' + U.ig_footer, 60, y + 42);
    return y + 42;
  }

  /* ---------- read aloud: notes one under the other, English or Arabic voice ---------- */
  var synth = window.speechSynthesis, queue = [], qpos = -1, paused = false, playing = false;
  function listLang() { var r = document.querySelector('input[name="stLang"]:checked'); return r ? r.value : 'en'; }
  function stopSpeak() {
    if (synth) synth.cancel(); queue = []; qpos = -1; paused = false; playing = false;
    var b = $('#stPlay'); if (b) b.textContent = '▶ ' + U.play_all;
    $$('.st-note.now').forEach(function (x) { x.classList.remove('now'); });
  }
  function arLead(i, n) { return U.ar_note.replace('{i}', i); }
  function segmentsFor(i, lang) {                    // what to say for note i, as [{text, lang}]
    var n = (K.notes || [])[i], out = [];
    if (!n) return out;
    if (lang === 'ar') {
      out.push({ text: n.kind === 'term' ? U.ar_term : U.ar_note.replace('{i}', i + 1), lang: 'ar-EG' });
      if (n.kind === 'term' && n.ar) out.push({ text: n.ar, lang: 'ar-EG' });
    }
    out.push({ text: n.text, lang: 'en-US' });
    return out;
  }
  function speakFrom(idxs) {
    if (!synth) { $('#stVoiceNote').hidden = false; return; }
    stopSpeak(); playing = true; $('#stPlay').textContent = '⏸ ' + U.pause;
    var lang = listLang(), rate = parseFloat($('#stRate').value) || 1, segs = [];
    idxs.forEach(function (i) { segmentsFor(i, lang).forEach(function (s) { s.i = i; segs.push(s); }); });
    queue = segs; qpos = 0;
    (function next() {
      if (!playing || qpos >= queue.length) { stopSpeak(); return; }
      var s = queue[qpos++], u = new SpeechSynthesisUtterance(s.text); u.lang = s.lang; u.rate = rate;
      $$('.st-note.now').forEach(function (x) { x.classList.remove('now'); });
      var li = $('#stNote' + s.i); if (li) li.classList.add('now');
      u.onend = next; u.onerror = next; synth.speak(u);
    })();
  }
  function listenAll() {
    if (playing && synth) { if (paused) { synth.resume(); paused = false; $('#stPlay').textContent = '⏸ ' + U.pause; } else { synth.pause(); paused = true; $('#stPlay').textContent = '▶ ' + U.play; } return; }
    speakFrom((K.notes || []).map(function (_, i) { return i; }));
  }

  /* ---------- videos: play inside the page ---------- */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.st-vid'); if (!b) return;
    var box = $('#stPlayerBox'), wrap = $('#stPlayer'); box.innerHTML = '';
    if (b.dataset.kind === 'yt') {
      var f = document.createElement('iframe');
      f.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(b.dataset.src) + '?rel=0&autoplay=1';
      f.allow = 'accelerometer; autoplay; encrypted-media; picture-in-picture; fullscreen'; f.allowFullscreen = true; f.title = b.dataset.title;
      box.appendChild(f);
    } else {
      var v = document.createElement('video'); v.controls = true; v.autoplay = true; v.preload = 'metadata'; v.src = b.dataset.src; v.setAttribute('controlsList', 'nodownload');
      box.appendChild(v);
    }
    $('#stPlayerTitle').textContent = b.dataset.title; wrap.hidden = false; wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  /* ---------- buttons ---------- */
  document.addEventListener('click', function (e) {
    var a = e.target.closest('[data-act]'); if (!a) return;
    var k = a.dataset.act;
    if (k === 'print') { document.body.classList.add('st-printing'); window.print(); setTimeout(function () { document.body.classList.remove('st-printing'); }, 400); }
    else if (k === 'flash-reset') flashReset();
    else if (k === 'quiz-reset') quizReset();
    else if (k === 'mind-png') downloadSvgPng();
    else if (k === 'info-png') { drawInfographic(); saveCanvas($('#stIg'), 'infographic'); }
    else if (k === 'listen-play') listenAll();
    else if (k === 'listen-one') speakFrom([parseInt(a.dataset.i, 10)]);
    else if (k === 'listen-stop') stopSpeak();
  });
  window.addEventListener('beforeunload', stopSpeak);

  flashReset(); quizReset(); drawMap(); if (cur === 'info') drawInfographic();
})();
