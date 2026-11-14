/* Chat assistant: sends one message to /assistant and shows the answer with buttons that open the page. */
(function () {
  var C = window.STUDYMATE_AS, fab = document.getElementById('asFab'), panel = document.getElementById('asPanel');
  if (!C || !fab || !panel) return;
  var log = document.getElementById('asLog'), form = document.getElementById('asForm'), input = document.getElementById('asInput'),
      chips = document.getElementById('asChips'), busy = false;

  function open(on) {
    panel.hidden = !on; fab.setAttribute('aria-expanded', on ? 'true' : 'false'); fab.classList.toggle('on', on);
    if (on) { setTimeout(function () { input.focus(); }, 50); }
  }
  fab.addEventListener('click', function () { open(panel.hidden); });
  document.getElementById('asClose').addEventListener('click', function () { open(false); fab.focus(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) { open(false); fab.focus(); } });

  function add(text, who, actions) {
    var m = document.createElement('div'); m.className = 'as-msg ' + who; m.textContent = text;     // text only: never HTML
    if (actions && actions.length) {
      var row = document.createElement('div'); row.className = 'as-acts';
      actions.forEach(function (a) {
        var el;
        if (a.url) { el = document.createElement('a'); el.href = a.url; }
        else {
          if (a.click && !document.querySelector(a.click)) return;           // the button does not exist for this person
          el = document.createElement('button'); el.type = 'button';
          el.addEventListener('click', function () { var t = document.querySelector(a.click); if (t) { open(false); t.click(); } });
        }
        el.className = 'btn teal as-act'; el.textContent = a.label; row.appendChild(el);
      });
      if (row.childNodes.length) m.appendChild(row);
    }
    log.appendChild(m); log.scrollTop = log.scrollHeight; return m;
  }

  function send(text) {
    text = (text || '').trim(); if (!text || busy) return;
    busy = true; chips.hidden = true; add(text, 'me'); input.value = '';
    var wait = add(C.wait, 'bot wait');
    fetch(C.url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({q: text}), credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (j) { wait.remove(); if (j && j.ok) add(j.answer, 'bot', j.actions); else add(C.err, 'bot'); })
      .catch(function () { wait.remove(); add(C.err, 'bot'); })
      .then(function () { busy = false; input.focus(); });
  }
  form.addEventListener('submit', function (e) { e.preventDefault(); send(input.value); });
  chips.addEventListener('click', function (e) { var b = e.target.closest('.as-chip'); if (b) send(b.textContent); });
})();
