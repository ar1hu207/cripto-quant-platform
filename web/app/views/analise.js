/* Apollux · view Análise (#analise): o segundo papel do produto, entender o ativo com o porquê à vista.

   Dado real, só com a view montada:
   - screener dos pares da config: preço (/precos, 15 s); variação 24 h, ATR% e tendência 1 h a partir do
     /candles 1h; tendência 1d do /candles 1d; funding do /funding. Duas leituras de /candles por par,
     4 de cada vez, na abertura, no botão "atualizar" e a cada 5 min. Convicção só aparece quando há
     sinal na fila: o motor pontua quando dispara, e uma nota inventada para par sem sinal seria número
     de mock;
   - painel do ativo: /analise (leitura e EMA/Bollinger do PRÓPRIO motor, paridade), /smartmoney, /book;
     Donchian 20 e RSI 14 calculados aqui sobre o /candles;
   - Mercado: /sentimento e /funding (60 s) + o mapa de calor das variações 24 h do screener.
   Fora do mock, declarado: dominância BTC e fluxo taker por par na tabela (nenhuma rota entrega em lote),
   notas do dono por ativo (não há tabela nem rota) e a Pítia (F7). */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt;
  var css = '<style>' +
  '.v-analise{display:grid;gap:18px;min-width:0}' +
  '.v-analise .flt{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}' +
  '.v-analise .flt input{background:var(--panel2);border:1px solid var(--line2);border-radius:10px;color:var(--txt);padding:7px 10px;font:inherit;font-size:12.5px;width:180px;max-width:100%}' +
  '.v-analise .flt input:focus{outline:none;border-color:var(--accent)}' +
  '.v-analise .flt button.f{border:1px solid var(--line2);background:none;color:var(--txt2);border-radius:999px;padding:4px 10px;font-family:var(--f-mono);font-size:11px;cursor:pointer}' +
  '.v-analise .flt button.f[aria-pressed="true"]{color:var(--accent);border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-analise .flt .fill{margin-left:auto;font-family:var(--f-mono);font-size:11px;color:var(--mute)}' +
  '.v-analise .tbl th button{background:none;border:0;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;cursor:pointer;padding:0}' +
  '.v-analise .tbl th button[aria-sort]{color:var(--accent)}' +
  '.v-analise .tbl tr.is-on td{background:rgba(var(--accent-rgb),.07)}' +
  '.v-analise .tbl .par b{display:block;font-family:var(--f-mono);font-size:12.5px} .v-analise .tbl .par span{font-family:var(--f-mono);font-size:10.5px;color:var(--mute)}' +
  '.v-analise .tbl tr.is-on .par b{color:var(--accent)}' +
  '.v-analise .cv{display:flex;align-items:center;gap:8px;min-width:110px} .v-analise .cv .bar{flex:1}' +
  '.v-analise .row-ch{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:start}' +
  '.v-analise .chart{position:relative;height:380px} .v-analise .chart-rsi{position:relative;height:110px;margin-top:6px}' +
  '.v-analise .chart-msg{position:absolute;inset:0;display:grid;place-items:center;font-family:var(--f-mono);font-size:12px;color:var(--mute);pointer-events:none}' +
  '.v-analise .ind{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}' +
  '.v-analise .ind button{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line2);background:none;color:var(--txt2);border-radius:8px;padding:4px 10px;font-family:var(--f-mono);font-size:11px;cursor:pointer}' +
  '.v-analise .ind button i{width:12px;height:2px;background:var(--c,var(--mute));opacity:.35}' +
  '.v-analise .ind button[aria-pressed="true"]{color:var(--txt);border-color:rgba(var(--accent-rgb),var(--glow))} .v-analise .ind button[aria-pressed="true"] i{opacity:1}' +
  '.v-analise .ind button:disabled{opacity:.45;cursor:not-allowed}' +
  '.v-analise .foot{font-family:var(--f-mono);font-size:11px;color:var(--mute);margin-top:8px}' +
  '.v-analise .at-head{display:flex;gap:12px;align-items:center}' +
  '.v-analise .at-par{font-family:var(--f-display);font-weight:800;font-size:22px}' +
  '.v-analise .at-px{font-family:var(--f-mono);font-size:13px;color:var(--txt2)}' +
  '.v-analise .sec{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin:16px 0 8px;border-top:1px solid var(--line);padding-top:12px}' +
  '.v-analise .why{list-style:none;margin:0;padding:0;display:grid;gap:8px}' +
  '.v-analise .why li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;font-size:12.5px;align-items:start}' +
  '.v-analise .why small{display:block;font-family:var(--f-mono);font-size:10.5px;color:var(--mute)}' +
  '.v-analise .leitura{font-size:12.5px;color:var(--txt2);line-height:1.55;margin:0}' +
  '.v-analise .sg{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--panel2);display:grid;gap:8px;margin-top:8px}' +
  '.v-analise .mk{display:grid;grid-template-columns:auto minmax(0,1fr) minmax(0,1.3fr);gap:18px;align-items:center}' +
  '.v-analise .fg{width:120px;height:120px;position:relative}' +
  '.v-analise .fg svg{width:100%;height:100%;transform:rotate(135deg)}' +
  '.v-analise .fg .b0{fill:none;stroke:rgba(var(--txt-rgb),.08);stroke-width:9;stroke-linecap:round}' +
  '.v-analise .fg .b1{fill:none;stroke:var(--accent);stroke-width:9;stroke-linecap:round}' +
  '.v-analise .fg div{position:absolute;inset:0;display:grid;place-items:center;text-align:center;font-family:var(--f-mono)}' +
  '.v-analise .fg b{display:block;font-size:26px} .v-analise .fg small{font-size:9.5px;letter-spacing:.1em;color:var(--mute);text-transform:uppercase}' +
  '.v-analise .mk-kv{display:grid;gap:8px;font-size:12.5px}' +
  '.v-analise .mk-kv div{display:flex;justify-content:space-between;gap:10px} .v-analise .mk-kv span:first-child{color:var(--txt2)} .v-analise .mk-kv span:last-child{font-family:var(--f-mono);text-align:right}' +
  '.v-analise .heat{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:4px}' +
  '.v-analise .heat button{border:0;border-radius:6px;padding:6px 2px;font-family:var(--f-mono);font-size:10.5px;color:var(--txt);cursor:pointer;line-height:1.3;background:rgba(var(--txt-rgb),.06)}' +
  '.v-analise .heat button b{display:block;font-size:11px}' +
  '.v-analise .heat-l{display:flex;gap:12px;font-family:var(--f-mono);font-size:10.5px;color:var(--mute);margin-top:8px;flex-wrap:wrap}' +
  '.v-analise .heat-l i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}' +
  '@media (max-width:1100px){.v-analise .row-ch{grid-template-columns:1fr}.v-analise .mk{grid-template-columns:auto minmax(0,1fr)}.v-analise .mk .heatw{grid-column:1/-1}}' +
  '@media (max-width:640px){.v-analise .chart{height:300px}.v-analise .mk{grid-template-columns:1fr;justify-items:stretch}.v-analise .fg{justify-self:center}.v-analise .heat{grid-template-columns:repeat(4,minmax(0,1fr))}.v-analise .flt .fill{margin-left:0;width:100%}}' +
  '</style>';

  var COLS = [['par', 'Par'], ['px', 'Preço', 1], ['ch', '24 h', 1], ['cv', 'Convicção'], ['atr', 'ATR% 1h', 1], ['t1', 'Tend. 1h'], ['td', 'Tend. 1d'], ['fu', 'Funding 8h', 1], ['', '']];
  var html = css + '<div class="v-analise">' +
    '<section class="card"><div class="card-head"><h2 class="h2">Screener</h2><span class="count" id="an-n">—</span></div>' +
      '<div class="flt"><input type="search" id="an-q" placeholder="filtrar par…" aria-label="Filtrar par"><button type="button" class="f" data-f="sinal" aria-pressed="false">com sinal na fila</button><button type="button" class="f" data-f="alinh" aria-pressed="false">tendência 1h = 1d</button><button type="button" class="f" data-f="fneg" aria-pressed="false">funding negativo</button>' +
      '<span class="fill" id="an-upd">—</span><button type="button" class="btn ghost sm" id="an-atu">atualizar</button></div>' +
      '<div class="tablewrap"><table class="tbl"><thead><tr>' + COLS.map(function (c) { return '<th' + (c[2] ? ' class="num"' : '') + '>' + (c[0] && c[0] !== 'par' ? '<button type="button" data-sort="' + c[0] + '">' + c[1] + '</button>' : c[1]) + '</th>'; }).join('') + '</tr></thead><tbody id="an-tb"><tr><td colspan="9"><div class="skel"></div></td></tr></tbody></table></div>' +
      '<div class="foot">24 h, ATR(14) e tendência (EMA 20 × 50) calculados aqui sobre o /candles da Binance Futures · convicção = nota do sinal na fila (sem sinal, o motor não pontua)</div></section>' +
    '<section class="row-ch">' +
      '<article class="card"><div class="card-head"><h2 class="h2">Gráfico <span class="mono txt2" style="font-size:12px;font-weight:400" id="an-ch-t"></span></h2><div class="seg" id="an-tf" role="group" aria-label="Tempo gráfico"><button type="button" data-tf="1h" aria-pressed="true">1h</button><button type="button" data-tf="4h" aria-pressed="false">4h</button><button type="button" data-tf="1d" aria-pressed="false">1d</button></div></div>' +
        '<div class="ind" id="an-ind"><button type="button" data-ind="ema" aria-pressed="true" style="--c:var(--accent)"><i></i>EMA 20/50</button><button type="button" data-ind="bb" aria-pressed="true" style="--c:var(--txt2)"><i></i>Bollinger</button><button type="button" data-ind="don" aria-pressed="false" style="--c:var(--info)"><i></i>Donchian 20</button><button type="button" data-ind="rsi" aria-pressed="true" style="--c:var(--warn)"><i></i>RSI 14</button><button type="button" disabled title="o /candles não traz volume"><i></i>volume · sem dado</button></div>' +
        '<div class="chart" id="an-chart"><div class="chart-msg" id="an-msg">carregando…</div></div><div class="chart-rsi" id="an-rsi"></div>' +
        '<div class="foot">EMA e Bollinger vêm do /analise, o mesmo cálculo do motor (indicadores.py): o que você vê é o que o Apollo vê. Donchian e RSI são calculados nesta tela.</div></article>' +
      '<aside class="card" id="an-at"><div class="skel"></div></aside>' +
    '</section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Mercado</h2><span class="count mute" id="an-mk-t">—</span></div><div class="mk" id="an-mk"><div class="skel"></div></div></section>' +
  '</div>';

  var S = null;
  function $(id) { return S && S.root.querySelector('#' + id); }
  function pares(e) { return String(((e || {}).config || {}).ativos || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean); }
  function ema(v, n) { var k = 2 / (n + 1), o = [], p = null; for (var i = 0; i < v.length; i++) { p = p == null ? v[i] : v[i] * k + p * (1 - k); o.push(p); } return o; }
  function tend(c) { if (!c || c.length < 55) return null; var cl = c.map(function (x) { return x.close; }), a = ema(cl, 20), b = ema(cl, 50), i = cl.length - 1, d = (a[i] - b[i]) / b[i]; return Math.abs(d) < 0.002 ? 'lateral' : d > 0 ? 'alta' : 'baixa'; }
  function atrPct(c, n) { if (!c || c.length < n + 1) return null; var s = 0; for (var i = c.length - n; i < c.length; i++) { var p = c[i - 1].close; s += Math.max(c[i].high - c[i].low, Math.abs(c[i].high - p), Math.abs(c[i].low - p)); } return s / n / c[c.length - 1].close * 100; }
  function rsiSerie(c, n) {
    var o = []; if (c.length <= n) return o; var g = 0, l = 0;
    for (var i = 1; i <= n; i++) { var d = c[i].close - c[i - 1].close; if (d > 0) g += d; else l -= d; }
    g /= n; l /= n; o.push({ time: c[n].time, value: l ? 100 - 100 / (1 + g / l) : 100 });
    for (var j = n + 1; j < c.length; j++) { var d2 = c[j].close - c[j - 1].close; g = (g * (n - 1) + Math.max(d2, 0)) / n; l = (l * (n - 1) + Math.max(-d2, 0)) / n; o.push({ time: c[j].time, value: l ? 100 - 100 / (1 + g / l) : 100 }); }
    return o;
  }
  function chipT(t) { return t ? '<span class="chip ' + (t === 'alta' ? 'long' : t === 'baixa' ? 'short' : 'neutro') + '">' + t + '</span>' : '<span class="mute">—</span>'; }

  /* ---------- screener ---------- */
  async function varre() {
    if (S.varrendo) return; S.varrendo = true;
    var l = pares(S.estado), i = 0, feito = 0, me = S;
    $('an-upd').textContent = 'lendo 0/' + l.length + '…';
    async function um(a) {
      try {
        var r = await Promise.all([A.api('/candles?ativo=' + encodeURIComponent(a) + '&tf=1h&limite=60'), A.api('/candles?ativo=' + encodeURIComponent(a) + '&tf=1d&limite=60')]);
        if (S !== me) return;
        var h = r[0] || [], d = r[1] || [], x = S.lin[a] || (S.lin[a] = {});
        if (h.length > 24) x.ch = (h[h.length - 1].close / h[h.length - 25].close - 1) * 100;
        x.atr = atrPct(h, 14); x.t1 = tend(h); x.td = tend(d); if (h.length) x.pxc = h[h.length - 1].close;
      } catch (err) {}
      feito++; if (S === me) $('an-upd').textContent = 'lendo ' + feito + '/' + l.length + '…';
    }
    async function worker() { while (S === me && i < l.length) await um(l[i++]); }
    await Promise.all([worker(), worker(), worker(), worker()]);
    if (S !== me) return;
    S.varrendo = false; S.varridoEm = new Date();
    $('an-upd').textContent = 'velas lidas às ' + S.varridoEm.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    tabela(); mercadoHeat();
  }
  async function precos() { var l = pares(S.estado); if (!l.length) return; try { var p = await A.api('/precos?ativos=' + encodeURIComponent(l.join(','))); if (!S) return; Object.keys(p || {}).forEach(function (k) { (S.lin[k] || (S.lin[k] = {})).px = p[k]; }); tabela(); } catch (e) {} }
  async function funding() { try { var f = await A.api('/funding'); if (!S) return; S.fund = f || []; (f || []).forEach(function (x) { (S.lin[x.ativo] || (S.lin[x.ativo] = {})).fu = x.funding_pct; }); tabela(); } catch (e) {} }
  function tabela() {
    var e = S.estado || {}, l = pares(e), q = ($('an-q').value || '').trim().toUpperCase(), sig = {};
    (e.pendentes || []).forEach(function (s) { if (!sig[s.ativo] || s.conviccao > sig[s.ativo].conviccao) sig[s.ativo] = s; });
    var rows = l.map(function (a) { var x = S.lin[a] || {}, s = sig[a]; return { a: a, px: x.px != null ? x.px : x.pxc, ch: x.ch, cv: s ? s.conviccao : null, s: s, atr: x.atr, t1: x.t1, td: x.td, fu: x.fu }; })
      .filter(function (r) { return (!q || F.par(r.a).indexOf(q) >= 0) && (!S.f.sinal || r.s) && (!S.f.alinh || (r.t1 && r.t1 === r.td && r.t1 !== 'lateral')) && (!S.f.fneg || r.fu < 0); });
    var k = S.sort, dir = S.dir;
    rows.sort(function (x, y) { var a = x[k], b = y[k]; if (k === 't1' || k === 'td') { a = a || ''; b = b || ''; return dir * (a < b ? -1 : a > b ? 1 : 0); } a = a == null ? -Infinity : a; b = b == null ? -Infinity : b; return dir * (b - a); });
    $('an-n').textContent = rows.length + ' de ' + l.length + ' pares';
    Array.prototype.forEach.call(S.root.querySelectorAll('[data-sort]'), function (b) { if (b.dataset.sort === k) b.setAttribute('aria-sort', dir > 0 ? 'descending' : 'ascending'); else b.removeAttribute('aria-sort'); });
    $('an-tb').innerHTML = rows.map(function (r) {
      return '<tr class="' + (r.a === S.ativo ? 'is-on' : '') + '"><td class="par"><b>' + A.esc(F.par(r.a)) + '</b><span>' + A.esc(r.a) + '</span></td><td class="mono num">' + (r.px != null ? F.px(r.px) : '—') + '</td>' +
        '<td class="mono num ' + F.cls(r.ch) + '">' + (r.ch != null ? F.pct(r.ch, 1) : '—') + '</td>' +
        '<td>' + (r.s ? '<div class="cv"><span class="mono">' + Math.round(r.cv) + '</span><div class="bar"><i style="--w:' + Math.round(r.cv) + '%"></i></div><span class="chip ' + (r.s.direcao === 'LONG' ? 'long' : 'short') + '">' + r.s.direcao + '</span></div>' : '<span class="mute">sem sinal</span>') + '</td>' +
        '<td class="mono num">' + (r.atr != null ? F.f2(r.atr) + '%' : '—') + '</td><td>' + chipT(r.t1) + '</td><td>' + chipT(r.td) + '</td>' +
        '<td class="mono num ' + (r.fu < 0 ? 'neg' : '') + '">' + (r.fu != null ? F.pct(r.fu, 4) : '—') + '</td><td><button type="button" class="btn ghost sm" data-ver="' + A.esc(r.a) + '">ver</button></td></tr>';
    }).join('') || '<tr><td colspan="9" class="mute">Nenhum par passa nesses filtros.</td></tr>';
  }

  /* ---------- gráfico + RSI ---------- */
  function tema() { return { txt: A.cor('mute'), line: A.rgba('line', .55), pos: A.cor('pos'), neg: A.cor('neg'), acc: A.cor('accent'), warn: A.cor('warn'), info: A.cor('info'), txt2: A.cor('txt2') }; }
  function opts(el, T, h) { return { width: el.clientWidth || 600, height: h, layout: { background: { color: 'transparent' }, textColor: T.txt, fontFamily: 'Fira Code, monospace', fontSize: 11 }, grid: { vertLines: { color: T.line }, horzLines: { color: T.line } }, timeScale: { timeVisible: true, borderColor: T.line }, rightPriceScale: { borderColor: T.line, minimumWidth: 72 } }; }
  function monta() {
    var el = $('an-chart'), er = $('an-rsi'), T = tema();
    S.ch = LightweightCharts.createChart(el, opts(el, T, el.clientHeight || 380));
    S.v = S.ch.addCandlestickSeries({ upColor: T.pos, downColor: T.neg, borderVisible: false, wickUpColor: T.pos, wickDownColor: T.neg });
    var ln = function (c, w, st) { return S.ch.addLineSeries({ color: c, lineWidth: w, lineStyle: st || 0, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }); };
    S.ser = { e20: ln(T.acc, 2), e50: ln(T.warn, 2), bu: ln(T.txt2, 1), bm: ln(T.txt2, 1, 2), bl: ln(T.txt2, 1), du: ln(T.info, 1, 1), dl: ln(T.info, 1, 1) };
    S.chR = LightweightCharts.createChart(er, Object.assign(opts(er, T, er.clientHeight || 110), { timeScale: { visible: false, borderColor: T.line } }));
    S.rsi = S.chR.addLineSeries({ color: T.warn, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
    [70, 30].forEach(function (v) { S.rsi.createPriceLine({ price: v, color: T.txt2, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }); });
    S.ch.timeScale().subscribeVisibleLogicalRangeChange(function (r) { if (r && S && S.chR) S.chR.timeScale().setVisibleLogicalRange(r); });
    S.ro = new ResizeObserver(function () { if (!S) return; if (S.ch && el.clientWidth) S.ch.applyOptions({ width: el.clientWidth }); if (S.chR && er.clientWidth) S.chR.applyOptions({ width: er.clientWidth }); });
    S.ro.observe(el);
  }
  function recolore() {
    if (!S || !S.ch) return; var T = tema(), g = { layout: { textColor: T.txt }, grid: { vertLines: { color: T.line }, horzLines: { color: T.line } } };
    S.ch.applyOptions(g); S.chR.applyOptions(g);
    S.v.applyOptions({ upColor: T.pos, downColor: T.neg, wickUpColor: T.pos, wickDownColor: T.neg });
    S.ser.e20.applyOptions({ color: T.acc }); S.ser.e50.applyOptions({ color: T.warn }); ['bu', 'bm', 'bl'].forEach(function (k) { S.ser[k].applyOptions({ color: T.txt2 }); });
    ['du', 'dl'].forEach(function (k) { S.ser[k].applyOptions({ color: T.info }); }); S.rsi.applyOptions({ color: T.warn });
  }
  async function grafico() {
    if (!S.ch) return;
    var a = S.ativo, tf = S.tf, meu = ++S.seq;
    $('an-ch-t').textContent = F.par(a) + ' · ' + tf;
    try {
      var r = await Promise.all([A.api('/candles?ativo=' + encodeURIComponent(a) + '&tf=' + tf + '&limite=200'), A.api('/analise?ativo=' + encodeURIComponent(a) + '&tf=' + tf).catch(function () { return null; })]);
      if (!S || meu !== S.seq) return;
      var c = r[0] || [], an = r[1]; S.c = c; S.an = an;
      $('an-msg').hidden = !!c.length; if (!c.length) $('an-msg').textContent = 'sem velas';
      if (c.length) { var u = Math.abs(c[c.length - 1].close) || 1, pr = u >= 1000 ? 2 : u >= 10 ? 3 : u >= 1 ? 4 : u >= 0.01 ? 5 : 7; S.v.applyOptions({ priceFormat: { type: 'price', precision: pr, minMove: Math.pow(10, -pr) } }); }
      S.v.setData(c); camadas(); S.ch.timeScale().fitContent(); painel();
    } catch (err) { if (S && meu === S.seq) { $('an-msg').hidden = false; $('an-msg').textContent = 'não consegui ler o /candles (' + A.erroTxt(err) + ')'; } }
  }
  function camadas() {
    var an = S.an || {}, c = S.c || [], i = S.ind;
    S.ser.e20.setData(i.ema && an.ema20 ? an.ema20 : []); S.ser.e50.setData(i.ema && an.ema50 ? an.ema50 : []);
    S.ser.bu.setData(i.bb && an.bb_up ? an.bb_up : []); S.ser.bm.setData(i.bb && an.bb_mid ? an.bb_mid : []); S.ser.bl.setData(i.bb && an.bb_lo ? an.bb_lo : []);
    var u = [], l = [];
    if (i.don) for (var k = 19; k < c.length; k++) { var hi = -Infinity, lo = Infinity; for (var j = k - 19; j <= k; j++) { hi = Math.max(hi, c[j].high); lo = Math.min(lo, c[j].low); } u.push({ time: c[k].time, value: hi }); l.push({ time: c[k].time, value: lo }); }
    S.ser.du.setData(u); S.ser.dl.setData(l);
    $('an-rsi').hidden = !i.rsi; S.rsi.setData(i.rsi ? rsiSerie(c, 14) : []);
    if (i.rsi && S.chR) { S.chR.applyOptions({ width: $('an-rsi').clientWidth }); var r = S.ch.timeScale().getVisibleLogicalRange(); if (r) S.chR.timeScale().setVisibleLogicalRange(r); }
  }

  /* ---------- painel do ativo ---------- */
  async function extras() {
    var a = S.ativo;
    var r = await Promise.all([A.api('/smartmoney?ativo=' + encodeURIComponent(a)).catch(function () { return null; }), A.api('/book?ativo=' + encodeURIComponent(a)).catch(function () { return null; })]);
    if (!S || S.ativo !== a) return; S.sm = r[0]; S.bk = r[1]; painel();
  }
  function painel() {
    var e = S.estado || {}, a = S.ativo, an = S.an || {}, sn = an.snapshot || {}, x = S.lin[a] || {};
    var sig = (e.pendentes || []).filter(function (s) { return s.ativo === a; }), pos = (e.posicoes || []).filter(function (p) { return p.ativo === a; });
    var s0 = sig[0], cv = s0 ? Math.round(s0.conviccao) : null, C = 2 * Math.PI * 22;
    var px = x.px != null ? x.px : sn.preco;
    var h = '<div class="at-head"><div class="fg" style="width:64px;height:64px"><svg viewBox="0 0 56 56" aria-hidden="true"><circle class="b0" cx="28" cy="28" r="22" stroke-dasharray="' + (C * .75).toFixed(1) + ' ' + C.toFixed(1) + '" style="stroke-width:5"/>' + (cv != null ? '<circle class="b1" cx="28" cy="28" r="22" stroke-dasharray="' + (C * .75 * cv / 100).toFixed(1) + ' ' + C.toFixed(1) + '" style="stroke-width:5"/>' : '') + '</svg><div><b style="font-size:16px">' + (cv != null ? cv : '—') + '</b></div></div>' +
      '<div><div class="at-par">' + A.esc(F.par(a)) + '</div><div class="at-px">' + (px != null ? F.px(px) : '—') + (x.ch != null ? ' <span class="' + F.cls(x.ch) + '">' + F.pct(x.ch, 1) + ' 24 h</span>' : '') + '</div></div></div>' +
      '<div class="mute" style="font-size:11px;margin-top:6px">' + (cv != null ? 'convicção do sinal na fila' : 'sem sinal na fila: o motor não pontua este par agora') + '</div>';
    h += '<div class="sec">por quê · leitura do motor no ' + A.esc(S.tf) + '</div>';
    if (an.leitura) h += '<p class="leitura">' + A.esc(an.leitura) + '</p>';
    var it = [];
    if (sn.ema20 != null) it.push(['EMA 20 ' + (sn.ema20 > sn.ema50 ? '>' : '<') + ' EMA 50', F.px(sn.ema20) + ' / ' + F.px(sn.ema50), sn.ema20 > sn.ema50 ? 'long' : 'short', sn.ema20 > sn.ema50 ? 'alta' : 'baixa']);
    if (sn.adx != null) it.push(['ADX ' + sn.adx, sn.adx >= (+((e.config || {}).adx_min) || 25) ? 'acima do portão (' + ((e.config || {}).adx_min) + ')' : 'abaixo do portão (' + ((e.config || {}).adx_min) + ')', sn.adx >= (+((e.config || {}).adx_min) || 25) ? 'info' : 'neutro', sn.adx >= (+((e.config || {}).adx_min) || 25) ? 'tendência' : 'fraca']);
    if (sn.rsi != null) it.push(['RSI ' + sn.rsi, sn.rsi > 70 ? 'sobrecomprado' : sn.rsi < 30 ? 'sobrevendido' : 'zona neutra', sn.rsi > 70 || sn.rsi < 30 ? 'warn' : 'neutro', sn.rsi > 70 ? 'alto' : sn.rsi < 30 ? 'baixo' : 'neutro']);
    if (S.bk) it.push(['Fluxo taker ' + F.f0(S.bk.fluxo_comprador) + '% comprador', 'book ±1%: ' + F.f0(S.bk.pressao_compra) + '% compra · grande: ' + S.bk.lado_grande, S.bk.fluxo_comprador >= 50 ? 'long' : 'short', S.bk.fluxo_comprador >= 50 ? 'compra' : 'venda']);
    if (S.sm && S.sm.funding_pct != null) it.push(['Funding ' + F.pct(S.sm.funding_pct, 4), S.sm.leitura_funding || '', S.sm.funding_pct < 0 ? 'short' : 'neutro', S.sm.funding_pct < 0 ? 'negativo' : 'positivo']);
    if (x.td) it.push(['Tendência 1d ' + x.td, x.t1 ? (x.t1 === x.td ? 'alinhada com o 1h' : '1h em ' + x.t1) : '', x.td === 'alta' ? 'long' : x.td === 'baixa' ? 'short' : 'neutro', x.td]);
    h += it.length ? '<ul class="why">' + it.map(function (w) { return '<li><span>' + A.esc(w[0]) + '<small>' + A.esc(w[1]) + '</small></span><span class="chip ' + w[2] + '">' + A.esc(w[3]) + '</span></li>'; }).join('') + '</ul>' : '<div class="skel"></div>';
    if (S.sm && ((S.sm.liquidez_acima || []).length || (S.sm.liquidez_abaixo || []).length)) h += '<div class="mute" style="font-size:11px;margin-top:8px;font-family:var(--f-mono)">liquidez acima ' + (S.sm.liquidez_acima || []).map(F.px).join(' · ') + '<br>liquidez abaixo ' + (S.sm.liquidez_abaixo || []).map(F.px).join(' · ') + '</div>';
    h += '<div class="sec">posição e sinal</div>';
    h += pos.length ? pos.map(function (p) { return '<div class="sg"><div style="display:flex;gap:8px;align-items:center"><span class="chip ' + (p.direcao === 'LONG' ? 'long' : 'short') + '">' + p.direcao + '</span><span class="mono">' + p.alavancagem + 'x · entrada ' + F.px(p.entrada) + '</span><span class="mono ' + F.cls(p.pnl) + '" style="margin-left:auto">' + F.money(p.pnl) + '</span></div><div><button type="button" class="btn danger sm" data-fechar="' + p.id + '">Fechar</button> <a class="btn ghost sm" href="#operar?par=' + encodeURIComponent(a) + '">abrir no Operar</a></div></div>'; }).join('') : '<div class="mute" style="font-size:12.5px">Nenhuma posição aberta neste par.</div>';
    h += sig.map(function (s) { var st = A.statusEntrada(s, px); return '<div class="sg"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="chip ' + (s.direcao === 'LONG' ? 'long' : 'short') + '">' + s.direcao + '</span><span class="mono">conv. ' + Math.round(s.conviccao) + ' · ' + A.esc(s.tf) + '</span><span class="mono mute" style="margin-left:auto">há ' + A.idade(s.ts) + '</span></div><div style="font-size:12px;color:var(--txt2)">' + A.esc((s.motivos || '').split(', ').slice(0, 3).join(' · ')) + '</div><span class="chip ' + st.cls + '" style="justify-self:start">' + st.txt + '</span><div><button type="button" class="btn primary sm" data-conf="' + s.id + '">Confirmar</button> <button type="button" class="btn ghost sm" data-pular="' + s.id + '">Pular</button></div></div>'; }).join('');
    h += '<div class="sec">notas do dono</div><div class="mute" style="font-size:12px">Notas por ativo: <span class="soon">em breve</span> (o backend ainda não tem onde guardar).</div>';
    h += '<div class="sec">Pítia</div><div class="mute" style="font-size:12px">O oráculo de análise (nome proposto) lê tokenomics, notícias e o gráfico e responde com a fonte. <span class="soon">em breve · F7</span></div>';
    $('an-at').innerHTML = h;
  }

  /* ---------- mercado ---------- */
  async function mercado() {
    var s = null; try { s = await A.api('/sentimento'); } catch (e) {}
    if (!S) return; S.sent = s; await funding(); if (!S) return; mercadoHeat();
    $('an-mk-t').textContent = 'às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  function mercadoHeat() {
    var s = S.sent, fu = S.fund || [], C = 2 * Math.PI * 50, fg = s && s.fear_greed;
    var g = '<div class="fg"><svg viewBox="0 0 120 120" aria-hidden="true"><circle class="b0" cx="60" cy="60" r="50" stroke-dasharray="' + (C * .75).toFixed(1) + ' ' + C.toFixed(1) + '"/>' + (fg ? '<circle class="b1" cx="60" cy="60" r="50" stroke-dasharray="' + (C * .75 * fg.valor / 100).toFixed(1) + ' ' + C.toFixed(1) + '"/>' : '') + '</svg><div><span><b>' + (fg ? fg.valor : '—') + '</b><small>fear &amp; greed</small></span></div></div>';
    var kv = '<div class="mk-kv">' + (fg ? '<div><span>Regime</span><span>' + A.esc(fg.label) + '</span></div>' : '<div><span>Fear &amp; Greed</span><span>indisponível</span></div>');
    if (s && s.breadth) kv += '<div><span>Breadth</span><span>' + s.breadth.pct_subindo + '% das ' + s.breadth.n + ' subindo</span></div><div><span>Variação média hoje</span><span class="' + F.cls(s.breadth.variacao_media) + '">' + F.pct(s.breadth.variacao_media) + '</span></div>';
    if (fu.length) { var med = fu.reduce(function (a, x) { return a + (x.funding_pct || 0); }, 0) / fu.length, neg = fu.slice().sort(function (a, b) { return a.funding_pct - b.funding_pct; }).slice(0, 2); kv += '<div><span>Funding médio</span><span>' + F.pct(med, 4) + ' / 8h</span></div><div><span>Mais negativo</span><span>' + neg.map(function (x) { return A.esc(F.base(x.ativo)) + ' ' + F.pct(x.funding_pct, 4); }).join(' · ') + '</span></div>'; }
    var e = S.estado || {}; kv += '<div><span>Sinais na fila</span><span>' + (e.pendentes || []).length + '</span></div><div><span>Dominância BTC</span><span class="mute">sem rota</span></div></div>';
    var l = pares(e).map(function (a) { return { a: a, ch: (S.lin[a] || {}).ch }; }).filter(function (x) { return x.ch != null; }).sort(function (a, b) { return b.ch - a.ch; });
    var mx = Math.max.apply(null, l.map(function (x) { return Math.abs(x.ch); }).concat([1]));
    var heat = '<div class="heatw">' + (l.length ? '<div class="heat">' + l.map(function (x) { var t = Math.min(1, Math.abs(x.ch) / mx), c = Math.abs(x.ch) < .3 ? 'rgba(var(--txt-rgb),.07)' : 'rgba(var(--' + (x.ch > 0 ? 'pos' : 'neg') + '-rgb),' + (.18 + t * .6).toFixed(2) + ')'; return '<button type="button" data-ver="' + A.esc(x.a) + '" style="background:' + c + '"><b>' + A.esc(F.base(x.a)) + '</b>' + F.pct(x.ch, 1) + '</button>'; }).join('') + '</div><div class="heat-l"><span><i style="background:rgba(var(--neg-rgb),.7)"></i>queda</span><span><i style="background:rgba(var(--txt-rgb),.07)"></i>estável</span><span><i style="background:rgba(var(--pos-rgb),.7)"></i>alta</span><span>24 h · toque para ver</span></div>' : '<div class="skel"></div><div class="mute" style="font-size:11px">o mapa aparece quando o screener terminar de ler as velas</div>') + '</div>';
    $('an-mk').innerHTML = g + kv + heat;
  }

  function seleciona(a) {
    if (!a || a === S.ativo) return; S.ativo = a; S.sm = null; S.bk = null; A.store.set('pulse.analise.par', a);
    tabela(); painel(); grafico(); extras();
    if (window.innerWidth < 1100) $('an-chart').scrollIntoView({ behavior: A.RM ? 'auto' : 'smooth', block: 'start' });
  }
  function render(e) {
    if (!S) return; var primeira = !S.estado; S.estado = e;
    if (primeira) {
      var l = pares(e), g = A.store.get('pulse.analise.par');
      S.ativo = ((e.pendentes || [])[0] || {}).ativo || (l.indexOf(g) >= 0 ? g : l[0]) || 'BTC/USDT';
      tabela(); painel(); grafico(); extras(); precos(); varre(); mercado();
      return;
    }
    tabela(); painel();
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.analise = {
    id: 'analise', titulo: 'Análise', html: html,
    init: function (root) {
      S = { root: root, estado: null, lin: {}, f: {}, sort: 'cv', dir: 1, tf: '1h', ind: { ema: true, bb: true, don: false, rsi: true }, timers: [], offs: [], seq: 0, c: [] };
      var me = S;
      A.lib('lightweight-charts.standalone.production.js', 'LightweightCharts').then(function (ok) { if (S !== me) return; if (!ok) { $('an-msg').textContent = 'a biblioteca do gráfico não carregou (web/vendor)'; return; } monta(); if (S.ativo) grafico(); });
      S.offs.push(A.on('estado', render), A.on('paleta', recolore));
      root.addEventListener('click', function (ev) {
        var t = ev.target.closest('button'); if (!t || !S) return;
        var e = S.estado || {}, acha = function (l, id) { return (l || []).find(function (x) { return String(x.id) === id; }); };
        if (t.dataset.ver) seleciona(t.dataset.ver);
        else if (t.dataset.sort) { if (S.sort === t.dataset.sort) S.dir = -S.dir; else { S.sort = t.dataset.sort; S.dir = 1; } tabela(); }
        else if (t.dataset.f) { S.f[t.dataset.f] = !S.f[t.dataset.f]; t.setAttribute('aria-pressed', String(!!S.f[t.dataset.f])); tabela(); }
        else if (t.id === 'an-atu') { varre(); precos(); }
        else if (t.dataset.tf) { S.tf = t.dataset.tf; Array.prototype.forEach.call($('an-tf').children, function (b) { b.setAttribute('aria-pressed', String(b === t)); }); grafico(); }
        else if (t.dataset.ind) { var k = t.dataset.ind; S.ind[k] = !S.ind[k]; t.setAttribute('aria-pressed', String(S.ind[k])); if (S.ch) camadas(); }
        else if (t.dataset.conf) { var s = acha(e.pendentes, t.dataset.conf); if (s) A.operarSinal(s); }
        else if (t.dataset.pular) { var s2 = acha(e.pendentes, t.dataset.pular); if (s2) A.pularSinal(s2); }
        else if (t.dataset.fechar) { var p = acha(e.posicoes, t.dataset.fechar); if (p) A.fecharPosicao(p); }
      });
      root.addEventListener('click', function (ev) { var tr = ev.target.closest('tbody tr'); if (tr && !ev.target.closest('button') && S) { var b = tr.querySelector('[data-ver]'); if (b) seleciona(b.dataset.ver); } });
      $('an-q').addEventListener('input', function () { if (S) tabela(); });
      S.timers.push(setInterval(function () { if (!document.hidden) precos(); }, 15000), setInterval(function () { if (!document.hidden) mercado(); }, 60000), setInterval(function () { if (!document.hidden) varre(); }, 300000));
      if (A.estado) render(A.estado);
    },
    destroy: function () {
      if (!S) return;
      S.timers.forEach(clearInterval); S.offs.forEach(function (f) { f(); });
      if (S.ro) S.ro.disconnect();
      [S.ch, S.chR].forEach(function (c) { if (c) { try { c.remove(); } catch (e) {} } });
      S = null;
    }
  };
})();
