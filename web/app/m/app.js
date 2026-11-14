/* Apollux · app do celular (m.html). Casca + telas num arquivo só: o celular abre poucas telas, todas
   pequenas, e um arquivo a mais por tela é uma ida à rede a mais num 4G ruim.

   O que é do celular e o que NÃO é:
   - É do celular: a navegação (barra de abas, telas de detalhe com voltar), o painel deslizante (sheet) e
     o ARRASTE para confirmar (DS regra 6). Abrir trade, fechar posição, ligar o Apollo e o pânico pedem o
     knob a 85% do trilho: no bolso, um toque acidental abre posição; um arraste até o fim, não.
   - NÃO é do celular: credencial, conta, poll e login (app/api.js), e o tamanho do trade, a perda no pior
     caso e o "ainda dá pra entrar" (app/comum.js). Os mesmos do desktop, para o mesmo sinal dar o mesmo
     ticket nas duas telas.

   Rotas (hash): #painel #operar #apollo #analise #mais · detalhe #pos/<id> #sinal/<id> #carteira #diario.
   Cada tela monta um esqueleto fixo uma vez e só repinta os blocos que mudam a cada /estado (3 s): um
   innerHTML da tela inteira apagaria o que a pessoa está digitando no ticket e o knob no meio do arraste. */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt, root = document.documentElement;
  var $ = function (id) { return document.getElementById(id); };
  var esc = A.esc;
  function ic(n, cls) { return '<svg class="ic' + (cls ? ' ' + cls : '') + '" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; }
  function cur(v, sinal) { var a = Math.abs(v || 0); return (sinal ? (v > 0 ? '+' : v < 0 ? '−' : '') : (v < 0 ? '−' : '')) + '<span class="cur">R$</span>' + F.f2(a); }
  function chipLado(d, extra) { return '<span class="chip ' + (d === 'LONG' ? 'long' : 'short') + '">' + esc(d) + (extra ? ' ' + esc(extra) : '') + '</span>'; }
  function p1(v) { return F.f1(+v || 0); }
  /* contagem num título: a Syne desenha o zero como a letra "o" ("Sinais · o"), então o número vai em mono */
  function cnt(n) { return '<span class="mono cnt">' + n + '</span>'; }
  /* chave pública VAPID (base64url) → bytes, o formato que o pushManager.subscribe aceita */
  function chaveBytes(b64) {
    var s = atob((b64 + '='.repeat((4 - b64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/')), u = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
  }

  /* ================= paleta e conta ================= */
  var pal0 = A.paletaInicial(); if (pal0) A.pintaPaleta(pal0);
  if (A.CONTA === 'B') document.body.classList.add('conta-b');
  var NOME_CONTA = A.CONTA === 'B' ? 'Conta B' : 'Paper A';

  /* ================= estado compartilhado entre telas ================= */
  var M = { pnlHist: {}, saidas: {}, precos: {}, health: null, tr: null, trSig: '', mes: null };

  /* P&L de cada posição entre polls, para a sparkline (mesma ideia do Painel do desktop) */
  A.on('estado', function (e) {
    var vivos = {};
    (e.posicoes || []).forEach(function (p) { vivos[p.id] = 1; var v = M.pnlHist[p.id] || (M.pnlHist[p.id] = [0]); if (v[v.length - 1] !== p.pnl) v.push(p.pnl || 0); if (v.length > 80) v.splice(1, v.length - 80); });
    Object.keys(M.pnlHist).forEach(function (k) { if (!vivos[k]) delete M.pnlHist[k]; });
  });

  /* /trades?limite=500: o mês FECHADO (o mesmo número do desktop) e o Diário. Só relê quando um trade
     fechou ou o dia virou, como o Painel do desktop: é a resposta mais pesada do app. */
  var LIM = 500;
  function trSig(e) { return ((e.metricas || {}).n_trades || 0) + '|' + (((e.trades || [])[0] || {}).id || '') + '|' + A.hoje(); }
  async function lerTrades() {
    var e = A.estado; if (!e) return;
    var sig = trSig(e); if (sig === M.trSig) return; M.trSig = sig;
    try {
      var tr = await A.api('/trades?limite=' + LIM);
      tr = (tr || []).filter(function (t) { return t.fechado_em; }).sort(function (a, b) { return a.fechado_em < b.fechado_em ? -1 : 1; });
      var mk = A.hoje().slice(0, 7);
      M.tr = tr;
      M.mes = { pnl: tr.reduce(function (a, t) { return t.fechado_em.slice(0, 7) === mk ? a + (t.pnl_reais || 0) : a; }, 0),
        completo: tr.length < LIM || tr[0].fechado_em.slice(0, 7) < mk, desde: tr.length ? A.ddmm(tr[0].fechado_em) : '' };
      if (tela && tela.trades) tela.trades();
      if (tela && tela.update && A.estado) tela.update(A.estado);
    } catch (err) { M.trSig = ''; }
  }
  A.on('estado', lerTrades);

  async function lerSaude() { var h = await A.saude(); M.health = h.ok ? h.j : null; pintaConn(); }
  var saudeT = 0;
  function saudeLoop() { clearInterval(saudeT); if (!document.hidden) { lerSaude(); saudeT = setInterval(lerSaude, 30000); } }
  document.addEventListener('visibilitychange', saudeLoop);

  /* ================= toast e painel deslizante ================= */
  var sheetRes = null, sheetFoco = null;
  /* sheet({titulo, corpo, perigo, slide: {txt, perigo}, botao, cancelar, aoAbrir(box), antes(box)}) → Promise<boolean>.
     Com `slide`, o OK é o arraste até o fim; sem ele, um botão (só para o que não abre nem fecha risco). */
  function sheet(o) {
    if (sheetRes) sheetRes(false);
    sheetFoco = document.activeElement;
    var box = $('sheet'), dim = $('sheet-dim');
    box.className = 'sheet' + (o.perigo ? ' perigo' : '');
    box.innerHTML = '<div class="sheet-grip" aria-hidden="true"></div><h4 id="sheet-h">' + esc(o.titulo) + '</h4>' + (o.corpo || '') +
      (o.slide ? slideHtml(o.slide.txt, o.slide.perigo, 'sh-slide') : o.botao ? '<button type="button" class="btn primary block" id="sh-ok">' + esc(o.botao) + '</button>' : '') +
      '<button type="button" class="btn ghost block" id="sh-cancel">' + esc(o.cancelar || 'Cancelar') + '</button>';
    box.hidden = false; dim.hidden = false; document.body.style.overflow = 'hidden';
    if (window.gsap && !A.RM) gsap.fromTo(box, { yPercent: 100 }, { yPercent: 0, duration: .28, ease: 'power3.out', clearProps: 'transform' });
    return new Promise(function (res) {
      sheetRes = function (v) {
        sheetRes = null; box.hidden = true; dim.hidden = true; box.innerHTML = ''; document.body.style.overflow = '';
        if (sheetFoco && sheetFoco.focus && document.body.contains(sheetFoco)) sheetFoco.focus();
        res(v);
      };
      $('sh-cancel').addEventListener('click', function () { sheetRes(false); });
      if ($('sh-ok')) $('sh-ok').addEventListener('click', function () { if (o.antes && o.antes(box) === false) return; sheetRes(true); });
      if (o.slide) armaSlide($('sh-slide'), function () { if (o.antes && o.antes(box) === false) return false; sheetRes(true); return true; });
      arrastaParaFechar(box);
      if (o.aoAbrir) o.aoAbrir(box);
      setTimeout(function () { var f = box.querySelector('.knob, #sh-ok, #sh-cancel'); if (f) f.focus({ preventScroll: true }); }, 60);
    });
  }
  $('sheet-dim').addEventListener('click', function () { if (sheetRes) sheetRes(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && sheetRes) sheetRes(false); });
  /* puxar o painel para baixo pela alça fecha (DS: "sheet arrasta para fechar"); o botão Cancelar é o equivalente visível */
  function arrastaParaFechar(box) {
    var g = box.querySelector('.sheet-grip'), y0 = null, dy = 0;
    g.addEventListener('pointerdown', function (e) { y0 = e.clientY; dy = 0; g.setPointerCapture(e.pointerId); box.style.transition = 'none'; });
    g.addEventListener('pointermove', function (e) { if (y0 == null) return; dy = Math.max(0, e.clientY - y0); box.style.transform = 'translateY(' + dy + 'px)'; });
    var fim = function () { if (y0 == null) return; y0 = null; box.style.transition = ''; box.style.transform = ''; if (dy > 90 && sheetRes) sheetRes(false); };
    g.addEventListener('pointerup', fim); g.addEventListener('pointercancel', fim);
  }

  /* ================= arraste para confirmar ================= */
  function slideHtml(txt, perigo, id) {
    return '<div class="slide' + (perigo ? ' danger' : '') + '"' + (id ? ' id="' + id + '"' : '') + '><div class="fill"></div><div class="track">' + esc(txt) + ' →</div>' +
      '<button type="button" class="knob" aria-label="' + esc(txt) + ': arraste até o fim, ou use a seta para a direita">' + ic(perigo ? 'panico' : 'seta-d') + '</button></div>';
  }
  /* onDone() devolve true (feito), false (recusado: volta) ou uma Promise disso. O knob precisa passar de
     85% do trilho; soltar antes volta ao começo. Teclado: seta direita anda 1/8 do trilho, e só confirma
     ao passar dos 85%, então nenhuma tecla isolada executa. */
  function armaSlide(el, onDone) {
    if (!el) return;
    var k = el.querySelector('.knob'), fill = el.querySelector('.fill'), x = 0, x0 = 0, px0 = 0, arr = false, feito = false;
    function max() { return Math.max(1, el.clientWidth - k.offsetWidth - 8); }
    function pos(v, anim) {
      x = Math.max(0, Math.min(max(), v));
      k.style.transition = fill.style.transition = anim ? 'transform .25s ease-out, width .25s ease-out' : 'none';
      k.style.transform = 'translateX(' + x + 'px)'; fill.style.width = (x + k.offsetWidth / 2 + 4) + 'px';
      if (!x) fill.style.width = '0';
    }
    async function tenta() {
      if (x < max() * 0.85) { pos(0, true); return; }
      feito = true; pos(max(), true); el.classList.add('is-busy');
      var ok = false; try { ok = await onDone(); } catch (e) { ok = false; }
      el.classList.remove('is-busy');
      if (ok) el.classList.add('is-done'); else { feito = false; pos(0, true); }
    }
    k.addEventListener('pointerdown', function (e) { if (feito || el.classList.contains('is-off')) return; arr = true; x0 = x; px0 = e.clientX; k.setPointerCapture(e.pointerId); });
    k.addEventListener('pointermove', function (e) { if (arr) pos(x0 + e.clientX - px0, false); });
    k.addEventListener('pointerup', function () { if (!arr) return; arr = false; tenta(); });
    k.addEventListener('pointercancel', function () { arr = false; pos(0, true); });
    k.addEventListener('keydown', function (e) {
      if (feito || el.classList.contains('is-off')) return;
      if (e.key === 'ArrowRight') { e.preventDefault(); pos(x + max() / 8, true); if (x >= max() * 0.85) tenta(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); pos(x - max() / 8, true); }
    });
    el._reset = function () { feito = false; el.classList.remove('is-done'); pos(0, true); };
  }

  /* ================= ações (as mesmas rotas e respostas do desktop) ================= */
  async function panico() {
    var e = A.estado || {}, n = (e.posicoes || []).length, no = (e.ordens || []).length;
    var on = String((e.config || {}).auto_trade) === '1';
    var corpo = '<p class="note">O backend grava <b>auto_trade = 0 primeiro</b> e só depois fecha ' +
      (n ? '<b>' + n + (n === 1 ? ' posição' : ' posições') + '</b> a mercado.' : 'as posições abertas (agora: nenhuma).') + '</p>' +
      '<div class="diff"><div><span>Apollo (auto-trade)</span><span>' + (on ? 'ligado → <b class="neg">desligado</b>' : 'já desligado') + '</span></div>' +
      '<div><span>Posições abertas</span><span>' + n + ' → <b>0</b></span></div></div>' +
      (no ? '<div class="aviso">' + no + (no === 1 ? ' ordem post-only descansando NÃO é cancelada' : ' ordens post-only descansando NÃO são canceladas') + ' pelo pânico e ainda pode virar posição se o preço vier até ela.</div>' : '') +
      '<p class="note">Religar o Apollo depois exige ação explícita na aba Apollo.</p>';
    if (!(await sheet({ titulo: 'Pânico · ' + NOME_CONTA, corpo: corpo, perigo: true, slide: { txt: 'Arraste para o pânico', perigo: true } }))) return;
    await executaPanico();
  }
  /* o POST em si; quem chama já teve o arraste (sheet do topo, ou o cartão da aba Apollo) */
  async function executaPanico() {
    try {
      var r = await A.api('/panico', {});
      A.toast('Pânico: ' + r.fechadas + (r.fechadas === 1 ? ' posição fechada' : ' posições fechadas') + ' · P&L ' + F.money(r.pnl) + ' · auto desligado', 'neg');
      A.carregar(); return true;
    } catch (err) { A.toast('Pânico falhou: ' + A.erroTxt(err), 'neg'); return false; }
  }
  async function fechar(p) {
    var corpo = '<p class="note">Fecha a posição <b>' + esc(p.direcao) + ' ' + esc(p.alavancagem) + 'x</b> a mercado. A saída paga taxa taker.</p>' +
      '<div class="diff"><div><span>P&amp;L agora</span><b class="' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '</b></div><div><span>Margem</span><span>' + F.brl(p.valor_reais) + '</span></div></div>' +
      '<p class="note">O P&amp;L final é o do preço na hora da execução, não o deste retrato.</p>';
    if (!(await sheet({ titulo: 'Fechar ' + F.par(p.ativo), corpo: corpo, perigo: true, slide: { txt: 'Arraste para fechar', perigo: true } }))) return false;
    try {
      var r = await A.api('/fechar', { id: p.id });
      if (r.ok === false) { A.toast(r.erro, 'neg'); return false; }
      A.toast(r.pnl == null ? 'Posição já estava fechada' : 'Posição fechada · P&L ' + F.money(r.pnl)); A.carregar(); return true;
    } catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); return false; }
  }
  async function pular(s) {
    try { await A.api('/pular', { id: s.id }); A.toast('Sinal ' + F.par(s.ativo) + ' pulado'); A.carregar(); return true; }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); return false; }
  }
  async function alternaAuto() {
    var e = A.estado; if (!e) return; var cfg = e.config || {}, on = String(cfg.auto_trade) === '1';
    if (!on) {
      var corpo = '<p class="note">Ele passa a abrir e fechar posições sozinho na <b>' + NOME_CONTA + '</b>, com a config de agora:</p><div class="diff">' +
        '<div><span>risco por trade</span><b>' + F.f2((parseFloat(cfg.risco_por_trade) || 0) * 100) + '%</b></div><div><span>convicção mínima</span><b>' + esc(cfg.auto_conviccao_min) + '</b></div>' +
        '<div><span>máx. posições</span><b>' + esc(cfg.auto_max_posicoes) + '</b></div><div><span>alavancagem</span><b>' + esc(levTxt(cfg)) + '</b></div><div><span>execução</span><b>' + (cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado') + '</b></div></div>' +
        '<p class="note">Trava diária e teto de risco aberto continuam valendo. A config se muda na versão completa, antes de ligar.</p>';
      if (!(await sheet({ titulo: 'Ligar o Apollo', corpo: corpo, slide: { txt: 'Arraste para ligar' } }))) { if (tela && tela.update) tela.update(A.estado); return; }
    }
    /* pausar não pede arraste: apertar a guarda pode sempre (CLAUDE.md §2); as posições seguem com stop */
    try { await A.api('/auto', { auto_trade: on ? '0' : '1' }); A.toast(on ? 'Apollo pausado: posições abertas seguem com stop' : 'Apollo ligado'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); if (tela && tela.update) tela.update(A.estado); }
  }
  function levTxt(cfg) { return cfg.auto_lev_modo === 'fixo' ? cfg.alavancagem_padrao + 'x fixa' : cfg.auto_lev_modo === 'risco' ? 'pela conta (' + cfg.auto_lev_min + '–' + cfg.auto_lev_max + 'x)' : 'por convicção (' + cfg.auto_lev_min + '–' + cfg.auto_lev_max + 'x)'; }
  async function trocaContaSheet() {
    var corpo = '<p class="note">Cada conta é uma banca separada no backend. A credencial é a mesma.</p>' +
      '<div class="seg" role="group" aria-label="Conta"><button type="button" data-c="A" aria-pressed="' + (A.CONTA === 'A') + '">Paper A</button><button type="button" data-c="B" aria-pressed="' + (A.CONTA === 'B') + '">Conta B · teste A/B</button></div>';
    sheet({ titulo: 'Conta', corpo: corpo, cancelar: 'Fechar', aoAbrir: function (box) {
      box.querySelectorAll('[data-c]').forEach(function (b) { b.addEventListener('click', function () { A.trocaConta(b.dataset.c); }); });
    } });
  }

  /* ================= cabeçalho e conexão ================= */
  function mh(titulo, o) {
    o = o || {};
    return '<div class="mh">' + (o.voltar ? '<a class="back" href="' + o.voltar + '" aria-label="Voltar">' + ic('voltar') + '</a>' : '') +
      '<h4' + (o.voltar ? ' class="det"' : '') + '>' + titulo + '</h4>' + (o.extra || '') +
      (o.semConta ? '' : '<button type="button" class="acct" data-acao="conta" aria-label="Conta: ' + NOME_CONTA + '. Trocar"><span class="avatar">' + A.CONTA + '</span>' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</button>') +
      '<button type="button" class="ib danger" data-acao="panico" aria-label="Pânico">' + ic('panico') + '</button></div>' +
      '<div class="conn" id="m-conn"><span class="led off"></span><span>conectando…</span></div>' +
      '<div class="offline-bar" role="status">' + ic('alerta') + '<span id="m-off-txt">backend offline · reconectando. Os números abaixo são do último retrato.</span></div>';
  }
  function pintaConn() {
    var el = $('m-conn'); if (!el) return;
    var led = el.querySelector('.led'), t = el.querySelector('span:last-child'), e = A.estado, on = e && String((e.config || {}).auto_trade) === '1';
    if (A.online === false) { led.className = 'led bad'; t.textContent = 'backend offline'; return; }
    if (!e) return;
    var h = M.health, vivo = h ? h.status === 'ok' : true;
    led.className = 'led' + (vivo ? '' : ' bad');
    t.textContent = (vivo ? 'ao vivo' : 'ciclo parado') + (h && h.ciclo_ha_s != null ? ' · ciclo há ' + Math.round(h.ciclo_ha_s) + ' s' : '') + ' · Apollo ' + (on ? 'ligado' : 'desligado');
  }
  A.on('estado', pintaConn); A.on('online', pintaConn);
  A.on('offline', function (m) { var t = $('m-off-txt'); if (t) t.textContent = 'backend offline (' + m + ') · reconectando a cada 3 s. Os números abaixo são do último retrato.'; pintaConn(); });

  /* ================= blocos reutilizados ================= */
  function posItem(p) {
    var roe = p.valor_reais ? p.pnl / p.valor_reais * 100 : 0, sd = M.saidas[p.id];
    var mov = p.stop_abertura != null && Math.abs(p.stop - p.stop_abertura) > 1e-12;
    return '<a class="m-pos" href="#pos/' + p.id + '"><div><div class="top"><b>' + esc(F.par(p.ativo)) + '</b>' + chipLado(p.direcao, p.alavancagem + 'x') + '</div>' +
      '<div class="meta">' + F.px(p.preco_atual) + ' · stop ' + F.px(p.stop) + (mov ? ' (trailing)' : '') + ' · ' + A.idade(p.aberto_em) + '</div>' + A.spark(M.pnlHist[p.id]) + '</div>' +
      '<div class="pnl ' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '<small>' + F.pct(roe, 1) + ' ROE</small></div>' +
      (sd && sd.nivel === 'risco' ? '<div class="aviso-s">' + esc(F.decBR(sd.acao)) + '</div>' : '') + '</a>';
  }
  function sigItem(s, e) {
    var c = Math.round(s.conviccao || 0), ttl = parseFloat(((e || {}).config || {}).auto_freshness_min) || 12;
    return '<div class="sig"><div class="sig-top"><b>' + esc(F.par(s.ativo)) + '</b>' + chipLado(s.direcao) + '<span class="chip">' + esc(s.tf || '') + '</span>' +
      '<span class="sig-exp" title="o auto-trade só opera sinal com até ' + ttl + ' min">há ' + A.idade(s.ts) + '</span></div>' +
      '<div class="sig-conv"><span>convicção</span><span class="n">' + c + '</span><span class="bar"><i style="--w:' + c + '%"></i></span></div>' +
      '<div class="sig-why">' + esc(F.decBR((s.motivos || '').split(', ').slice(0, 3).join(' · ') || s.tipo || '')) + '</div>' +
      '<div class="sig-act"><a class="btn primary sm" href="#sinal/' + s.id + '">Ver e confirmar</a><button type="button" class="btn secondary sm" data-pular="' + s.id + '">Pular</button></div></div>';
  }
  function ordItem(o) {
    var falta = A.ts(o.expira_em) ? Math.max(0, Math.round((A.ts(o.expira_em) - Date.now()) / 60000)) : null;
    var c = A.ts(o.criada_em), x = A.ts(o.expira_em), tot = c && x ? x - c : 0, pas = c ? Date.now() - c : 0;
    return '<div class="ord"><div class="top"><b>' + esc(F.par(o.ativo)) + '</b>' + chipLado(o.direcao, o.alavancagem + 'x') + '<span class="px">' + F.px(o.preco_limite) + '</span></div>' +
      '<div class="meta">descansa há ' + A.idade(o.criada_em) + (falta != null ? ' · expira em ' + falta + ' min' : '') + ' · ' + F.brl(o.valor_reais) + '</div>' +
      '<div class="bar warn"><i style="--w:' + (tot ? Math.min(100, pas / tot * 100) : 0).toFixed(1) + '%"></i></div></div>';
  }
  function travaHtml(e) {
    var rg = e.risco || {}, perda = Math.max(0, -(rg.pnl_dia || 0)), pct = rg.limite_rs ? Math.min(100, perda / rg.limite_rs * 100) : 0;
    var st = rg.trava_dia ? '<span class="state-pill locked">disparada</span>' : pct >= 60 ? '<span class="state-pill near">perto</span>' : '<span class="state-pill free">livre</span>';
    return '<div class="risk"><div class="risk-head"><span class="k">Trava diária <span class="mono mute" style="font-size:11px">−' + p1(rg.limite_pct) + '%</span></span><span class="v">' + F.brl(perda) + ' de ' + F.brl(rg.limite_rs) + '</span>' + st + '</div>' +
      '<div class="bar neg" aria-hidden="true"><i style="--w:' + pct.toFixed(1) + '%"></i></div></div>';
  }
  function riscoAbertoHtml(e) {
    var rg = e.risco || {}, pct = rg.risco_aberto_max_rs ? Math.min(100, (rg.risco_aberto_rs || 0) / rg.risco_aberto_max_rs * 100) : 0;
    return '<div class="risk"><div class="risk-head"><span class="k">Risco aberto <span class="mono mute" style="font-size:11px">teto ' + p1(rg.risco_aberto_pct) + '%</span></span><span class="v">' + F.brl(rg.risco_aberto_rs) + ' de ' + F.brl(rg.risco_aberto_max_rs) + '</span>' +
      (rg.teto_aberto ? '<span class="state-pill locked">no teto</span>' : '') + '</div><div class="bar warn" aria-hidden="true"><i style="--w:' + pct.toFixed(1) + '%"></i></div></div>';
  }
  function guardasHtml(e) {
    var cfg = e.config || {}, rg = e.risco || {}, tr = String(cfg.trailing_ativo) === '1';
    return '<div class="guards"><span class="guard' + (rg.teto_aberto ? ' hot' : '') + '">teto de risco aberto ' + p1(rg.risco_aberto_pct) + '%</span>' +
      '<span class="guard' + (rg.trava_dia ? ' hot' : '') + '">trava diária ' + p1(rg.limite_pct) + '%</span>' +
      '<span class="guard">margem máx. ' + p1((parseFloat(cfg.exposicao_max) || 0) * 100) + '%</span>' +
      '<span class="guard' + (tr ? '' : ' off') + '">trailing ' + (tr ? (cfg.trailing_unidade === 'R' ? cfg.trailing_arma_r + 'R/' + cfg.trailing_dist_r + 'R' : '%') : 'desligado') + '</span>' +
      '<span class="guard' + (String(cfg.tp_ativo) === '1' ? '' : ' off') + '">TP por estrutura ' + (String(cfg.tp_ativo) === '1' ? 'ligado' : 'desligado') + '</span></div>';
  }
  function ultimaAcao(e) {
    var a = e.auto || {};
    if (a.ts) return A.hhmm(a.ts) + ' · ' + ((a.abertos || []).length ? a.abertos.length + ' aberto(s)' : (a.fechados || []).length ? a.fechados.length + ' fechado(s)' : (a.motivo || 'nada a fazer'));
    return a.motivo || '—';
  }

  /* ---- curva de capital: x por TEMPO (como o desktop desde a PR #28), toque mostra o ponto ---- */
  function curva(el, hist) {
    var h = (hist || []).map(function (p) { return { t: +A.ts(p.ts), v: p.equity_total }; }).filter(function (p) { return p.t && isFinite(p.v); });
    if (h.length < 2) { el.innerHTML = '<div class="empty">A curva aparece depois de alguns ciclos.</div>'; return; }
    var W = Math.max(200, el.clientWidth || 340), H = el.clientHeight || 150, pl = 4, pr = 4, pt = 10, pb = 18;
    var t0 = h[0].t, t1 = h[h.length - 1].t, dur = (t1 - t0) || 1;
    var lo = Math.min.apply(null, h.map(function (p) { return p.v; })), hi = Math.max.apply(null, h.map(function (p) { return p.v; })), sp = (hi - lo) || 1;
    var X = function (t) { return pl + (t - t0) / dur * (W - pl - pr); }, Y = function (v) { return pt + (1 - (v - lo) / sp) * (H - pt - pb); };
    var d = h.map(function (p, i) { return (i ? 'L' : 'M') + X(p.t).toFixed(1) + ' ' + Y(p.v).toFixed(1); }).join(' ');
    var ar = d + ' L' + X(t1).toFixed(1) + ' ' + (H - pb) + ' L' + X(t0).toFixed(1) + ' ' + (H - pb) + ' Z';
    var curto = dur < 2 * 86400000, lbl = function (t) { var s = new Date(t).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).replace(',', ''); return curto ? s.slice(6) : s.slice(0, 5); };
    var ticks = '', n = 3;
    for (var i = 0; i < n; i++) { var tt = t0 + dur * i / (n - 1); ticks += '<text class="ax" x="' + X(tt).toFixed(1) + '" y="' + (H - 3) + '" text-anchor="' + (i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle') + '">' + lbl(tt) + '</text>'; }
    el.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="Curva de equity de ' + lbl(t0) + ' a ' + lbl(t1) + ', mínimo ' + F.brl(lo) + ', máximo ' + F.brl(hi) + '">' +
      '<line class="g" x1="0" x2="' + W + '" y1="' + Y(hi).toFixed(1) + '" y2="' + Y(hi).toFixed(1) + '"/><line class="g" x1="0" x2="' + W + '" y1="' + Y(lo).toFixed(1) + '" y2="' + Y(lo).toFixed(1) + '"/>' +
      '<path class="ar" d="' + ar + '"/><path class="ln" d="' + d + '"/>' + ticks +
      '<text class="ax" x="' + (W - 2) + '" y="' + (Y(hi) - 3).toFixed(1) + '" text-anchor="end">' + F.f2(hi) + '</text><text class="ax" x="' + (W - 2) + '" y="' + (Y(lo) - 4).toFixed(1) + '" text-anchor="end">' + F.f2(lo) + '</text>' +
      '<g id="cv-m" visibility="hidden"><line class="cross" id="cv-x" y1="' + pt + '" y2="' + (H - pb) + '"/><circle class="dot" id="cv-d" r="3.5"/></g></svg><div class="tip" id="cv-tip" hidden></div>';
    var svg = el.querySelector('svg'), tip = el.querySelector('#cv-tip'), cx = el.querySelector('#cv-x'), dt = el.querySelector('#cv-d'), mk = el.querySelector('#cv-m');
    function mostra(ev) {
      var r = svg.getBoundingClientRect(), xx = (ev.clientX - r.left) / r.width * W, t = t0 + (xx - pl) / (W - pl - pr) * dur, b = 0;
      for (var j = 1; j < h.length; j++) if (Math.abs(h[j].t - t) < Math.abs(h[b].t - t)) b = j;
      var px = X(h[b].t), py = Y(h[b].v);
      mk.setAttribute('visibility', 'visible'); cx.setAttribute('x1', px); cx.setAttribute('x2', px); dt.setAttribute('cx', px); dt.setAttribute('cy', py);
      tip.hidden = false; tip.innerHTML = F.brl(h[b].v) + ' · ' + lbl(h[b].t); tip.style.left = Math.max(60, Math.min(r.width - 60, px / W * r.width)) + 'px';
    }
    svg.addEventListener('pointerdown', mostra); svg.addEventListener('pointermove', function (ev) { if (ev.pointerType === 'mouse' || ev.buttons) mostra(ev); });
    svg.addEventListener('pointerleave', function () { tip.hidden = true; mk.setAttribute('visibility', 'hidden'); });
  }

  /* ================= telas ================= */
  var TELAS = {};

  /* ---------- Painel: a mesma hierarquia do desktop, empilhada (DS §5): risco e P&L na primeira dobra ---------- */
  TELAS.painel = {
    tab: 'painel', titulo: 'Painel',
    html: function () {
      return mh('Painel') +
        '<section class="m-hero" aria-label="Equity e resultado do dia"><span class="kpi-lbl" id="p-eq-l">Equity</span><div class="eq" id="p-eq">—</div>' +
        '<div class="row" id="p-chips"></div><div class="dec" id="p-dec"></div><div id="p-trava" style="margin-top:12px"></div></section>' +
        '<section class="m-kpis" id="p-kpis" aria-label="Indicadores"></section>' +
        '<section class="m-card" aria-label="Curva de capital"><div class="m-sec" style="padding:0"><h5>Curva de capital</h5><span class="n" id="p-cv-sub"></span></div><div class="curve" id="p-curva"></div></section>' +
        '<div class="m-sec"><h5 id="p-pos-h">Posições</h5><a href="#operar">Operar</a></div><div id="p-pos" style="display:grid;gap:8px"></div>' +
        '<div class="m-sec"><h5 id="p-sig-h">Sinais</h5><a href="#operar">ver fila</a></div><div id="p-sig" style="display:grid;gap:8px"></div>' +
        '<div id="p-ord-w" hidden><div class="m-sec"><h5 id="p-ord-h">Ordens descansando</h5></div><div id="p-ord" style="display:grid;gap:8px;margin-top:8px"></div></div>' +
        '<div class="m-sec"><h5>Últimos trades</h5><a href="#diario">diário</a></div><section class="m-card" style="padding:4px 14px"><ul class="jr" id="p-jr"></ul></section>';
    },
    init: function () { this.sigCv = ''; this.timers = [setInterval(lerSaidas, 8000)]; lerSaidas(); },
    destroy: function () { (this.timers || []).forEach(clearInterval); },
    update: function (e) {
      var rg = e.risco || {}, m = e.metricas || {}, cfg = e.config || {}, eq = e.equity_total, pd = rg.pnl_dia || 0, base = eq - pd;
      $('p-eq-l').textContent = 'Equity · início do dia ' + F.brl(base);
      A.contar($('p-eq'), eq, function (v) { return cur(v); });
      /* P&L do dia = equity agora − 1º retrato do dia (a base da trava). Decomposto como no desktop:
         pnl_dia = fechado hoje + (aberto agora − aberto às 00h). */
      var real = rg.realizado_hoje || 0, dAb = Math.round((pd - real) * 100) / 100;
      var mes = M.mes, mesTxt = mes ? F.money(mes.pnl) + ' · ' + F.pct(((e.banca || {}).atual || 0) - mes.pnl > 0 ? mes.pnl / (((e.banca || {}).atual || 0) - mes.pnl) * 100 : 0) + ' no mês' : 'mês …';
      $('p-chips').innerHTML = '<span class="chip lg ' + (pd > 0 ? 'long' : pd < 0 ? 'short' : '') + '">' + F.money(pd) + (base > 0 ? ' · ' + F.pct(pd / base * 100) : '') + ' hoje</span>' +
        '<span class="chip lg' + (mes ? (mes.pnl > 0 ? ' long' : mes.pnl < 0 ? ' short' : '') : '') + '" title="P&L FECHADO no mês' + (mes && !mes.completo ? ', desde ' + mes.desde + ' (500 trades)' : '') + '">' + mesTxt + '</span>';
      var unreal = eq - ((e.banca || {}).atual || 0);
      $('p-dec').innerHTML = 'hoje: fechado <b class="' + F.cls(real) + '">' + F.money(real) + '</b> · aberto <b class="' + F.cls(dAb) + '">' + F.money(dAb) + '</b> desde 00h<br>em aberto agora <b class="' + F.cls(unreal) + '">' + F.money(unreal) + '</b> · mês = só o fechado';
      $('p-trava').innerHTML = travaHtml(e);
      var h = e.equity_hist || [], pico = h.reduce(function (a, x) { return Math.max(a, x.equity_total); }, eq), ddA = pico ? (eq / pico - 1) * 100 : 0;
      var on = String(cfg.auto_trade) === '1', payoff = m.perda_media ? Math.abs(m.ganho_medio / m.perda_media) : 0;
      $('p-kpis').innerHTML =
        '<div class="m-kpi"><div class="kpi-lbl">Drawdown</div><div class="kpi-val ' + (ddA < 0 ? 'neg' : '') + '">' + F.pct(ddA, 1) + '</div><div class="kpi-sub">máx. ' + F.pct(-(m.max_dd_mtm_pct || 0), 1) + '</div></div>' +
        '<div class="m-kpi"><div class="kpi-lbl">Win rate</div><div class="kpi-val">' + (m.n_trades ? F.f0(m.win_rate) + '%' : '—') + '</div><div class="kpi-sub">' + (m.n_trades ? 'payoff ' + F.f2(payoff) : 'sem trade') + '</div></div>' +
        '<a class="m-kpi" href="#apollo"><div class="kpi-lbl">Apollo</div><div class="kpi-val ' + (on ? 'acc-t' : 'mute') + '" style="display:flex;align-items:center;gap:6px;font-size:14px;margin-top:8px"><span class="led' + (on ? '' : ' off') + '"></span>' + (on ? 'ligado' : 'desligado') + '</div><div class="kpi-sub">' + (cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado') + '</div></a>';
      var sc = h.length + '|' + (h.length ? h[h.length - 1].ts : '') + '|' + $('p-curva').clientWidth;
      if (sc !== this.sigCv) { this.sigCv = sc; curva($('p-curva'), h); $('p-cv-sub').textContent = h.length ? A.ddmm(h[0].ts) + ' → ' + A.ddmm(h[h.length - 1].ts) : ''; }
      var pos = e.posicoes || [], tot = pos.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
      $('p-pos-h').innerHTML = 'Posições · ' + cnt(pos.length) + (pos.length ? ' <span class="mono ' + F.cls(tot) + '" style="font-size:13px;font-weight:500">' + F.money(tot) + '</span>' : '');
      $('p-pos').innerHTML = pos.length ? pos.map(posItem).join('') : '<div class="empty">Nenhuma posição aberta.</div>';
      var sg = e.pendentes || [];
      $('p-sig-h').innerHTML = 'Sinais · ' + cnt(sg.length);
      $('p-sig').innerHTML = sg.length ? sg.slice(0, 2).map(function (s) { return sigItem(s, e); }).join('') + (sg.length > 2 ? '<a class="btn ghost block" href="#operar">mais ' + (sg.length - 2) + ' na fila</a>' : '') : '<div class="empty">Nenhum sinal na fila. O motor está varrendo.</div>';
      var od = e.ordens || []; $('p-ord-w').hidden = !od.length; $('p-ord-h').innerHTML = 'Ordens descansando · ' + cnt(od.length); $('p-ord').innerHTML = od.map(ordItem).join('');
      $('p-jr').innerHTML = jrItens((e.trades || []).slice(0, 4));
    }
  };
  async function lerSaidas() {
    if (!A.estado || !(A.estado.posicoes || []).length) return;
    try { var l = await A.api('/saidas'); M.saidas = {}; (l || []).forEach(function (s) { M.saidas[s.posicao_id] = s; }); if (tela && tela.update && A.estado) tela.update(A.estado); } catch (e) {}
  }
  function jrItens(l) {
    if (!l.length) return '<li><span class="mute" style="grid-column:1/-1">Nenhum trade fechado ainda.</span></li>';
    return l.map(function (t) {
      return '<li><time>' + A.ddmm(t.fechado_em) + '<br>' + A.hhmm(t.fechado_em) + '</time><div class="q"><b>' + esc(F.par(t.ativo)) + '</b>' + chipLado(t.direcao) + '<small>' + esc(t.motivo_saida || '') + '</small></div>' +
        '<div class="p ' + F.cls(t.pnl_reais) + '">' + F.money(t.pnl_reais) + '</div></li>';
    }).join('');
  }

  /* ---------- Operar: tudo que está em jogo agora ---------- */
  TELAS.operar = {
    tab: 'operar', titulo: 'Operar',
    html: function () {
      return mh('Operar') +
        '<div class="m-sec"><h5 id="o-pos-h">Posições</h5></div><div id="o-pos" style="display:grid;gap:8px"></div>' +
        '<div class="m-sec"><h5 id="o-sig-h">Sinais na fila</h5></div><div id="o-sig" style="display:grid;gap:8px"></div>' +
        '<div class="m-sec"><h5 id="o-ord-h">Ordens descansando</h5></div><div id="o-ord" style="display:grid;gap:8px"></div>' +
        '<p class="note">Toque numa posição para ver stop, risco e fechar. O ticket do sinal mostra a perda no pior caso antes de abrir.</p>';
    },
    init: function () { this.timers = [setInterval(lerSaidas, 8000)]; lerSaidas(); },
    destroy: function () { (this.timers || []).forEach(clearInterval); },
    update: function (e) {
      var pos = e.posicoes || [], tot = pos.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
      $('o-pos-h').innerHTML = 'Posições · ' + cnt(pos.length) + (pos.length ? ' <span class="mono ' + F.cls(tot) + '" style="font-size:13px;font-weight:500">' + F.money(tot) + '</span>' : '');
      $('o-pos').innerHTML = pos.length ? pos.map(posItem).join('') : '<div class="empty">Nenhuma posição aberta.</div>';
      var sg = e.pendentes || []; $('o-sig-h').innerHTML = 'Sinais na fila · ' + cnt(sg.length);
      $('o-sig').innerHTML = sg.length ? sg.map(function (s) { return sigItem(s, e); }).join('') : '<div class="empty">Nenhum sinal na fila.</div>';
      var od = e.ordens || []; $('o-ord-h').innerHTML = 'Ordens descansando · ' + cnt(od.length);
      $('o-ord').innerHTML = od.length ? od.map(ordItem).join('') + '<p class="note">Ordem que expira não devolve o sinal · maker só na entrada · já conta nos tetos.</p>' : '<div class="empty">Nenhuma ordem descansando.' + ((e.config || {}).exec_modo === 'post_only' ? '' : ' Execução atual: a mercado.') + '</div>';
    }
  };

  /* ---------- Posição ---------- */
  TELAS.pos = {
    tab: 'operar', titulo: 'Posição',
    html: function (id) {
      this.id = +id;
      /* o lado mora no hero, não no cabeçalho: a 360 px chip + pânico deixam ~135 px e o par vira "BTCUS…" */
      return mh('<span id="ps-t">Posição</span>', { voltar: '#operar', semConta: true }) +
        '<div id="ps-corpo"><div class="m-card"><div class="skel" style="width:40%"></div><div class="skel"></div></div></div>' +
        '<button type="button" class="btn danger block" id="ps-fechar" hidden>' + ic('fechar') + 'Fechar a mercado</button>';
    },
    init: function () {
      var self = this;
      $('ps-fechar').addEventListener('click', async function () { var p = self.p; if (!p) return; if (await fechar(p)) location.hash = '#operar'; });
      this.timers = [setInterval(lerSaidas, 8000)]; lerSaidas();
    },
    destroy: function () { (this.timers || []).forEach(clearInterval); },
    update: function (e) {
      var p = (e.posicoes || []).filter(function (x) { return x.id === this.id; }, this)[0];
      this.p = p; $('ps-fechar').hidden = !p;
      if (!p) { $('ps-corpo').innerHTML = '<div class="empty">Esta posição não está mais aberta. O resultado dela está no <a class="acc-t" href="#diario">diário</a>.</div>'; return; }
      var cfg = e.config || {}, roe = p.valor_reais ? p.pnl / p.valor_reais * 100 : 0, sd = M.saidas[p.id];
      var mov = p.stop_abertura != null && Math.abs(p.stop - p.stop_abertura) > 1e-12;
      var dStop = p.preco_atual ? (p.stop - p.preco_atual) / p.preco_atual * 100 : 0, rAgora = p.risco_abertura ? p.pnl / p.risco_abertura : null;
      var taxaE = p.taxa_entrada != null ? (Math.abs(p.taxa_entrada - (parseFloat(cfg.taxa_maker) || -1)) < 1e-12 ? 'maker ' : 'taker ') + F.fix(p.taxa_entrada * 100, 3) + '%' : 'taker ' + F.fix((parseFloat(cfg.taxa_por_lado) || 0) * 100, 3) + '% (a mercado)';
      $('ps-t').textContent = F.par(p.ativo);
      var tps = null; try { tps = p.tps ? JSON.parse(p.tps) : null; } catch (x) { tps = null; }
      /* a classe vai DENTRO da que o A.spark já escreve: atributo duplicado o navegador descarta, e sem "spark" o path perde cor e vira um polígono preto */
      var spark = A.spark(M.pnlHist[p.id]).replace('<svg class="spark ', '<svg preserveAspectRatio="none" class="spark spark-g ').replace(/<circle[^>]*\/>/, '');
      $('ps-corpo').innerHTML =
        '<section class="m-hero" style="gap:2px"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">' + chipLado(p.direcao, p.alavancagem + 'x') + '<span class="kpi-lbl">P&amp;L aberto · marcado no último ciclo</span></div><div class="eq ' + F.cls(p.pnl) + '" style="font-size:34px">' + F.money(p.pnl) + '</div>' +
        '<span class="mono txt2" style="font-size:12px">' + F.pct(roe, 1) + ' ROE' + (rAgora != null ? ' · ' + F.r(rAgora) : '') + ' · há ' + A.idade(p.aberto_em) + '</span>' + spark + '</section>' +
        (sd ? '<div class="aviso' + (sd.nivel === 'risco' ? '' : ' info') + '" style="' + (sd.nivel === 'risco' ? '' : 'color:var(--txt2);border-color:var(--line2);background:transparent') + '">' + esc(F.decBR(sd.acao)) + '</div>' : '') +
        '<section class="m-card" style="gap:0;padding:4px 14px">' +
        row('Entrada', F.px(p.entrada)) + row('Atual', F.px(p.preco_atual)) +
        row('Stop' + (mov ? '<small>movido pelo trailing · era ' + F.px(p.stop_abertura) + '</small>' : ''), '<span class="neg">' + F.px(p.stop) + '</span> · ' + F.pct(dStop, 2)) +
        row('Risco na abertura<small>até o stop original, com taxa</small>', p.risco_abertura ? F.brl(p.risco_abertura) : '—') +
        row('Margem · nocional', F.brl(p.valor_reais) + ' · ' + F.brl(p.valor_reais * p.alavancagem)) +
        row('Taxa de entrada', taxaE) +
        row('Convicção na entrada', p.conviccao != null ? F.f0(p.conviccao) : '—') +
        row('Aberta em', A.ddmm(p.aberto_em) + ' ' + A.hhmm(p.aberto_em)) + '</section>' +
        (tps && (tps.niveis || []).length ? '<section class="m-card" style="gap:0;padding:4px 14px"><h5 style="padding:10px 0 2px">Alvos por estrutura</h5>' + tps.niveis.map(function (t, i) {
          return row('TP' + (i + 1) + '<small>' + esc(t.fonte || '') + '</small>', F.px(t.preco) + ' · ' + F.f1(t.r) + 'R' + (t.feito ? ' · <span class="pos">feito</span>' : ''));
        }).join('') + '</section>' : '');
    }
  };
  function row(k, v) { return '<div class="m-row"><span class="k">' + k + '</span><span class="v">' + v + '</span></div>'; }

  /* ---------- Sinal: o ticket (tamanho e perda pelo app/comum.js) e o arraste para confirmar ---------- */
  TELAS.sinal = {
    tab: 'operar', titulo: 'Sinal',
    html: function (id) {
      this.id = +id; this.s = (A.estado && (A.estado.pendentes || []).filter(function (x) { return x.id === +id; })[0]) || null;
      return mh('Sinal', { voltar: '#operar', extra: '<span id="sn-idade"></span>', semConta: true }) +
        '<div id="sn-corpo"></div>';
    },
    init: function () {
      var self = this, s = this.s;
      /* link direto antes do primeiro /estado: espera o retrato em vez de dizer que o sinal sumiu */
      if (!A.estado) { this.esperando = true; $('sn-corpo').innerHTML = '<div class="m-card"><div class="skel" style="width:40%"></div><div class="skel"></div><div class="skel" style="width:70%"></div></div>'; return; }
      if (!s) { $('sn-corpo').innerHTML = '<div class="empty">Este sinal saiu da fila: foi confirmado, pulado, expirou ou o Apollo abriu. <a class="acc-t" href="#operar">Voltar ao Operar</a>.</div>'; return; }
      var cfg = (A.estado || {}).config || {}, lev0 = +cfg.alavancagem_padrao || 10, risco0 = (parseFloat(cfg.risco_por_trade) || 0.01) * 100;
      var c = Math.round(s.conviccao || 0), exec = cfg.exec_modo === 'post_only' ? 'post-only: a ordem descansa e, se expirar, não devolve o sinal' : 'a mercado';
      $('sn-corpo').innerHTML =
        '<section class="m-hero"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><b style="font-size:24px;font-family:var(--f-display)">' + esc(F.par(s.ativo)) + '</b>' + chipLado(s.direcao) + '<span class="chip info">' + esc(s.tf || '') + '</span><span class="chip">' + esc(s.tipo || '') + '</span></div>' +
        '<div class="sig-conv" style="margin-top:10px"><span>convicção</span><span class="n" style="font-size:28px">' + c + '</span><span class="bar" style="height:8px"><i style="--w:' + c + '%"></i></span></div>' +
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px"><span class="chip" id="sn-st">aguardando preço ao vivo</span><span class="mono txt2" style="font-size:12px" id="sn-px"></span></div></section>' +
        '<section class="m-card"><h5>Por quê</h5><ul class="m-why">' + (s.motivos || '').split(', ').filter(Boolean).map(function (x) { return '<li>' + ic('confirmar') + '<span>' + esc(F.decBR(x)) + '</span></li>'; }).join('') + '</ul><div id="sn-wr" class="note"></div></section>' +
        '<section class="m-card"><h5>Ticket</h5><div class="flds"><label class="fld">VALOR R$<input class="inp" id="tk-valor" type="number" inputmode="decimal" min="1" step="1"></label>' +
        '<label class="fld">ALAVANC.<input class="inp" id="tk-lev" type="number" inputmode="numeric" min="1" max="125" step="1" value="' + lev0 + '"></label>' +
        '<label class="fld">RISCO %<input class="inp" id="tk-risco" type="number" inputmode="decimal" min="0.1" max="20" step="0.1" value="' + (+risco0.toFixed(2)) + '"></label></div>' +
        '<div id="tk-prev" style="display:grid;gap:0"></div><p class="note">Execução ' + exec + '. O risco digitado aqui só dimensiona este trade; não muda a config.</p></section>' +
        '<div id="tk-avisos" style="display:grid;gap:8px"></div>' +
        slideHtml('Arraste para confirmar', false, 'tk-slide') +
        '<button type="button" class="btn ghost block" id="sn-pular">Pular este sinal</button>';
      var v = $('tk-valor'); v.value = A.ticket.calc(s, lev0, risco0).valor;
      ['tk-valor', 'tk-lev', 'tk-risco'].forEach(function (id) { $(id).addEventListener('input', function () { self.previa(); }); });
      $('sn-pular').addEventListener('click', async function () { if (await pular(s)) location.hash = '#operar'; });
      armaSlide($('tk-slide'), function () { return self.confirma(); });
      this.previa(); this.preco();
      this.timers = [setInterval(function () { self.preco(); }, 5000)];
    },
    destroy: function () { (this.timers || []).forEach(clearInterval); },
    preco: async function () {
      var s = this.s; if (!s) return;
      try { var r = await A.api('/precos?ativos=' + encodeURIComponent(s.ativo)); M.precos[s.ativo] = r[s.ativo]; } catch (e) {}
      if (tela !== this) return;
      var pa = M.precos[s.ativo], st = A.statusEntrada(s, pa);
      $('sn-st').className = 'chip ' + st.cls; $('sn-st').textContent = st.txt;
      $('sn-px').textContent = pa ? 'agora ' + F.px(pa) + ' · sinal a ' + F.px(s.preco) + ' (' + F.pct((pa - s.preco) / s.preco * 100, 2) + ')' : 'sinal a ' + F.px(s.preco);
    },
    previa: function () {
      var s = this.s; if (!s || !$('tk-prev')) return;
      var v = +$('tk-valor').value || 0, l = +$('tk-lev').value || 1, P = A.ticket.previa(s, v, l, +$('tk-risco').value), c = P.c, x = P.expo;
      $('tk-prev').innerHTML =
        row('Entrada ~', F.px(s.preco)) +
        row('Stop sugerido', F.px(s.stop_sugerido) + ' · ' + F.f2(c.sd * 100) + '%') +
        row('R efetivo<small>min(stop, liquidação)</small>', '<span class="' + (P.liqAntes ? 'warn' : '') + '">' + F.f2(P.sdEf * 100) + '%</span>') +
        row('Nocional', F.brl(P.nocional)) +
        row('Perda no pior caso<small>com taxa nos dois lados</small>', '<b class="neg">' + F.brl(P.perda) + '</b> · ' + F.f2(P.perdaPct) + '%' + (P.margemInteira ? ' · margem inteira' : '')) +
        (x ? row('Exposição após este trade', '<span class="' + (x.estoura ? 'neg' : '') + '">' + F.brl(x.nt) + ' / ' + F.brl(x.tt) + '</span>') : '') +
        '<div class="m-row"><span class="k">Tamanho p/ arriscar ' + F.f2(c.risco * 100) + '%</span><span class="v"><b>' + F.brl(c.valor) + '</b> <button type="button" class="btn secondary sm" id="tk-usar" style="margin-left:6px">usar</button></span></div>';
      var self = this; $('tk-usar').addEventListener('click', function () { $('tk-valor').value = c.valor; self.previa(); });
      var av = '';
      if (P.liqAntes) av += '<div class="aviso neg">Alavancagem alta para esse stop: a liquidação vem antes do stop e o backend recusa o trade. Baixe para ≤ ' + P.levMax + 'x.</div>';
      if (x && x.estoura) av += '<div class="aviso neg">Estoura o teto de risco aberto: o backend recusa.</div>';
      if (x && P.nOrd) av += '<div class="aviso">Sem contar ' + P.nOrd + (P.nOrd === 1 ? ' ordem descansando' : ' ordens descansando') + ': o backend conta, então pode recusar mesmo abaixo do teto.</div>';
      if (P.trava) av += '<div class="aviso neg">Trava diária ativa: o backend vai recusar.</div>';
      $('tk-avisos').innerHTML = av;
      $('sn-wr').innerHTML = P.wr ? 'Win rate histórico nesta faixa de convicção: <b>' + P.wr.win_rate + '%</b> (' + P.wr.n + ' trades). Referência, não garantia.' : '';
      this.ok = v > 0 && l >= 1 && !P.liqAntes && !P.trava;
      $('tk-slide').classList.toggle('is-off', !this.ok || !this.naFila);
    },
    confirma: async function () {
      var s = this.s, v = +$('tk-valor').value, l = +$('tk-lev').value;
      if (!this.ok || !this.naFila) { A.toast('Ajuste o ticket: do jeito que está, o backend recusa', 'warn'); return false; }
      if (this.busy) return false; this.busy = true;
      try {
        var r = await A.api('/confirmar', { sinal_id: s.id, valor_reais: v, alavancagem: l });
        if (r && r.ok === false) { A.toast(r.erro, 'neg'); return false; }
        A.toast(r.tipo === 'ordem' ? 'Ordem post-only colocada: ' + F.par(s.ativo) + ' ' + s.direcao + ' · ' + F.brl(v) + ' @ ' + l + 'x' : s.direcao + ' ' + F.par(s.ativo) + ' aberto · ' + F.brl(v) + ' @ ' + l + 'x');
        A.carregar(); setTimeout(function () { location.hash = '#operar'; }, 700); return true;
      } catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); return false; }
      finally { this.busy = false; }
    },
    update: function (e) {
      var id = this.id;
      if (this.esperando) { this.esperando = false; this.s = (e.pendentes || []).filter(function (x) { return x.id === id; })[0] || null; this.init(); }
      if (!this.s || !$('tk-slide')) return;
      this.naFila = (e.pendentes || []).some(function (x) { return x.id === id; });
      $('sn-idade').innerHTML = this.naFila ? '<span class="chip">há ' + A.idade(this.s.ts) + '</span>' : '<span class="chip warn">saiu da fila</span>';
      this.previa();
    }
  };

  /* ---------- Apollo ---------- */
  TELAS.apollo = {
    tab: 'apollo', titulo: 'Apollo',
    html: function () {
      return mh('Apollo') +
        '<section class="m-card" style="gap:0;padding:4px 14px"><div class="m-row"><span class="k" style="color:var(--txt)">Auto-trade<small id="a-st">—</small></span><button type="button" class="tgl" role="switch" aria-checked="false" aria-label="Auto-trade" id="a-tgl"><span class="sw-t"></span></button></div><div id="a-kv"></div></section>' +
        '<section class="m-card"><h5>Guardas</h5><div id="a-g"></div><div id="a-trava"></div><div id="a-risco"></div></section>' +
        '<div id="a-ord-w" hidden><div class="m-sec"><h5 id="a-ord-h">Ordens descansando</h5></div><div id="a-ord" style="display:grid;gap:8px;margin-top:8px"></div></div>' +
        '<section class="m-card"><h5>Pânico</h5><p class="note" id="a-pan-n"></p>' + slideHtml('Arraste para o pânico', true, 'a-pan') + '</section>' +
        '<p class="note">Risco, alavancagem, convicção e saídas se configuram na versão completa (Mais › Versão completa).</p>';
    },
    init: function () {
      $('a-tgl').addEventListener('click', alternaAuto);
      /* o cartão já mostra o que o pânico faz (o mesmo resumo do sheet do topo); o arraste aqui executa.
         Depois de feito, o knob volta para o começo em 2 s: a aba continua sendo a do pânico. */
      armaSlide($('a-pan'), async function () {
        var ok = await executaPanico();
        if (ok) setTimeout(function () { var s = $('a-pan'); if (s && s._reset) s._reset(); }, 2000);
        return ok;
      });
    },
    update: function (e) {
      var cfg = e.config || {}, on = String(cfg.auto_trade) === '1', h = M.health;
      $('a-tgl').setAttribute('aria-checked', on ? 'true' : 'false');
      $('a-st').textContent = on ? 'ligado · abre e fecha sozinho' : 'desligado · só você abre posição';
      $('a-kv').innerHTML = row('Execução', cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado') + row('Risco por trade', F.f2((parseFloat(cfg.risco_por_trade) || 0) * 100) + '%') +
        row('Alavancagem', esc(levTxt(cfg))) + row('Convicção mínima', esc(cfg.auto_conviccao_min)) + row('Máx. posições', esc(cfg.auto_max_posicoes)) +
        row('Última ação', esc(F.decBR(ultimaAcao(e)))) + row('Ciclo do worker', h && h.ciclo_ha_s != null ? 'há ' + Math.round(h.ciclo_ha_s) + ' s' : '—');
      $('a-g').innerHTML = guardasHtml(e); $('a-trava').innerHTML = travaHtml(e); $('a-risco').innerHTML = riscoAbertoHtml(e);
      var od = e.ordens || []; $('a-ord-w').hidden = !od.length; $('a-ord-h').innerHTML = 'Ordens descansando · ' + cnt(od.length); $('a-ord').innerHTML = od.map(ordItem).join('');
      var n = (e.posicoes || []).length, no = od.length;
      $('a-pan-n').innerHTML = 'Grava <code>auto_trade=0</code> <b>antes</b> de fechar ' + (n ? '<b>' + n + (n === 1 ? ' posição' : ' posições') + '</b>' : 'as posições (agora: nenhuma)') + ' a mercado' +
        (no ? '. ' + no + (no === 1 ? ' ordem descansando NÃO é cancelada' : ' ordens descansando NÃO são canceladas') : '') + '. O mesmo botão fica no topo de toda tela.';
    }
  };

  /* ---------- Análise: gráfico do par com as EMAs do PRÓPRIO motor (/analise) e a leitura dele ---------- */
  TELAS.analise = {
    tab: 'analise', titulo: 'Análise',
    html: function () {
      return mh('Análise') + '<div class="chips" id="an-pares" role="group" aria-label="Par"></div>' +
        '<div class="seg" id="an-tf" role="group" aria-label="Tempo gráfico"><button type="button" data-tf="15m">15m</button><button type="button" data-tf="1h">1h</button><button type="button" data-tf="4h">4h</button><button type="button" data-tf="1d">1d</button></div>' +
        '<section class="m-card" style="padding:10px"><div class="m-sec" style="padding:0 4px"><h5 id="an-t">—</h5><span class="n" id="an-px"></span></div><div class="chart" id="an-ch"><div class="msg" id="an-msg">carregando…</div></div>' +
        '<div class="mono mute" style="font-size:10.5px;padding:0 4px">EMA 20 <span class="acc-t">━</span> · EMA 50 <span class="warn">━</span> · hora de São Paulo</div></section>' +
        '<section class="m-card"><h5>Leitura do motor</h5><div id="an-lt"><div class="skel"></div></div></section>' +
        '<div id="an-rel" style="display:grid;gap:8px"></div>';
    },
    init: function () {
      var self = this, cfg = (A.estado || {}).config || {};
      this.ativos = String(cfg.ativos || 'BTC/USDT,ETH/USDT,SOL/USDT').split(',').map(function (x) { return x.trim(); }).filter(Boolean);
      this.ativo = A.store.get('m.an.ativo'); if (this.ativos.indexOf(this.ativo) < 0) this.ativo = this.ativos[0];
      this.tf = A.store.get('m.an.tf') || '1h'; this.seq = 0;
      this.pintaSel();
      $('an-pares').addEventListener('click', function (ev) { var b = ev.target.closest('[data-a]'); if (!b) return; self.ativo = b.dataset.a; A.store.set('m.an.ativo', self.ativo); self.pintaSel(); self.carrega(); });
      $('an-tf').addEventListener('click', function (ev) { var b = ev.target.closest('[data-tf]'); if (!b) return; self.tf = b.dataset.tf; A.store.set('m.an.tf', self.tf); self.pintaSel(); self.carrega(); });
      A.lib('lightweight-charts.standalone.production.js', 'LightweightCharts').then(function (ok) {
        if (tela !== self) return;
        if (!ok) { $('an-msg').textContent = 'a biblioteca do gráfico não carregou'; return; }
        self.monta(); self.carrega();
      });
      this.timers = [setInterval(function () { self.carrega(true); }, 60000)];
    },
    destroy: function () { (this.timers || []).forEach(clearInterval); if (this.ro) this.ro.disconnect(); if (this.ch) { try { this.ch.remove(); } catch (e) {} } this.ch = null; },
    pintaSel: function () {
      var self = this;
      $('an-pares').innerHTML = this.ativos.map(function (a) { return '<button type="button" data-a="' + esc(a) + '" aria-pressed="' + (a === self.ativo) + '">' + esc(F.base(a)) + '</button>'; }).join('');
      $('an-tf').querySelectorAll('[data-tf]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.tf === self.tf)); });
    },
    monta: function () {
      var el = $('an-ch'), self = this, T = { txt: A.cor('mute'), line: A.rgba('line', .55), pos: A.cor('pos'), neg: A.cor('neg'), acc: A.cor('accent'), warn: A.cor('warn') };
      var L = A.lwcLocal(function (v) { return F.fix(v, self.prec != null ? self.prec : F.pxCasas(v)); });
      this.ch = LightweightCharts.createChart(el, { width: el.clientWidth || 340, height: el.clientHeight || 300, localization: L.localization,
        layout: { background: { color: 'transparent' }, textColor: T.txt, fontFamily: 'Fira Code, monospace', fontSize: 10 },
        grid: { vertLines: { color: T.line }, horzLines: { color: T.line } }, rightPriceScale: { borderColor: T.line },
        timeScale: { timeVisible: true, borderColor: T.line, tickMarkFormatter: L.tick }, handleScroll: { vertTouchDrag: false }, crosshair: { mode: 1 } });
      this.v = this.ch.addCandlestickSeries({ upColor: T.pos, downColor: T.neg, borderVisible: false, wickUpColor: T.pos, wickDownColor: T.neg });
      this.e20 = this.ch.addLineSeries({ color: T.acc, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      this.e50 = this.ch.addLineSeries({ color: T.warn, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      this.ro = new ResizeObserver(function () { if (self.ch && el.clientWidth) self.ch.applyOptions({ width: el.clientWidth }); }); this.ro.observe(el);
    },
    carrega: async function (silencioso) {
      if (!this.ch) return;
      var a = this.ativo, tf = this.tf, meu = ++this.seq, self = this;
      $('an-t').textContent = F.par(a) + ' · ' + tf; if (!silencioso) { $('an-msg').hidden = false; $('an-msg').textContent = 'carregando…'; }
      try {
        var r = await Promise.all([A.api('/candles?ativo=' + encodeURIComponent(a) + '&tf=' + tf + '&limite=150'), A.api('/analise?ativo=' + encodeURIComponent(a) + '&tf=' + tf).catch(function () { return null; })]);
        if (tela !== self || meu !== self.seq) return;
        var c = r[0] || [], an = r[1] || {};
        $('an-msg').hidden = !!c.length; if (!c.length) $('an-msg').textContent = 'sem velas';
        if (c.length) { var pr = self.prec = F.pxCasas(c[c.length - 1].close); self.v.applyOptions({ priceFormat: { type: 'price', precision: pr, minMove: Math.pow(10, -pr) } }); }
        self.v.setData(c); self.e20.setData(an.ema20 || []); self.e50.setData(an.ema50 || []);
        if (!silencioso) self.ch.timeScale().fitContent();
        var ult = c[c.length - 1], pri = c[0];
        $('an-px').innerHTML = ult ? F.px(ult.close) + ' <span class="' + F.cls(ult.close - pri.close) + '">' + F.pct((ult.close / pri.close - 1) * 100, 1) + '</span>' : '';
        self.leitura(an);
      } catch (err) { if (tela === self && meu === self.seq) { $('an-msg').hidden = false; $('an-msg').textContent = 'não consegui ler o /candles (' + A.erroTxt(err) + ')'; } }
    },
    leitura: function (an) {
      var e = A.estado || {}, sn = an.snapshot || {}, adxMin = +((e.config || {}).adx_min) || 25, h = '';
      if (an.leitura) h += '<p class="note" style="font-size:13px;color:var(--txt)">' + esc(F.decBR(an.leitura)) + '</p>';
      h += '<div style="display:grid;gap:0">';
      if (sn.ema20 != null) h += row('EMA 20 ' + (sn.ema20 > sn.ema50 ? '>' : '<') + ' EMA 50', '<span class="chip ' + (sn.ema20 > sn.ema50 ? 'long' : 'short') + '">' + (sn.ema20 > sn.ema50 ? 'alta' : 'baixa') + '</span>');
      if (sn.adx != null) h += row('ADX ' + F.f1(+sn.adx), sn.adx >= adxMin ? 'acima do portão (' + adxMin + ')' : 'abaixo do portão (' + adxMin + ')');
      if (sn.rsi != null) h += row('RSI ' + F.f1(+sn.rsi), sn.rsi > 70 ? 'sobrecomprado' : sn.rsi < 30 ? 'sobrevendido' : 'zona neutra');
      h += '</div>';
      $('an-lt').innerHTML = h || '<div class="empty">Sem leitura do motor para este par agora.</div>';
      this.update(e);
    },
    update: function (e) {
      if (!$('an-rel')) return;
      var a = this.ativo, sg = (e.pendentes || []).filter(function (s) { return s.ativo === a; }), ps = (e.posicoes || []).filter(function (p) { return p.ativo === a; });
      $('an-rel').innerHTML = (ps.length ? '<div class="m-sec"><h5>Posição neste par</h5></div>' + ps.map(posItem).join('') : '') + (sg.length ? '<div class="m-sec"><h5>Sinal neste par</h5></div>' + sg.map(function (s) { return sigItem(s, e); }).join('') : '');
    }
  };

  /* ---------- Mais ---------- */
  TELAS.mais = {
    tab: 'mais', titulo: 'Mais',
    html: function () {
      var cad = function (t, s) { return '<div class="m-row"><span class="k">' + ic('cadeado') + ' ' + t + '<small>' + s + '</small></span><span class="chip">em breve</span></div>'; };
      return mh('Mais') +
        '<section class="m-card" style="gap:0;padding:4px 14px">' +
        '<a class="m-row" href="#carteira"><span class="k" style="color:var(--txt)">Carteira<small>métricas de todos os trades</small></span>' + ic('chev') + '</a>' +
        '<a class="m-row" href="#diario"><span class="k" style="color:var(--txt)">Diário<small>dia a dia e journal</small></span>' + ic('chev') + '</a>' +
        '<button type="button" class="m-row" data-acao="conta"><span class="k" style="color:var(--txt)">Conta<small>' + (A.CONTA === 'B' ? 'Conta B · teste A/B' : 'Paper A · produção') + '</small></span>' + ic('chev') + '</button>' +
        '<button type="button" class="m-row" id="mx-scan"><span class="k" style="color:var(--txt)">Escanear o mercado agora<small>varre fora do ciclo do worker</small></span>' + ic('pulso') + '</button></section>' +
        '<section class="m-card"><h5>Notificações</h5><p class="note" id="nt-st">Verificando este aparelho…</p><div id="nt-acts" style="display:grid;gap:8px"></div></section>' +
        '<section class="m-card"><h5>Paleta</h5><div class="chips" id="mx-pal" role="group" aria-label="Paleta" style="margin:0;padding:2px 0;flex-wrap:wrap"></div><p class="note">Lembrada neste aparelho, a mesma do desktop.</p></section>' +
        '<section class="m-card" style="gap:0;padding:4px 14px"><h5 style="padding:10px 0 2px">Em construção</h5>' +
        cad('Notícias', 'por ativo, com o impacto nas posições') + cad('Fundamentos (LLM)', 'Pítia, com fonte em cada frase') + cad('Ações BR', 'B3: ações, índice e mini dólar') +
        '<div class="m-row"><span class="k">' + ic('pesquisa') + ' Pesquisa<small>veredito, testes e lacrados</small></span><span class="chip">no desktop</span></div></section>' +
        '<section class="m-card" style="gap:0;padding:4px 14px">' +
        '<a class="m-row" href="index.html" id="mx-full"><span class="k" style="color:var(--txt)">Versão completa<small>o painel do computador, com config e reset</small></span>' + ic('chev') + '</a>' +
        '<button type="button" class="m-row" id="mx-sair"><span class="k neg">Sair<small>encerra a sessão neste aparelho</small></span></button></section>' +
        '<div class="foot" id="mx-foot"></div>';
    },
    init: function () {
      $('mx-pal').innerHTML = A.paletas.map(function (p) { return '<button type="button" data-p="' + esc(p.id) + '" aria-pressed="' + (A.store.get('pulse.paleta') === p.id || (!A.store.get('pulse.paleta') && p.id === 'osso')) + '" style="--c:' + esc(p.t.accent) + '"><i></i>' + esc(p.nome) + '</button>'; }).join('');
      $('mx-pal').addEventListener('click', function (ev) {
        var b = ev.target.closest('[data-p]'); if (!b) return; var p = A.paletaPorId(b.dataset.p); if (!p) return;
        A.pintaPaleta(p); A.store.set('pulse.paleta', p.id); A.emit('paleta', p);
        $('mx-pal').querySelectorAll('[data-p]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      });
      $('mx-scan').addEventListener('click', async function () {
        A.toast('Escaneando o mercado…');
        try { var s = await A.api('/scan', {}); A.toast('Varridos ' + s.varridos + ' · ' + s.novos + (s.novos === 1 ? ' sinal novo' : ' sinais novos')); A.carregar(); }
        catch (err) { A.toast('Scan falhou: ' + A.erroTxt(err), 'neg'); }
      });
      $('mx-full').addEventListener('click', function () { A.store.set('apx.ui', 'desktop'); });
      $('mx-sair').addEventListener('click', function () { A.sair(); });
      this.update(A.estado || {});
      this.notif();
    },
    /* [PUSH-1] Notificação nativa. Quatro estados, nesta ordem: o aparelho não suporta (no iPhone,
       Safari em aba: só o app instalado recebe), o backend não tem chave, o usuário bloqueou, e
       ligado/desligado PARA ESTA CONTA -- o mesmo aparelho pode receber da A e não da B. */
    notif: async function () {
      var self = this, st = $('nt-st'), box = $('nt-acts'); if (!st) return;
      var acts = function (h) { box.innerHTML = h; };
      var ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
      var app = navigator.standalone === true || !!(window.matchMedia && matchMedia('(display-mode: standalone)').matches);
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        st.innerHTML = ios && !app ? 'No iPhone a notificação só chega no app instalado. No Safari: <b>Compartilhar → Adicionar à Tela de Início</b>, e abra pelo ícone do Apollux.' : 'Este navegador não recebe notificação push.';
        acts(''); return;
      }
      var reg = await Promise.race([navigator.serviceWorker.ready, new Promise(function (r) { setTimeout(function () { r(null); }, 5000); })]);
      if (tela !== self) return;
      if (!reg) { st.textContent = 'O app ainda não terminou de instalar neste aparelho. Feche e abra de novo.'; acts(''); return; }
      var sub = null; try { sub = await reg.pushManager.getSubscription(); } catch (e) { sub = null; }
      var k = null;
      try { k = await A.api('/push/chave' + (sub ? '?endpoint=' + encodeURIComponent(sub.endpoint) : '')); }
      /* 404 = o front já publicou (merge na main) e o backend do dl380 ainda roda o commit de antes */
      catch (e) { if (tela === self) { st.textContent = e.status === 404 ? 'O backend ainda não tem notificação: falta o deploy no servidor.' : 'Não consegui falar com o backend: ' + A.erroTxt(e); acts(''); } return; }
      if (tela !== self) return;
      self.k = k; self.reg = reg; self.sub = sub;
      var conta = 'conta ' + esc(k.conta || A.CONTA);
      if (!k.ativo) { st.textContent = 'O backend ainda não está pronto para notificação: ' + k.motivo + '.'; acts(''); return; }
      if (Notification.permission === 'denied') { st.innerHTML = 'Bloqueadas neste aparelho. Libere em <b>Ajustes → Notificações → Apollux</b> e volte aqui.'; acts(''); return; }
      if (sub && k.inscrito) {
        st.innerHTML = 'Ligadas neste aparelho para a <b>' + conta + '</b>: abriu, ordem preenchida, fechou, parcial e trava diária.';
        acts('<button type="button" class="btn secondary block" id="nt-teste">Mandar um teste</button><button type="button" class="btn ghost block" id="nt-off">Desligar nesta conta</button>');
        $('nt-teste').onclick = function () { self.teste(); };
        $('nt-off').onclick = function () { self.desligar(); };
      } else {
        st.innerHTML = sub ? 'Desligadas neste aparelho para a <b>' + conta + '</b>.' : 'Receba no celular, como notificação do sistema, quando um trade abre, a ordem enche, a posição fecha ou a trava diária dispara.';
        acts('<button type="button" class="btn primary block" id="nt-on">' + ic('sino') + 'Ativar notificações' + (sub ? ' da ' + conta : '') + '</button>');
        $('nt-on').onclick = function () { self.ativar(); };
      }
    },
    ativar: async function () {
      var b = $('nt-on');
      /* o pedido de permissão é a PRIMEIRA coisa do toque: o iOS só abre o diálogo dentro do gesto,
         e um await de rede antes dele faria o pedido sair fora do gesto e ser negado calado */
      var perm = await Notification.requestPermission();
      if (perm !== 'granted') { A.toast(perm === 'denied' ? 'Bloqueadas: libere em Ajustes → Notificações → Apollux' : 'Permissão não concedida', 'warn'); return this.notif(); }
      if (b) b.disabled = true;
      try {
        var sub = this.sub || await this.reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: chaveBytes(this.k.chave) });
        var r = await A.api('/push/inscrever', sub.toJSON());
        if (!r.ok) throw new Error(r.erro || 'recusado pelo backend');
        var t = await A.api('/push/teste', { endpoint: sub.endpoint });
        A.toast(t.ok ? 'Notificações ligadas · mandei um teste' : 'Ligadas, mas o teste não saiu: ' + (t.motivo || 'falha no serviço de push'), t.ok ? '' : 'warn');
      } catch (e) { A.toast('Não deu para ativar: ' + A.erroTxt(e), 'neg'); }
      this.notif();
    },
    teste: async function () {
      try { var t = await A.api('/push/teste', { endpoint: this.sub.endpoint }); A.toast(t.ok ? 'Teste enviado: chega em segundos' : 'O teste não saiu (' + (t.motivo || t.falhas + ' falha') + ')', t.ok ? '' : 'warn'); }
      catch (e) { A.toast('Erro: ' + A.erroTxt(e), 'neg'); }
    },
    desligar: async function () {
      try { await A.api('/push/sair', { endpoint: this.sub.endpoint }); A.toast('Notificações desta conta desligadas'); }
      catch (e) { A.toast('Erro: ' + A.erroTxt(e), 'neg'); }
      this.notif();
    },
    update: function () {
      var h = M.health; $('mx-foot').textContent = 'Apollux · ' + NOME_CONTA + (h ? ' · v' + h.versao + (h.commit ? ' · ' + String(h.commit).slice(0, 7) : '') : '') + ' · paper trading: dinheiro fictício, preço real';
    }
  };

  /* ---------- Carteira: as MESMAS métricas e rótulos do desktop ---------- */
  TELAS.carteira = {
    tab: 'mais', titulo: 'Carteira',
    html: function () {
      return mh('Carteira', { voltar: '#mais', semConta: true }) +
        '<section class="m-hero" style="gap:2px"><span class="kpi-lbl">P&amp;L fechado · todos os trades</span><div class="eq" id="ct-pnl">—</div><span class="mono txt2" style="font-size:12px" id="ct-sub"></span></section>' +
        '<div class="mt" id="ct-mt"></div>' +
        '<section class="m-card" style="gap:0;padding:4px 14px"><h5 style="padding:10px 0 2px">Por faixa de convicção</h5><div id="ct-cv"></div></section>' +
        '<p class="note">Toque e segure uma métrica para ler como ela é calculada.</p>';
    },
    update: function (e) {
      var m = e.metricas || {}, tem = !!m.n_trades, xr = A.expR(m), dd = m.max_drawdown || 0, banca = e.banca || {};
      $('ct-pnl').className = 'eq ' + F.cls(m.pnl_total); $('ct-pnl').textContent = F.money(m.pnl_total);
      $('ct-sub').textContent = (m.n_trades || 0) + ' trades · taxas ' + F.brl(m.taxa_total) + ' · banca inicial ' + F.brl(banca.inicial);
      var L = [['Win rate', tem ? F.f1(m.win_rate) + '%' : '—', '', 'trades com P&L > 0 ÷ trades'],
        ['Profit factor', !tem ? '—' : m.profit_factor >= 999 ? '∞' : F.f2(m.profit_factor), '', 'soma dos ganhos ÷ soma das perdas'],
        ['Ganho médio', F.money(m.ganho_medio), 'pos', ''], ['Perda média', F.money(m.perda_media), 'neg', ''],
        ['Expectativa', tem ? F.money(m.expectancia) : '—', F.cls(m.expectancia), 'P&L médio por trade'],
        ['Expectativa (R)', xr.txt + (xr.n ? ' <small class="mute">' + xr.n + ' tr.</small>' : ''), F.cls(xr.v), 'P&L ÷ risco até o stop gravado na abertura'],
        ['SQN (R)', xr.n ? F.f2(xr.sqn) : '—', '', 'média ÷ desvio dos R × √min(n,100)'],
        ['Sharpe', tem ? F.f2(m.sharpe) : '—', '', 'retornos diários da curva, ×√365'],
        ['DD máx. fechado', dd ? F.money(-dd) + ' · ' + F.pct(-(m.max_drawdown_pct || 0), 1) : '—', dd ? 'neg' : '', 'maior queda da curva realizada'],
        ['DD máx. c/ aberto', m.max_dd_mtm_pct ? F.pct(-m.max_dd_mtm_pct, 1) : '—', m.max_dd_mtm_pct ? 'neg' : '', 'com o P&L das abertas'],
        ['Lucro ÷ DD máx.', tem && dd ? F.f2(m.calmar) : '—', '', 'não é o Calmar anualizado'],
        ['Sortino', tem ? F.f2(m.sortino) : '—', '', 'média ÷ desvio das perdas']];
      $('ct-mt').innerHTML = L.map(function (x) { return '<div title="' + esc(x[3]) + '"><div class="k">' + x[0] + '</div><div class="v ' + x[2] + '">' + x[1] + '</div>' + (x[3] ? '<div class="h">' + esc(x[3]) + '</div>' : '') + '</div>'; }).join('');
      var cv = m.por_conviccao || [];
      $('ct-cv').innerHTML = cv.length ? cv.map(function (c) { return row('Convicção ' + esc(c.faixa) + '<small>' + c.n + ' trades</small>', F.f1(c.win_rate) + '% · <span class="' + F.cls(c.pnl) + '">' + F.money(c.pnl) + '</span>'); }).join('') : '<div class="empty" style="margin:10px 0">Sem trades ainda.</div>';
    }
  };

  /* ---------- Diário: P&L FECHADO por dia (14 dias) e o journal ---------- */
  TELAS.diario = {
    tab: 'mais', titulo: 'Diário',
    html: function () {
      return mh('Diário', { voltar: '#mais', semConta: true }) +
        '<section class="m-card"><div class="m-sec" style="padding:0"><h5>Últimos 14 dias</h5><span class="n" id="dd-seq"></span></div><div id="dd-b"><div class="skel"></div><div class="skel"></div></div>' +
        '<p class="note">P&amp;L fechado por dia, agrupado em hora de São Paulo. O "hoje" é só o que já fechou; o P&amp;L do dia do Painel soma o aberto.</p></section>' +
        '<div class="m-sec"><h5>Journal</h5><span class="n" id="dd-n"></span></div><section class="m-card" style="padding:4px 14px"><ul class="jr" id="dd-jr"></ul></section><button type="button" class="btn secondary block" id="dd-mais" hidden>Mostrar mais 30</button>';
    },
    init: function () { this.nJr = 30; this.trades(); },
    trades: function () {
      var tr = M.tr; if (!tr || !$('dd-b')) return;
      var por = {}; tr.forEach(function (t) { var k = A.dia(t.fechado_em); var d = por[k] || (por[k] = { pnl: 0, n: 0 }); d.pnl += t.pnl_reais || 0; d.n++; });
      var hk = A.hoje(), base = new Date(+hk.slice(0, 4), +hk.slice(5, 7) - 1, +hk.slice(8, 10)), dias = [];
      for (var i = 13; i >= 0; i--) { var d = new Date(base); d.setDate(d.getDate() - i); var k = d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2), x = por[k] || { pnl: 0, n: 0 }; dias.push({ k: k, pnl: Math.round(x.pnl * 100) / 100, n: x.n }); }
      /* o mais antigo dos 500 pode ter o dia incompleto: não desenha dia anterior à cobertura */
      var ini = tr.length >= LIM ? A.dia(tr[0].fechado_em) : '';
      var mx = Math.max.apply(null, dias.map(function (x) { return Math.abs(x.pnl); })) || 1;
      var bars = dias.map(function (x) {
        var fora = ini && x.k <= ini, alt = (Math.abs(x.pnl) / mx * 100).toFixed(1) + '%';
        return '<div class="c' + (x.k === hk ? ' hoje' : '') + '" title="' + A.ddmm(x.k) + ': ' + (fora ? 'fora da cobertura' : x.n ? F.money(x.pnl) + ', ' + x.n + ' trades' : 'sem trade') + '"><i class="u" style="height:' + (x.pnl > 0 && !fora ? alt : '0') + '"></i><i class="d" style="height:' + (x.pnl < 0 && !fora ? alt : '0') + '"></i></div>';
      }).join('');
      var lbls = dias.map(function (x) { return '<span>' + A.ddmm(x.k).slice(0, 2) + '</span>'; }).join('');
      var soma = function (n) { return dias.slice(-n).reduce(function (a, x) { return a + x.pnl; }, 0); };
      var hoje = dias[dias.length - 1], mes = M.mes || { pnl: 0 };
      var dir = 0, cnt = 0; for (var j = dias.length - 1; j >= 0; j--) { var dj = dias[j]; if (!dj.n) continue; var sg = dj.pnl > 0 ? 1 : dj.pnl < 0 ? -1 : 0; if (!dir) dir = sg; if (sg !== dir || !sg) break; cnt++; }
      $('dd-seq').innerHTML = cnt ? '<span class="' + (dir > 0 ? 'pos' : 'neg') + '">' + cnt + (dir > 0 ? (cnt > 1 ? ' dias positivos' : ' dia positivo') : (cnt > 1 ? ' dias negativos' : ' dia negativo')) + '</span>' : '';
      $('dd-b').innerHTML = '<div class="ddb" role="img" aria-label="P&L fechado por dia nos últimos 14 dias">' + bars + '</div><div class="ddl" aria-hidden="true">' + lbls + '</div>' +
        /* linhas, não três caixas: a 360 px cada caixa tem ~76 px e "-R$ 1.234,56" quebrava no meio do número */
        '<div class="dds">' + row('Hoje', '<b class="' + F.cls(hoje.pnl) + '">' + F.money(hoje.pnl) + '</b>') + row('7 dias', '<b class="' + F.cls(soma(7)) + '">' + F.money(soma(7)) + '</b>') + row('Mês', '<b class="' + F.cls(mes.pnl) + '">' + F.money(mes.pnl) + '</b>') + '</div>';
      var self = this, l = tr.slice().reverse(), n = this.nJr || 30; $('dd-n').textContent = Math.min(n, l.length) + ' de ' + l.length;
      $('dd-jr').innerHTML = jrItens(l.slice(0, n));
      $('dd-mais').hidden = l.length <= n; $('dd-mais').onclick = function () { self.nJr = n + 30; self.trades(); };
    }
  };

  /* ================= roteador ================= */
  var tela = null, rotaAtual = null, tabs = Array.prototype.slice.call(document.querySelectorAll('#m-tabs [data-tab]'));
  function parse() {
    var h = location.hash.replace(/^#/, '').split('?')[0], p = h.split('/');
    if (TELAS[p[0]] && (p[0] !== 'pos' && p[0] !== 'sinal' || p[1])) return { id: p[0], arg: p[1], chave: h };
    return { id: 'painel', chave: 'painel' };
  }
  function vai() {
    var r = parse(); if (r.chave === rotaAtual) return; rotaAtual = r.chave;
    if (sheetRes) sheetRes(false);
    if (tela && tela.destroy) { try { tela.destroy(); } catch (e) { console.error('tela destroy', e); } }
    var t = TELAS[r.id]; tela = t;
    tabs.forEach(function (a) { var on = a.dataset.tab === t.tab; a.classList.toggle('is-active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    document.title = (A.CONTA === 'B' ? '[Conta B] ' : '') + t.titulo + ' · Apollux';
    /* nó novo por montagem (mesma regra do desktop): listener delegado morre com a tela */
    var mount = document.createElement('div'); mount.style.display = 'contents';
    mount.innerHTML = t.html(r.arg);
    var raiz = $('m-root'); raiz.innerHTML = ''; raiz.appendChild(mount);
    window.scrollTo(0, 0);
    try { if (t.init) t.init(); if (t.update && A.estado) t.update(A.estado); } catch (e) { console.error('tela ' + r.id, e); }
    pintaConn();
    if (window.gsap && !A.RM) gsap.from(mount.children, { y: 10, opacity: 0, duration: .35, stagger: .04, ease: 'power2.out', clearProps: 'transform,opacity' });
  }
  window.addEventListener('hashchange', vai);
  A.on('estado', function (e) { if (tela && tela.update) { try { tela.update(e); } catch (err) { console.error('tela update', err); } } badges(e); });
  function badges(e) { var n = (e.pendentes || []).length + (e.ordens || []).length, b = $('tb-operar'); b.hidden = !n; b.textContent = n; }
  /* cliques que valem em qualquer tela: conta, pânico, pular */
  $('m-root').addEventListener('click', function (ev) {
    var a = ev.target.closest('[data-acao]');
    if (a) { if (a.dataset.acao === 'panico') panico(); else if (a.dataset.acao === 'conta') trocaContaSheet(); return; }
    var pj = ev.target.closest('[data-pular]');
    if (pj) { var s = ((A.estado || {}).pendentes || []).filter(function (x) { return x.id === +pj.dataset.pular; })[0]; if (s) { pj.disabled = true; pular(s); } }
  });
  var rsT = 0; window.addEventListener('resize', function () { clearTimeout(rsT); rsT = setTimeout(function () { if (tela && tela.update && A.estado) tela.update(A.estado); }, 200); });

  /* ================= login: os mesmos ids do index.html ================= */
  $('gate-form').addEventListener('submit', A._gateEntrar);
  $('gate-eye').addEventListener('click', function () { var i = $('gate-pass'), oc = i.type === 'password'; i.type = oc ? 'text' : 'password'; this.textContent = oc ? 'ocultar' : 'ver'; this.setAttribute('aria-label', oc ? 'Ocultar senha' : 'Mostrar senha'); i.focus(); });
  ['keydown', 'keyup'].forEach(function (ev) { $('gate-pass').addEventListener(ev, function (e) { $('gate-caps').classList.toggle('on', !!(e.getModifierState && e.getModifierState('CapsLock'))); }); });

  /* ================= boot ================= */
  vai();
  A.carregar(); A.iniciar(); saudeLoop();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(function () {});
    /* [PUSH-1] toque numa notificação com o app aberto: o SW manda o hash da tela do aviso */
    navigator.serviceWorker.addEventListener('message', function (e) {
      var d = e.data || {}; if (d.tipo === 'abrir' && typeof d.url === 'string' && d.url.charAt(0) === '#') location.hash = d.url;
    });
  }
})();
