/* Apollux · view Operar (#operar): a mesa. Age sobre o que existe no backend: SINAL (confirmar, pular),
   POSIÇÃO (fechar) e ORDEM post-only (só leitura: não há rota de cancelar). O ticket livre do mock (ordem
   em qualquer par, sem sinal) é a fase F6 e fica "em breve": abrir posição sem sinal não tem rota.

   Dado real e rotas, todas só com a view montada: /estado (casca, 3 s) · /precos dos pares da config (8 s) ·
   /candles do par (ao trocar par/TF e a cada 30 s, como o clássico) · /analise (EMA 20/50 e Bollinger do
   próprio motor, paridade) · /book (6 s, como o clássico) · /smartmoney (com o par) · /saidas (8 s).
   Fora do mock, declarado: variação 24 h por par (nenhuma rota entrega; a lista mostra o preço e a série
   observada desde que a tela abriu), volume (o /candles não traz), book nível a nível e time & sales (o
   /book devolve o resumo ±1%, não os níveis; no lugar entram os trades fechados deste par). */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt;
  var TFS = ['5m', '15m', '1h', '4h', '1d'], TF_SEG = { '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400 };
  var css = '<style>' +
  '.v-operar{display:grid;grid-template-columns:250px minmax(0,1fr) 340px;gap:18px;align-items:start;min-width:0}' +
  '.v-operar .col{display:grid;gap:18px;min-width:0}' +
  '.v-operar .wl-search{display:flex;align-items:center;gap:8px;border:1px solid var(--line2);border-radius:10px;padding:0 10px;background:var(--panel2);margin-bottom:10px}' +
  '.v-operar .wl-search input{flex:1;min-width:0;background:none;border:0;color:var(--txt);font:inherit;font-size:13px;padding:9px 0;outline:none}' +
  '.v-operar .wl-search:focus-within{border-color:var(--accent)}' +
  '.v-operar .wl{list-style:none;margin:0;padding:0;display:grid;gap:4px;max-height:640px;overflow:auto;scrollbar-width:thin}' +
  '.v-operar .wl button{width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 8px;align-items:center;text-align:left;background:none;border:1px solid transparent;border-radius:10px;padding:8px 10px;color:var(--txt);cursor:pointer;font:inherit}' +
  '.v-operar .wl button:hover{background:var(--panel2)}' +
  '.v-operar .wl button.is-on{background:rgba(var(--accent-rgb),.1);border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-operar .wl .p{font-family:var(--f-mono);font-weight:600;font-size:12.5px;display:flex;gap:6px;align-items:center;min-width:0}' +
  '.v-operar .wl .is-on .p{color:var(--accent)}' +
  '.v-operar .wl .px{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2)}' +
  '.v-operar .wl .tags{display:flex;gap:4px;justify-content:flex-end}' +
  '.v-operar .wl .chip{font-size:9.5px;padding:1px 6px}' +
  '.v-operar .wl-note{font-family:var(--f-mono);font-size:10.5px;color:var(--mute);margin-top:10px;line-height:1.5}' +
  '.v-operar .ch-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}' +
  '.v-operar .ch-par{font-family:var(--f-display);font-weight:800;font-size:22px;letter-spacing:.02em}' +
  '.v-operar .ch-px{font-family:var(--f-mono);font-size:20px;font-weight:600}' +
  '.v-operar .ch-sub{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);margin:4px 0 10px}' +
  '.v-operar .ch-tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}' +
  '.v-operar .ind{display:flex;gap:6px;flex-wrap:wrap}' +
  '.v-operar .ind button{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line2);background:none;color:var(--txt2);border-radius:999px;padding:4px 10px;font-family:var(--f-mono);font-size:11px;cursor:pointer}' +
  '.v-operar .ind button i{width:8px;height:8px;border-radius:50%;background:var(--c,var(--mute));opacity:.35}' +
  '.v-operar .ind button[aria-pressed="true"]{color:var(--txt);border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-operar .ind button[aria-pressed="true"] i{opacity:1}' +
  '.v-operar .ind button:disabled{opacity:.45;cursor:not-allowed}' +
  '.v-operar .chart{position:relative;height:420px;border-radius:10px;overflow:hidden}' +
  '.v-operar .chart-msg[hidden]{display:none}' +
  '.v-operar .chart-msg{position:absolute;inset:0;display:grid;place-items:center;font-family:var(--f-mono);font-size:12px;color:var(--mute);pointer-events:none;text-align:center;padding:16px}' +
  '.v-operar .ch-foot{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);margin-top:10px;display:flex;flex-wrap:wrap;gap:4px 14px}' +
  '.v-operar .ch-foot b{color:var(--txt);font-weight:600}' +
  '.v-operar .anal{margin-top:12px;border:1px solid rgba(var(--accent-rgb),var(--glow-lo));border-radius:12px;padding:12px;background:var(--panel2)}' +
  '.v-operar .anal p{margin:6px 0 10px;font-size:12.5px;color:var(--txt2);line-height:1.55}' +
  '.v-operar .anal .g{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;font-family:var(--f-mono);font-size:11.5px}' +
  '.v-operar .anal .g span{display:block;color:var(--mute);font-size:10px;letter-spacing:.08em;text-transform:uppercase}' +
  '.v-operar .bk{display:grid;gap:10px;font-size:12.5px}' +
  '.v-operar .bk-bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:rgba(var(--txt-rgb),.08)}' +
  '.v-operar .bk-bar i{display:block;background:var(--pos)} .v-operar .bk-bar b{display:block;flex:1;background:var(--neg)}' +
  '.v-operar .bk-row{display:flex;justify-content:space-between;gap:10px;font-family:var(--f-mono);font-size:12px}' +
  '.v-operar .bk-row span:first-child{color:var(--txt2);font-family:var(--f-ui)}' +
  '.v-operar .bk-sep{border-top:1px solid var(--line);margin:2px 0}' +
  '.v-operar .bk-note{font-family:var(--f-mono);font-size:10.5px;color:var(--mute);line-height:1.5}' +
  '.v-operar .sg{display:grid;gap:10px}' +
  '.v-operar .sg-item{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2);display:grid;gap:8px}' +
  '.v-operar .sg-item.is-on{border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-operar .sg-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}' +
  '.v-operar .sg-top .t{margin-left:auto;font-family:var(--f-mono);font-size:11px;color:var(--txt2)}' +
  '.v-operar .sg-kv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;font-family:var(--f-mono);font-size:11.5px}' +
  '.v-operar .sg-kv span{display:block;color:var(--mute);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase}' +
  '.v-operar .sg-act{display:flex;gap:8px;flex-wrap:wrap}' +
  '.v-operar .ps{display:grid;gap:10px}' +
  '.v-operar .ps-item{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2);display:grid;gap:6px}' +
  '.v-operar .ps-item.is-on{border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-operar .ps-top{display:flex;gap:8px;align-items:center}' +
  '.v-operar .ps-top .amt{margin-left:auto;font-family:var(--f-mono);font-weight:600;font-size:15px}' +
  '.v-operar .ps-meta{font-family:var(--f-mono);font-size:11px;color:var(--txt2);display:flex;flex-wrap:wrap;gap:2px 12px}' +
  '.v-operar .ps-saida{font-size:11.5px;color:var(--warn);border:1px solid rgba(var(--warn-rgb),.35);border-radius:8px;padding:5px 8px}' +
  '.v-operar .tk-soon{display:grid;gap:8px;font-size:12.5px;color:var(--txt2)}' +
  '.v-operar .tk-soon .seg button{pointer-events:none}' +
  '.v-operar .jr{list-style:none;margin:0;padding:0}' +
  '.v-operar .jr li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;padding:7px 0;border-bottom:1px solid rgba(var(--line-rgb),.6);font-family:var(--f-mono);font-size:11.5px;align-items:center}' +
  '.v-operar .jr li:last-child{border-bottom:0}' +
  '.v-operar .jr .w{color:var(--mute)}' +
  '@media (max-width:1300px){.v-operar{grid-template-columns:220px minmax(0,1fr)}.v-operar .col-r{grid-column:1/-1;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}' +
  '@media (max-width:900px){.v-operar{grid-template-columns:minmax(0,1fr)}.v-operar .wl{grid-auto-flow:column;grid-auto-columns:150px;overflow-x:auto;max-height:none;padding-bottom:4px}.v-operar .chart{height:320px}.v-operar .anal .g{grid-template-columns:repeat(3,minmax(0,1fr))}}' +
  '</style>';

  var html = css + '<div class="v-operar">' +
    '<div class="col"><section class="card" aria-label="Pares"><div class="card-head"><h2 class="h2">Pares</h2><span class="count" id="op-wl-n">—</span></div>' +
      '<label class="wl-search"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="op-busca" type="search" placeholder="Buscar par…" aria-label="Buscar par" autocomplete="off"></label>' +
      '<ul class="wl" id="op-wl"></ul><div class="wl-note">os pares que o motor varre (config <span class="mono">ativos</span>) · preço a cada 8 s · a linha é o preço observado desde que você abriu esta tela</div></section></div>' +
    '<div class="col">' +
      '<section class="card"><div class="ch-head"><span class="ch-par" id="op-par">—</span><span class="ch-px" id="op-px">—</span><span class="mono" id="op-var"></span></div>' +
        '<div class="ch-sub" id="op-sub">—</div>' +
        '<div class="ch-tools"><div class="seg" id="op-tf" role="group" aria-label="Tempo gráfico">' + TFS.map(function (t) { return '<button type="button" data-tf="' + t + '" aria-pressed="false">' + t + '</button>'; }).join('') + '</div>' +
        '<div class="ind" id="op-ind">' +
          '<button type="button" data-ind="ema" aria-pressed="true" style="--c:var(--accent)"><i></i>EMA 20 · 50</button>' +
          '<button type="button" data-ind="bb" aria-pressed="false" style="--c:var(--txt2)"><i></i>Bollinger</button>' +
          '<button type="button" data-ind="don" aria-pressed="false" style="--c:var(--info)"><i></i>Donchian 20</button>' +
          '<button type="button" data-ind="liq" aria-pressed="true" style="--c:var(--warn)"><i></i>Liquidez</button>' +
          '<button type="button" disabled title="o /candles não traz volume"><i></i>Volume · sem dado</button></div></div>' +
        '<div class="chart" id="op-chart"><div class="chart-msg" id="op-chart-msg">carregando o gráfico…</div></div>' +
        '<div class="ch-foot" id="op-foot"></div><div id="op-anal"></div></section>' +
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px"><section class="card"><div class="card-head"><h2 class="h2">Book e fluxo</h2><span class="count mute" id="op-bk-t">resumo ±1%</span></div><div class="bk" id="op-book"><div class="skel"></div><div class="skel"></div></div></section>' +
      '<section class="card"><div class="card-head"><h2 class="h2">Trades neste par</h2><span class="count" id="op-jr-n">0</span></div><ul class="jr" id="op-jr"></ul></section></div>' +
    '</div>' +
    '<div class="col col-r">' +
      '<section class="card"><div class="card-head"><h2 class="h2">Sinais na fila</h2><span class="count" id="op-sg-n">0</span></div><div class="sg" id="op-sg"></div></section>' +
      '<section class="card"><div class="card-head"><h2 class="h2">Ticket livre</h2><span class="soon">em breve · F6</span></div><div class="tk-soon">' +
        '<div class="seg" aria-hidden="true"><button type="button" aria-pressed="true">Comprar · LONG</button><button type="button">Vender · SHORT</button></div>' +
        '<p style="margin:0">Ordem em qualquer par, sem sinal do motor. Hoje o backend só abre posição a partir de um sinal (o tamanho e a prévia de risco ficam no <b>Confirmar</b> de cada sinal).</p></div></section>' +
      '<section class="card"><div class="card-head"><h2 class="h2">Posições</h2><span class="count" id="op-ps-n">0</span></div><div class="ps" id="op-ps"></div></section>' +
      '<section class="card"><div class="card-head"><h2 class="h2">Ordens descansando</h2><span class="count" id="op-od-n">0</span></div><div class="ps" id="op-od"></div></section>' +
    '</div>' +
  '</div>';

  var S = null;
  function $(id) { return S && S.root.querySelector('#' + id); }
  function pares(e) { return String(((e || {}).config || {}).ativos || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean); }

  /* ---------- lista de pares ---------- */
  function lista() {
    var e = S.estado || {}, l = pares(e), q = ($('op-busca').value || '').trim().toUpperCase();
    var sig = {}, pos = {};
    (e.pendentes || []).forEach(function (s) { sig[s.ativo] = s.direcao; });
    (e.posicoes || []).forEach(function (p) { pos[p.ativo] = p.direcao; });
    $('op-wl-n').textContent = l.length + ' pares';
    var f = l.filter(function (a) { return !q || F.par(a).indexOf(q) >= 0; });
    $('op-wl').innerHTML = f.map(function (a) {
      var px = S.precos[a], ser = S.serie[a];
      return '<li><button type="button" data-par="' + A.esc(a) + '" class="' + (a === S.ativo ? 'is-on' : '') + '" aria-pressed="' + (a === S.ativo) + '">' +
        '<span class="p">' + A.esc(F.par(a)) + '</span><span class="tags">' + (pos[a] ? '<span class="chip info" title="posição aberta">pos</span>' : '') + (sig[a] ? '<span class="chip ' + (sig[a] === 'LONG' ? 'long' : 'short') + '" title="sinal na fila">' + sig[a] + '</span>' : '') + '</span>' +
        '<span class="px">' + (px ? F.px(px) : '—') + '</span><span>' + A.spark(ser) + '</span></button></li>';
    }).join('') || '<li class="mute" style="font-size:12px;padding:8px">Nenhum par com “' + A.esc(q) + '”.</li>';
  }
  async function precos() {
    var l = pares(S.estado); if (!l.length) return;
    try {
      var p = await A.api('/precos?ativos=' + encodeURIComponent(l.join(',')));
      if (!S) return;
      Object.keys(p || {}).forEach(function (k) { var v = p[k]; if (typeof v !== 'number') return; S.precos[k] = v; var s = S.serie[k] || (S.serie[k] = []); if (s[s.length - 1] !== v) s.push(v); if (s.length > 40) s.shift(); });
      lista(); cabecalho(); sinais(S.estado);
    } catch (err) {}
  }

  /* ---------- gráfico (Lightweight-Charts vendorado; cores lidas dos tokens na hora) ---------- */
  function tema() {
    return { bg: A.cor('panel'), txt: A.cor('mute'), line: A.rgba('line', .55), pos: A.cor('pos'), neg: A.cor('neg'), acc: A.cor('accent'), warn: A.cor('warn'), info: A.cor('info'), txt2: A.cor('txt2') };
  }
  function montaGrafico() {
    /* o eixo usa a precisão do PAR (pela última vela), não a de cada marca: senão saíam "1,0652" e "0,99750" lado a lado */
    var el = $('op-chart'), T = tema(), L = A.lwcLocal(function (v) { return F.fix(v, S && S.prec != null ? S.prec : F.pxCasas(v)); });
    S.chart = LightweightCharts.createChart(el, {
      width: el.clientWidth || 600, height: el.clientHeight || 420, localization: L.localization,
      layout: { background: { color: 'transparent' }, textColor: T.txt, fontFamily: 'Fira Code, monospace', fontSize: 11 },
      grid: { vertLines: { color: T.line }, horzLines: { color: T.line } },
      timeScale: { timeVisible: true, borderColor: T.line, tickMarkFormatter: L.tick }, rightPriceScale: { borderColor: T.line }, crosshair: { mode: 1 }
    });
    S.velas = S.chart.addCandlestickSeries({ upColor: T.pos, downColor: T.neg, borderVisible: false, wickUpColor: T.pos, wickDownColor: T.neg });
    var ln = function (c, w, st) { return S.chart.addLineSeries({ color: c, lineWidth: w, lineStyle: st || 0, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }); };
    S.ser = { ema20: ln(T.acc, 2), ema50: ln(T.warn, 2), bbU: ln(T.txt2, 1), bbM: ln(T.txt2, 1, 2), bbL: ln(T.txt2, 1), donU: ln(T.info, 1, 1), donL: ln(T.info, 1, 1) };
    S.ro = new ResizeObserver(function () { if (S && S.chart && el.clientWidth) S.chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }); });
    S.ro.observe(el);
  }
  function recolore() {
    if (!S || !S.chart) return; var T = tema();
    S.chart.applyOptions({ layout: { textColor: T.txt }, grid: { vertLines: { color: T.line }, horzLines: { color: T.line } }, timeScale: { borderColor: T.line }, rightPriceScale: { borderColor: T.line } });
    S.velas.applyOptions({ upColor: T.pos, downColor: T.neg, wickUpColor: T.pos, wickDownColor: T.neg });
    S.ser.ema20.applyOptions({ color: T.acc }); S.ser.ema50.applyOptions({ color: T.warn });
    ['bbU', 'bbM', 'bbL'].forEach(function (k) { S.ser[k].applyOptions({ color: T.txt2 }); });
    ['donU', 'donL'].forEach(function (k) { S.ser[k].applyOptions({ color: T.info }); });
    linhas();
  }
  function atr(c, n) {
    if (c.length < n + 1) return null; var s = 0;
    for (var i = c.length - n; i < c.length; i++) { var p = c[i - 1].close; s += Math.max(c[i].high - c[i].low, Math.abs(c[i].high - p), Math.abs(c[i].low - p)); }
    return s / n;
  }
  function donchian(c, n) {
    var u = [], l = [];
    for (var i = n - 1; i < c.length; i++) { var hi = -Infinity, lo = Infinity; for (var j = i - n + 1; j <= i; j++) { if (c[j].high > hi) hi = c[j].high; if (c[j].low < lo) lo = c[j].low; } u.push({ time: c[i].time, value: hi }); l.push({ time: c[i].time, value: lo }); }
    return { u: u, l: l };
  }
  async function carregaVelas() {
    if (!S || !S.chart) return;
    var ativo = S.ativo, tf = S.tf, meu = ++S.seqVelas, msg = $('op-chart-msg');
    try {
      var c = await A.api('/candles?ativo=' + encodeURIComponent(ativo) + '&tf=' + tf + '&limite=200');
      if (!S || meu !== S.seqVelas) return;
      S.c = c || [];
      if (S.c.length) { var pr = S.prec = F.pxCasas(S.c[S.c.length - 1].close); S.velas.applyOptions({ priceFormat: { type: 'price', precision: pr, minMove: Math.pow(10, -pr) } }); }
      S.velas.setData(S.c); S.velasEm = Date.now();
      msg.hidden = !!S.c.length; if (!S.c.length) msg.textContent = 'sem velas para ' + F.par(ativo) + ' em ' + tf;
      if (S.refit) { S.chart.timeScale().fitContent(); S.velas.priceScale().applyOptions({ autoScale: true }); S.refit = false; }
      cabecalho(); indicadores(); marcadores(); linhas();
    } catch (err) { if (S && meu === S.seqVelas) { msg.hidden = false; msg.textContent = 'não consegui ler o /candles (' + A.erroTxt(err) + ')'; } }
  }
  async function indicadores() {
    var on = S.ind, ativo = S.ativo, tf = S.tf;
    var vazio = function (ks) { ks.forEach(function (k) { S.ser[k].setData([]); }); };
    var d = on.don && S.c.length > 20 ? donchian(S.c, 20) : null;
    S.ser.donU.setData(d ? d.u : []); S.ser.donL.setData(d ? d.l : []);
    if (!on.ema && !on.bb && !S.sinalSel) { vazio(['ema20', 'ema50', 'bbU', 'bbM', 'bbL']); S.anal = null; analise(); return; }
    try {
      var a = await A.api('/analise?ativo=' + encodeURIComponent(ativo) + '&tf=' + tf);
      if (!S || S.ativo !== ativo || S.tf !== tf) return;
      S.anal = a;
      if (on.ema) { S.ser.ema20.setData(a.ema20 || []); S.ser.ema50.setData(a.ema50 || []); } else vazio(['ema20', 'ema50']);
      if (on.bb) { S.ser.bbU.setData(a.bb_up || []); S.ser.bbM.setData(a.bb_mid || []); S.ser.bbL.setData(a.bb_lo || []); } else vazio(['bbU', 'bbM', 'bbL']);
    } catch (err) { S.anal = null; }
    analise();
  }
  function linhas() {
    if (!S || !S.velas) return;
    S.plines.forEach(function (l) { try { S.velas.removePriceLine(l); } catch (e) {} }); S.plines = [];
    var e = S.estado || {}, T = tema(), add = function (o) { S.plines.push(S.velas.createPriceLine(Object.assign({ lineWidth: 1, axisLabelVisible: true }, o))); };
    (e.posicoes || []).filter(function (p) { return p.ativo === S.ativo; }).forEach(function (p) {
      add({ price: p.entrada, color: p.direcao === 'LONG' ? T.pos : T.neg, lineWidth: 2, lineStyle: 0, title: p.direcao + ' entrada' });
      if (p.stop) add({ price: p.stop, color: T.neg, lineStyle: 2, title: 'stop' });
    });
    (e.ordens || []).filter(function (o) { return o.ativo === S.ativo; }).forEach(function (o) { add({ price: o.preco_limite, color: T.acc, lineStyle: 1, title: 'ordem ' + o.direcao }); });
    var s = S.sinalSel && (e.pendentes || []).find(function (x) { return x.id === S.sinalSel; });
    if (s && s.ativo === S.ativo) { add({ price: s.preco, color: T.acc, lineStyle: 1, title: 'sinal ' + s.direcao }); add({ price: s.stop_sugerido, color: T.neg, lineStyle: 3, title: 'stop sugerido' }); }
    if (S.ind.liq && S.smart && S.smart.ativo === S.ativo) {
      (S.smart.j.liquidez_acima || []).forEach(function (p) { add({ price: p, color: T.warn, lineStyle: 3, title: 'liq ↑' }); });
      (S.smart.j.liquidez_abaixo || []).forEach(function (p) { add({ price: p, color: T.warn, lineStyle: 3, title: 'liq ↓' }); });
    }
    pe(e);
  }
  function marcadores() {
    if (!S || !S.velas) return;
    /* no celular o rótulo da seta ("LONG", "SHORT aberta") encavala com o vizinho e vira "LONGLONGLO":
       a seta e a cor já dizem o lado, então lá o texto sai */
    var e = S.estado || {}, T = tema(), seg = TF_SEG[S.tf] || 900, mk = [], estreito = $('op-chart').clientWidth < 560;
    var snap = function (dt) { var d = A.ts(dt); return d ? Math.floor(d.getTime() / 1000 / seg) * seg : null; };
    (e.trades || []).filter(function (t) { return t.ativo === S.ativo && t.aberto_em; }).forEach(function (t) { var tm = snap(t.aberto_em); if (tm) mk.push({ time: tm, position: t.direcao === 'LONG' ? 'belowBar' : 'aboveBar', color: t.direcao === 'LONG' ? T.pos : T.neg, shape: t.direcao === 'LONG' ? 'arrowUp' : 'arrowDown', text: estreito ? '' : t.direcao }); });
    (e.posicoes || []).filter(function (p) { return p.ativo === S.ativo && p.aberto_em; }).forEach(function (p) { var tm = snap(p.aberto_em); if (tm) mk.push({ time: tm, position: p.direcao === 'LONG' ? 'belowBar' : 'aboveBar', color: T.warn, shape: p.direcao === 'LONG' ? 'arrowUp' : 'arrowDown', text: estreito ? 'aberta' : p.direcao + ' aberta' }); });
    var t0 = S.c.length ? S.c[0].time : 0; mk = mk.filter(function (m) { return m.time >= t0; }).sort(function (a, b) { return a.time - b.time; });
    try { S.velas.setMarkers(mk); } catch (err) {}
  }
  function pe(e) {
    var ps = (e.posicoes || []).filter(function (p) { return p.ativo === S.ativo; }), h = [];
    ps.forEach(function (p) { h.push('<span>' + A.esc(p.direcao) + ' entrada <b>' + F.px(p.entrada) + '</b></span><span>stop <b class="neg">' + F.px(p.stop) + '</b>' + (p.stop_abertura != null && Math.abs(p.stop - p.stop_abertura) > 1e-12 ? ' · movido pelo trailing' : '') + '</span><span>P&amp;L <b class="' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '</b></span>'); });
    if (S.ind.liq && S.smart && S.smart.ativo === S.ativo && S.smart.j.funding_pct != null) h.push('<span>funding <b class="' + F.cls(S.smart.j.funding_pct) + '">' + F.pct(S.smart.j.funding_pct, 4) + '</b></span>');
    $('op-foot').innerHTML = h.join('') || '<span class="mute">sem posição neste par · linhas pontilhadas âmbar = zonas de liquidez do /smartmoney</span>';
  }
  function cabecalho() {
    if (!S) return;
    var px = S.precos[S.ativo] || (S.c.length ? S.c[S.c.length - 1].close : null);
    $('op-par').textContent = F.par(S.ativo); $('op-px').textContent = px ? F.px(px) : '—';
    var v = $('op-var');
    if (S.c.length > 1) { var ch = (S.c[S.c.length - 1].close / S.c[0].open - 1) * 100; v.className = 'mono ' + F.cls(ch); v.textContent = F.pct(ch) + ' nas ' + S.c.length + ' velas'; } else v.textContent = '';
    var at = atr(S.c, 14);
    $('op-sub').textContent = S.tf + ' · ' + S.c.length + ' velas' + (at ? ' · ATR(14) ' + F.px(at) + ' (' + F.f2(at / (px || 1) * 100) + '%)' : '') + ' · eixo em hora de São Paulo';
    Array.prototype.forEach.call($('op-tf').children, function (b) { b.setAttribute('aria-pressed', String(b.dataset.tf === S.tf)); });
  }
  function analise() {
    var el = $('op-anal'), e = S.estado || {}, s = S.sinalSel && (e.pendentes || []).find(function (x) { return x.id === S.sinalSel; });
    if (!s || s.ativo !== S.ativo || !S.anal) { el.innerHTML = ''; return; }
    var a = S.anal, sn = a.snapshot || {}, st = A.statusEntrada(s, S.precos[s.ativo] || sn.preco);
    el.innerHTML = '<div class="anal"><div class="sg-top"><b>Análise do sinal</b><span class="chip ' + (s.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(s.direcao) + '</span><span class="chip neutro">' + A.esc(s.tf) + ' · ' + A.esc(s.tipo || '') + '</span><span class="chip ' + st.cls + '">' + st.txt + '</span><button type="button" class="btn ghost sm" data-fecha-anal style="margin-left:auto">fechar</button></div>' +
      '<p>' + A.esc(F.decBR(a.leitura)) + '</p><div class="g"><div><span>RSI</span>' + (sn.rsi != null ? F.f1(+sn.rsi) : '—') + '</div><div><span>ADX</span>' + (sn.adx != null ? F.f1(+sn.adx) : '—') + '</div><div><span>EMA 20</span>' + F.px(sn.ema20) + '</div><div><span>EMA 50</span>' + F.px(sn.ema50) + '</div><div><span>Bollinger</span>' + F.px(sn.bb_lo) + '–' + F.px(sn.bb_up) + '</div></div>' +
      '<div class="sg-act" style="margin-top:10px"><button type="button" class="btn primary sm" data-conf="' + s.id + '">Confirmar com prévia de risco</button><button type="button" class="btn ghost sm" data-pular="' + s.id + '">Pular</button></div>' +
      (S.tf !== s.tf ? '<div class="mute" style="font-size:11px;margin-top:8px">O sinal nasceu no ' + A.esc(s.tf) + '; a leitura acima é do ' + S.tf + '.</div>' : '') + '</div>';
  }

  /* ---------- book e smart money ---------- */
  async function book() {
    if (!S) return; var ativo = S.ativo;
    try {
      var b = await A.api('/book?ativo=' + encodeURIComponent(ativo));
      if (!S || S.ativo !== ativo) return;
      if (!b) { $('op-book').innerHTML = '<div class="empty">Book indisponível para ' + A.esc(F.par(ativo)) + '.</div>'; return; }
      var lado = b.lado_grande === 'COMPRA' ? 'pos' : b.lado_grande === 'VENDA' ? 'neg' : '';
      var k = function (v) { return 'R$\u00a0' + F.f0((v || 0) / 1000) + 'k'; };
      $('op-book').innerHTML = '<div class="bk-row"><span>Pressão no book (±1%)</span><span><span class="pos">' + F.f1(b.pressao_compra) + '% compra</span> · <span class="neg">' + F.f1(100 - b.pressao_compra) + '% venda</span></span></div>' +
        '<div class="bk-bar" aria-hidden="true"><i style="width:' + Math.max(0, Math.min(100, b.pressao_compra)) + '%"></i><b></b></div>' +
        '<div class="bk-row"><span>Fluxo taker</span><span class="' + (b.fluxo_comprador >= 50 ? 'pos' : 'neg') + '">' + F.f1(b.fluxo_comprador) + '% comprando</span></div>' +
        '<div class="bk-row"><span>Dinheiro grande</span><span class="' + lado + '">' + A.esc(b.lado_grande) + ' <span class="txt2">(C ' + k(b.grande_compra) + ' · V ' + k(b.grande_venda) + ')</span></span></div>' +
        '<div class="bk-sep"></div>' +
        '<div class="bk-row"><span>Parede de compra</span><span>' + F.px(b.parede_compra && b.parede_compra.preco) + ' · ' + k(b.parede_compra && b.parede_compra.valor) + '</span></div>' +
        '<div class="bk-row"><span>Parede de venda</span><span>' + F.px(b.parede_venda && b.parede_venda.preco) + ' · ' + k(b.parede_venda && b.parede_venda.valor) + '</span></div>' +
        '<div class="bk-row"><span>Mid</span><span>' + F.px(b.mid) + '</span></div>' +
        (S.smart && S.smart.ativo === ativo && S.smart.j.leitura_funding ? '<div class="bk-sep"></div><div class="bk-note">' + A.esc(S.smart.j.leitura_funding) + '</div>' : '') +
        '<div class="bk-note">o /book entrega o resumo de ±1% em volta do mid, não os níveis um a um</div>';
      $('op-bk-t').textContent = 'resumo ±1% · ' + new Date().toLocaleTimeString('pt-BR');
    } catch (err) { if (S) $('op-book').innerHTML = '<div class="empty">Não consegui ler o /book (' + A.esc(A.erroTxt(err)) + ').</div>'; }
  }
  async function smart() {
    var ativo = S.ativo;
    try { var j = await A.api('/smartmoney?ativo=' + encodeURIComponent(ativo)); if (!S || S.ativo !== ativo) return; S.smart = { ativo: ativo, j: j || {} }; linhas(); } catch (err) {}
  }

  /* ---------- colunas da direita ---------- */
  function sinais(e) {
    if (!S || !e) return;
    var l = (e.pendentes || []).slice().sort(function (a, b) { return (b.ativo === S.ativo) - (a.ativo === S.ativo); });
    $('op-sg-n').textContent = l.length;
    $('op-sg').innerHTML = l.length ? l.map(function (s) {
      var st = A.statusEntrada(s, S.precos[s.ativo]), sd = s.preco ? Math.abs(s.preco - s.stop_sugerido) / s.preco * 100 : 0;
      return '<div class="sg-item' + (s.id === S.sinalSel ? ' is-on' : '') + '"><div class="sg-top"><span class="mono strong">' + A.esc(F.par(s.ativo)) + '</span><span class="chip ' + (s.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(s.direcao) + '</span><span class="chip neutro">' + A.esc(s.tf) + '</span><span class="t">há ' + A.idade(s.ts) + '</span></div>' +
        '<div class="sg-kv"><div><span>convicção</span>' + Math.round(s.conviccao) + '</div><div><span>entrada</span>' + F.px(s.preco) + '</div><div><span>stop</span><span class="neg" style="font-size:11.5px;letter-spacing:0;text-transform:none">' + F.px(s.stop_sugerido) + ' · ' + F.f2(sd) + '%</span></div></div>' +
        '<div><span class="chip ' + st.cls + '">' + st.txt + '</span></div>' +
        '<div class="sg-act"><button type="button" class="btn primary sm" data-conf="' + s.id + '">Confirmar</button><button type="button" class="btn ghost sm" data-pular="' + s.id + '">Pular</button><button type="button" class="btn ghost sm" data-ver="' + s.id + '">Ver no gráfico</button></div></div>';
    }).join('') : '<div class="empty">Nenhum sinal na fila agora.</div>';
  }
  function posicoes(e) {
    var l = (e.posicoes || []).slice().sort(function (a, b) { return (b.ativo === S.ativo) - (a.ativo === S.ativo); });
    var tot = l.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
    $('op-ps-n').innerHTML = l.length + (l.length ? ' · <span class="' + F.cls(tot) + '">' + F.money(tot) + '</span>' : '');
    $('op-ps').innerHTML = l.length ? l.map(function (p) {
      var roe = p.valor_reais ? p.pnl / p.valor_reais * 100 : 0, sd = S.saidas[p.id];
      return '<div class="ps-item' + (p.ativo === S.ativo ? ' is-on' : '') + '"><div class="ps-top"><button type="button" class="mono strong" data-par="' + A.esc(p.ativo) + '" style="background:none;border:0;color:inherit;padding:0;cursor:pointer;font:inherit">' + A.esc(F.par(p.ativo)) + '</button><span class="chip ' + (p.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(p.direcao) + '</span><span class="amt ' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '</span></div>' +
        '<div class="ps-meta"><span>' + A.esc(p.alavancagem) + 'x · ' + A.idade(p.aberto_em) + '</span><span class="' + F.cls(roe) + '">' + F.pct(roe) + ' ROE</span><span>entrada ' + F.px(p.entrada) + '</span><span>stop <span class="neg">' + F.px(p.stop) + '</span></span><span>margem ' + F.brl(p.valor_reais) + '</span></div>' +
        (sd && sd.acao ? '<div class="ps-saida">' + A.esc(sd.acao) + '</div>' : '') +
        '<div class="sg-act"><button type="button" class="btn danger sm" data-fechar="' + p.id + '">Fechar a mercado</button></div></div>';
    }).join('') : '<div class="empty">Nenhuma posição aberta.</div>';
  }
  function ordens(e) {
    var l = e.ordens || [];
    $('op-od-n').textContent = l.length + ' · post-only';
    $('op-od').innerHTML = l.length ? l.map(function (o) {
      var c = A.ts(o.criada_em), x = A.ts(o.expira_em), tot = c && x ? x - c : 0, pas = c ? Date.now() - c : 0, falta = x ? Math.max(0, Math.round((x - Date.now()) / 60000)) : null;
      return '<div class="ps-item"><div class="ps-top"><span class="mono strong">' + A.esc(F.par(o.ativo)) + '</span><span class="chip ' + (o.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(o.direcao) + '</span><span class="amt">' + F.px(o.preco_limite) + '</span></div>' +
        '<div class="prog" aria-hidden="true"><i style="--w:' + (tot ? Math.min(100, pas / tot * 100) : 0).toFixed(1) + '%"></i></div>' +
        '<div class="ps-meta"><span>descansa há ' + A.idade(o.criada_em) + '</span>' + (falta != null ? '<span>expira em ' + falta + ' min</span>' : '') + '<span>' + F.brl(o.valor_reais) + ' · ' + A.esc(o.alavancagem) + 'x</span></div>' +
        '<div class="ps-meta"><span class="mute">cancelar: em breve (o backend não tem rota para isso)</span></div></div>';
    }).join('') : '<div class="empty">Nenhuma ordem descansando.' + ((e.config || {}).exec_modo === 'post_only' ? '' : ' Execução atual: a mercado.') + '</div>';
  }
  function journal(e) {
    var l = (e.trades || []).filter(function (t) { return t.ativo === S.ativo; });
    $('op-jr-n').textContent = l.length + ' dos últimos ' + (e.trades || []).length;
    $('op-jr').innerHTML = l.length ? l.slice(0, 10).map(function (t) {
      return '<li><span class="w">' + A.ddmm(t.fechado_em) + ' ' + A.hhmm(t.fechado_em) + '</span><span><span class="chip ' + (t.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(t.direcao) + '</span> ' + F.px(t.entrada) + ' → ' + F.px(t.saida) + ' <span class="mute">' + A.esc(t.motivo_saida || '') + '</span></span><span class="' + F.cls(t.pnl_reais) + '">' + F.money(t.pnl_reais) + '</span></li>';
    }).join('') : '<li><span class="mute" style="font-family:var(--f-ui)">Nenhum trade fechado neste par entre os 30 mais recentes.</span></li>';
  }

  function trocaPar(a, tf) {
    if (!a) return;
    var mudou = a !== S.ativo || (tf && tf !== S.tf);
    S.ativo = a; if (tf) S.tf = tf;
    A.store.set('pulse.operar.par', a);
    if (!mudou) return;
    S.c = []; S.anal = null; S.smart = null; S.refit = true;
    $('op-book').innerHTML = '<div class="skel"></div><div class="skel"></div>';
    lista(); cabecalho(); carregaVelas(); book(); smart();
    if (S.estado) render(S.estado);
  }
  function render(e) {
    if (!S) return; var primeira = !S.estado; S.estado = e;
    if (primeira) {
      var l = pares(e), guard = A.store.get('pulse.operar.par'), hashPar = (location.hash.match(/[?&]par=([^&]+)/) || [])[1];
      try { hashPar = hashPar && decodeURIComponent(hashPar); } catch (err) { hashPar = null; }
      var ini = hashPar || ((e.pendentes || [])[0] || {}).ativo || ((e.posicoes || [])[0] || {}).ativo || (l.indexOf(guard) >= 0 ? guard : l[0]);
      lista(); precos(); trocaPar(ini || 'BTC/USDT');
      return;
    }
    lista(); sinais(e); posicoes(e); ordens(e); journal(e); linhas(); marcadores(); analise();
    if (Date.now() - (S.velasEm || 0) > 30000) carregaVelas();
  }
  async function saidas() {
    if (!S || !(S.estado && (S.estado.posicoes || []).length)) return;
    try { var l = await A.api('/saidas'); if (!S) return; S.saidas = {}; (l || []).forEach(function (s) { S.saidas[s.posicao_id] = s; }); posicoes(S.estado); } catch (e) {}
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.operar = {
    id: 'operar', titulo: 'Operar', html: html,
    init: function (root) {
      S = { root: root, estado: null, ativo: null, tf: A.store.get('pulse.operar.tf') || '1h', c: [], precos: {}, serie: {}, saidas: {}, plines: [], timers: [], offs: [], seqVelas: 0, ind: { ema: true, bb: false, don: false, liq: true }, sinalSel: null, refit: true };
      if (TFS.indexOf(S.tf) < 0) S.tf = '1h';
      var me = S;
      A.lib('lightweight-charts.standalone.production.js', 'LightweightCharts').then(function (ok) {
        if (S !== me) return;
        if (!ok) { $('op-chart-msg').textContent = 'a biblioteca do gráfico não carregou (web/vendor)'; return; }
        montaGrafico(); if (S.ativo) { S.refit = true; carregaVelas(); }
      });
      S.offs.push(A.on('estado', render), A.on('paleta', recolore));
      root.addEventListener('click', function (ev) {
        var t = ev.target.closest('button'); if (!t || !S) return;
        var e = S.estado || {}, acha = function (l, id) { return (l || []).find(function (x) { return String(x.id) === id; }); };
        if (t.dataset.par) trocaPar(t.dataset.par);
        else if (t.dataset.tf) { A.store.set('pulse.operar.tf', t.dataset.tf); trocaPar(S.ativo, t.dataset.tf); }
        else if (t.dataset.ind) { var k = t.dataset.ind; S.ind[k] = !S.ind[k]; t.setAttribute('aria-pressed', String(S.ind[k])); if (k === 'liq') { linhas(); } else indicadores(); }
        else if (t.dataset.ver) { var sv = acha(e.pendentes, t.dataset.ver); if (sv) { S.sinalSel = sv.id; trocaPar(sv.ativo, TFS.indexOf(sv.tf) >= 0 ? sv.tf : S.tf); indicadores(); linhas(); sinais(e); $('op-chart').scrollIntoView({ behavior: A.RM ? 'auto' : 'smooth', block: 'center' }); } }
        else if (t.hasAttribute('data-fecha-anal')) { S.sinalSel = null; analise(); linhas(); sinais(e); }
        else if (t.dataset.conf) { var s = acha(e.pendentes, t.dataset.conf); if (s) A.operarSinal(s); }
        else if (t.dataset.pular) { var s2 = acha(e.pendentes, t.dataset.pular); if (s2) A.pularSinal(s2); }
        else if (t.dataset.fechar) { var p = acha(e.posicoes, t.dataset.fechar); if (p) A.fecharPosicao(p); }
      });
      $('op-busca').addEventListener('input', function () { if (S) lista(); });
      S.timers.push(
        setInterval(function () { if (!document.hidden) precos(); }, 8000),
        setInterval(function () { if (!document.hidden) book(); }, 6000),
        setInterval(function () { if (!document.hidden) saidas(); }, 8000));
      if (A.estado) render(A.estado);
    },
    destroy: function () {
      if (!S) return;
      S.timers.forEach(clearInterval); S.offs.forEach(function (f) { f(); });
      if (S.ro) S.ro.disconnect();
      if (S.chart) { try { S.chart.remove(); } catch (e) {} }
      S = null;
    }
  };
})();
