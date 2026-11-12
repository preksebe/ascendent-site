/* Fereastra de chat Ascendent: un buton roșu în colțul din dreapta jos care deschide asistentul.
   Asistentul răspunde doar din proprietățile de pe site (serverul: POST /api/chat). */
(function () {
  if (window.__ascendentChat) return;
  window.__ascendentChat = true;
  var NB = ' ';
  var css = [
    '.ac-buton{position:fixed;right:18px;bottom:18px;z-index:9000;display:flex;align-items:center;gap:8px;background:#c8102e;color:#fff;border:0;border-radius:999px;padding:14px 20px;font:600 16px/1 "DM Sans",system-ui,sans-serif;cursor:pointer;box-shadow:0 8px 24px rgba(200,16,46,.35)}',
    '.ac-buton:hover{background:#a80d26}.ac-buton:focus-visible{outline:3px solid #201e1d;outline-offset:3px}',
    '.ac-fereastra{position:fixed;right:18px;bottom:84px;z-index:9001;width:min(380px,calc(100vw - 24px));height:min(560px,calc(100vh - 110px));display:flex;flex-direction:column;background:#fff;color:#201e1d;border-radius:4px;box-shadow:0 18px 50px rgba(32,30,29,.28);font:15px/1.5 "DM Sans",system-ui,sans-serif;overflow:hidden}',
    '.ac-fereastra[hidden]{display:none}',
    '.ac-antet{background:#201e1d;color:#fff;padding:14px 16px;border-bottom:4px solid #c8102e;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}',
    '.ac-antet strong{display:block;font-size:19px;font-family:"DM Serif Display",Georgia,serif;font-weight:400}.ac-antet span{display:block;font-size:13px;opacity:.8}',
    '.ac-inchide{background:none;border:0;color:#fff;font-size:24px;line-height:1;cursor:pointer;padding:0 4px}',
    '.ac-mesaje{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#f3f2f2}',
    '.ac-msg{max-width:88%;padding:10px 12px;border-radius:4px;white-space:pre-wrap;overflow-wrap:anywhere;text-wrap:pretty}',
    '.ac-msg.eu{align-self:flex-end;background:#c8102e;color:#fff}.ac-msg.bot{align-self:flex-start;background:#fff;border:1px solid rgba(32,30,29,.12)}',
    '.ac-msg.scrie{color:#605d5d;display:flex;align-items:center;gap:8px}',
    '.ac-puncte{display:inline-flex;gap:4px}.ac-puncte i{width:6px;height:6px;border-radius:50%;background:#605d5d;animation:ac-puls 1.2s infinite ease-in-out both}',
    '.ac-puncte i:nth-child(2){animation-delay:.2s}.ac-puncte i:nth-child(3){animation-delay:.4s}',
    '@keyframes ac-puls{0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1)}}',
    '@media (prefers-reduced-motion:reduce){.ac-puncte i{animation:none;opacity:.6}}',
    '.ac-msg.bot a{color:#8c0b20}.ac-msg.eroare{align-self:center;background:none;color:#8c0b20;font-size:14px;text-align:center}',
    '.ac-form{display:flex;gap:8px;padding:10px;border-top:1px solid rgba(32,30,29,.12)}',
    '.ac-form textarea{flex:1;resize:none;height:44px;font:inherit;padding:10px;border:1px solid rgba(32,30,29,.3);border-radius:2px}',
    '.ac-form textarea:focus-visible{outline:2px solid #c8102e;outline-offset:0}',
    '.ac-form button{background:#c8102e;color:#fff;border:0;border-radius:2px;padding:0 14px;font:600 15px/1 "DM Sans",system-ui,sans-serif;cursor:pointer}',
    '.ac-form button[disabled]{opacity:.6;cursor:default}',
    '.ac-nota{font-size:12px;color:#605d5d;padding:0 12px 10px;text-wrap:pretty}',
    '@media (max-width:520px){.ac-fereastra{right:12px;bottom:76px}.ac-buton{right:12px;bottom:12px}}'
  ].join('');
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  var buton = document.createElement('button');
  buton.className = 'ac-buton'; buton.type = 'button';
  buton.setAttribute('aria-expanded', 'false'); buton.setAttribute('aria-controls', 'ac-fereastra');
  buton.textContent = 'Întrebați asistentul';

  var f = document.createElement('section');
  f.className = 'ac-fereastra'; f.id = 'ac-fereastra'; f.hidden = true;
  f.setAttribute('aria-label', 'Asistentul Ascendent');
  f.innerHTML =
    '<div class="ac-antet"><div><strong>Asistentul Ascendent</strong><span>Răspunde din proprietățile de' + NB + 'pe' + NB + 'site</span></div>' +
    '<button type="button" class="ac-inchide" aria-label="Închide asistentul">×</button></div>' +
    '<div class="ac-mesaje" role="log" aria-live="polite"></div>' +
    '<form class="ac-form"><label class="ac-ascuns" for="ac-text" style="position:absolute;left:-9999px">Întrebarea dumneavoastră</label>' +
    '<textarea id="ac-text" maxlength="500" placeholder="Scrieți întrebarea…"></textarea>' +
    '<button type="submit">Trimiteți</button></form>' +
    '<p class="ac-nota">Răspunsurile sunt generate automat de' + NB + 'un asistent AI, doar din' + NB + 'proprietățile de' + NB + 'pe' + NB + 'site. Conversația se' + NB + 'salvează, ca agenția să vă poată ajuta mai' + NB + 'bine.</p>';
  document.body.appendChild(buton); document.body.appendChild(f);

  var lista = f.querySelector('.ac-mesaje'), form = f.querySelector('form'), text = f.querySelector('textarea'),
      trimite = form.querySelector('button');
  var conv = null;
  try { conv = sessionStorage.getItem('ac-conversatie'); } catch (e) {}

  function adauga(t, cls) {
    var m = document.createElement('div'); m.className = 'ac-msg ' + cls;
    if (cls === 'bot') {
      // linkurile de pe site devin clicabile; restul rămâne text simplu
      t.split(/(https?:\/\/[^\s)]+)/g).forEach(function (bucata, i) {
        if (i % 2) { var a = document.createElement('a'); a.href = bucata; a.textContent = 'vedeți proprietatea'; m.appendChild(a); }
        else m.appendChild(document.createTextNode(bucata));
      });
    } else m.textContent = t;
    lista.appendChild(m); lista.scrollTop = lista.scrollHeight;
  }
  // Balonul „scrie un răspuns”: apare cât timp așteptăm răspunsul, ca omul să știe că cineva lucrează la el.
  function arataScrie() {
    var m = document.createElement('div'); m.className = 'ac-msg bot scrie';
    m.innerHTML = '<span>Asistentul formulează un răspuns</span><span class="ac-puncte" aria-hidden="true"><i></i><i></i><i></i></span>';
    lista.appendChild(m); lista.scrollTop = lista.scrollHeight;
    return m;
  }
  function deschide(da) {
    f.hidden = !da; buton.setAttribute('aria-expanded', String(da));
    if (da) { if (!lista.children.length) adauga('Bună ziua! Vă pot ajuta să găsiți o proprietate pe' + NB + 'site sau să aflați prețul mediu dintr-o zonă. Ce' + NB + 'căutați?', 'bot'); text.focus(); }
  }
  buton.addEventListener('click', function () { deschide(f.hidden); });
  f.querySelector('.ac-inchide').addEventListener('click', function () { deschide(false); buton.focus(); });
  text.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = text.value.trim(); if (!q || trimite.disabled) return;
    adauga(q, 'eu'); text.value = ''; trimite.disabled = true; trimite.textContent = '…';
    var scrie = arataScrie();
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mesaj: q, conversatie: conv, pagina: location.pathname }) })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) {
        scrie.remove();
        if (d && d.ok) { conv = d.conversatie; try { sessionStorage.setItem('ac-conversatie', conv); } catch (e) {} adauga(d.raspuns, 'bot'); }
        else adauga((d && d.eroare) || 'Asistentul nu poate răspunde acum.', 'eroare');
      })
      .catch(function () { scrie.remove(); adauga('Nu am putut trimite întrebarea. Verificați conexiunea la' + NB + 'internet.', 'eroare'); })
      .then(function () { trimite.disabled = false; trimite.textContent = 'Trimiteți'; text.focus(); });
  });
})();
