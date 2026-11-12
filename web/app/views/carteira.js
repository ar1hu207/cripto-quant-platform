/* Apollux · view Carteira (#carteira): a carteira é o objeto, não o trade.

   Dado real, só com a view montada: /estado (posições, DCA, banca, métricas, curva) · /candles 1h dos
   pares com posição + BTC (correlação de 30 dias e a régua B&H BTC da curva, ao abrir e a cada 10 min) ·
   /trades?limite=500 (histórico mensal, 5 min) · /dca, /dca/aportar, /dca/remover.
   Fora do mock, declarado: a conta que NÃO está selecionada aparece sem número (cada conta é um backend;
   ler a outra seria mais um poll), a conta Real é esteira sem número, e as bolhas de ações BR do mock
   (eram exemplo) saíram: entram com a B3 (F8). O DD por mês do mock não tem fonte por mês: sai. */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt;
  var css = '<style>' +
  '.v-carteira{display:grid;gap:18px;min-width:0}' +
  '.v-carteira .mapa{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:18px;align-items:center}' +
  '.v-carteira .bolhas{position:relative;height:380px;border-radius:12px;overflow:hidden;touch-action:none}' +
  '.v-carteira .bo{position:absolute;border-radius:50%;display:grid;place-items:center;text-align:center;cursor:grab;user-select:none;transform:translate(-50%,-50%);' +
    'background:radial-gradient(circle at 32% 28%,rgba(var(--txt-rgb),.55),rgba(var(--accent-rgb),.85) 38%,rgba(var(--accent-rgb),.35) 75%,rgba(var(--bg-rgb),.6));box-shadow:0 0 24px rgba(var(--accent-rgb),var(--glow-lo)),inset 0 -8px 18px rgba(var(--bg-rgb),.45);border:2px solid rgba(var(--accent-rgb),.6)}' +
  '.v-carteira .bo.pos{border-color:var(--pos)} .v-carteira .bo.neg{border-color:var(--neg)}' +
  '.v-carteira .bo.livre{background:repeating-linear-gradient(135deg,rgba(var(--txt-rgb),.08) 0 6px,rgba(var(--txt-rgb),.03) 6px 12px);border:1px dashed var(--line2);box-shadow:none}' +
  '.v-carteira .bo.dca{background:radial-gradient(circle at 32% 28%,rgba(var(--txt-rgb),.45),rgba(var(--warn-rgb),.75) 40%,rgba(var(--warn-rgb),.25) 80%);border-color:rgba(var(--warn-rgb),.7);box-shadow:0 0 18px rgba(var(--warn-rgb),.2)}' +
  '.v-carteira .bo b{display:block;font-family:var(--f-display);font-weight:800;font-size:var(--fs,14px);color:var(--txt);text-shadow:0 1px 4px rgba(var(--bg-rgb),.8);line-height:1.05}' +
  '.v-carteira .bo span{font-family:var(--f-mono);font-size:10px;color:var(--txt);opacity:.85}' +
  '.v-carteira .bo:active{cursor:grabbing}' +
  '.v-carteira .mapa-v{position:absolute;inset:0;display:grid;place-items:center;font-size:12.5px;color:var(--txt2);text-align:center;padding:20px}' +
  '.v-carteira .ct-lado{display:grid;gap:12px}' +
  '.v-carteira .box{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--panel2)}' +
  '.v-carteira .box.dash{border-style:dashed;background:none}' +
  '.v-carteira .box .k{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}' +
  '.v-carteira .box .v{font-family:var(--f-mono);font-size:20px;font-weight:600;margin:4px 0}' +
  '.v-carteira .box .s{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);line-height:1.55}' +
  '.v-carteira .ct-contas{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}' +
  '.v-carteira .ct-conta.is-on{border-color:rgba(var(--accent-rgb),var(--glow));box-shadow:0 0 0 1px rgba(var(--accent-rgb),var(--glow-lo))}' +
  '.v-carteira .ct-conta .v{font-family:var(--f-mono);font-size:26px;font-weight:600;margin:6px 0}' +
  '.v-carteira .ct-conta .v .cur{font-size:13px;color:var(--txt2);margin-right:2px}' +
  '.v-carteira .ct-conta .s{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);line-height:1.6}' +
  '.v-carteira .esteira{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-family:var(--f-mono);font-size:11px;margin:8px 0}' +
  '.v-carteira .esteira span{border:1px solid var(--line2);border-radius:6px;padding:2px 7px;color:var(--txt2)}' +
  '.v-carteira .aloc{display:flex;flex-wrap:wrap;gap:18px;align-items:center}.v-carteira .aloc .leg{flex:1 1 240px;min-width:0}' +
  '.v-carteira .donut{width:150px;height:150px;position:relative;flex:none}' +
  '.v-carteira .donut svg{width:100%;height:100%;transform:rotate(-90deg)}' +
  '.v-carteira .donut div{position:absolute;inset:0;display:grid;place-items:center;text-align:center;font-family:var(--f-mono)}' +
  '.v-carteira .donut b{display:block;font-size:22px} .v-carteira .donut small{font-size:9.5px;letter-spacing:.1em;color:var(--mute);text-transform:uppercase}' +
  '.v-carteira .leg{list-style:none;margin:0;padding:0;display:grid;gap:7px;font-size:12.5px}' +
  '.v-carteira .leg li{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:8px;align-items:center}' +
  '.v-carteira .leg i{width:10px;height:10px;border-radius:3px;display:block}' +
  '.v-carteira .leg .m{font-family:var(--f-mono);font-size:12px;text-align:right}' +
  '.v-carteira .exp{display:grid;gap:10px;margin-top:14px;border-top:1px solid var(--line);padding-top:12px}' +
  '.v-carteira .exp div{display:grid;grid-template-columns:130px minmax(0,1fr) auto;gap:10px;align-items:center;font-family:var(--f-mono);font-size:11.5px}' +
  '.v-carteira .exp span:first-child{color:var(--mute);letter-spacing:.06em;text-transform:uppercase;font-size:10.5px}' +
  '.v-carteira .exp .bar i{background:var(--c,var(--accent))}' +
  '.v-carteira .corr{display:grid;gap:4px;font-family:var(--f-mono);font-size:11.5px}' +
  '.v-carteira .corr .c{border-radius:6px;padding:9px 4px;text-align:center}' +
  '.v-carteira .corr .h{color:var(--mute);font-size:10.5px;text-align:center;align-self:center}' +
  '.v-carteira .nota{border-left:3px solid var(--warn);background:var(--panel2);border-radius:0 10px 10px 0;padding:10px 12px;font-size:12px;color:var(--txt2);margin-top:12px;line-height:1.55}' +
  '.v-carteira .chart{display:block;width:100%;height:240px;overflow:visible}' +
  '.v-carteira .chart .g{stroke:rgba(var(--txt-rgb),.07)} .v-carteira .chart .ax{fill:var(--mute);font-family:var(--f-mono);font-size:10px}' +
  '.v-carteira .chart .eq{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round}' +
  '.v-carteira .chart .bh{fill:none;stroke:var(--txt2);stroke-width:1.3;stroke-dasharray:4 4;opacity:.8}' +
  '.v-carteira .chart .ar{fill:rgba(var(--accent-rgb),.10)}' +
  '.v-carteira .lgd{display:flex;gap:14px;font-family:var(--f-mono);font-size:11px;color:var(--txt2)}' +
  '.v-carteira .lgd i{display:inline-block;width:16px;height:2px;vertical-align:3px;margin-right:6px;background:var(--accent)}' +
  '.v-carteira .lgd i.bh{background:none;border-top:2px dashed var(--txt2)}' +
  '.v-carteira .dca-it{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2);display:grid;gap:10px}' +
  '.v-carteira .dca-g{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}' +
  '.v-carteira .dca-g .k{font-family:var(--f-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute)}' +
  '.v-carteira .dca-g .v{font-family:var(--f-mono);font-size:13.5px;font-weight:600;margin-top:2px}' +
  '.v-carteira .dca-form{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin-top:12px;border-top:1px solid var(--line);padding-top:12px}' +
  '.v-carteira .dca-form select{background:var(--panel2);color:var(--txt);border:1px solid var(--line2);border-radius:8px;padding:8px;font-family:var(--f-mono);font-size:12.5px;width:100%}' +
  '.v-carteira .mt{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}' +
  '.v-carteira .mt>div{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel2);min-width:0}' +
  '.v-carteira .mt .k{font-family:var(--f-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
  '.v-carteira .mt .v{font-family:var(--f-mono);font-size:16px;font-weight:600;margin-top:3px}' +
  '@media (max-width:1100px){.v-carteira .mapa{grid-template-columns:1fr}.v-carteira .ct-contas{grid-template-columns:1fr}.v-carteira .mt{grid-template-columns:repeat(2,minmax(0,1fr))}}' +
  '@media (max-width:640px){.v-carteira .bolhas{height:320px}.v-carteira .aloc{justify-content:center}.v-carteira .exp div{grid-template-columns:96px minmax(0,1fr) auto}.v-carteira .dca-form{grid-template-columns:1fr 1fr}.v-carteira .dca-g{grid-template-columns:1fr 1fr}}' +
  '</style>';

  var html = css + '<div class="v-carteira">' +
    '<section class="card"><div class="card-head"><div><h2 class="h2">Mapa da carteira</h2><div class="sub">Cada bolha é uma posição ou plano de DCA; o tamanho é a margem (ou o valor do DCA), o aro é o P&amp;L.</div></div><span class="count mute">arraste as bolhas</span></div>' +
      '<div class="mapa"><div class="bolhas" id="ct-bo" aria-label="Mapa da carteira"></div><div class="ct-lado" id="ct-side"></div></div></section>' +
    '<section class="ct-contas" id="ct-contas"></section>' +
    '<section class="row-2"><article class="card"><div class="card-head"><h2 class="h2">Alocação</h2><span class="count" id="ct-al-n">—</span></div><div id="ct-al"></div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Correlação · 30 dias</h2><span class="count mute">retornos 1h</span></div><div id="ct-corr"><div class="skel"></div></div></article></section>' +
    '<section class="card"><div class="card-head"><div><h2 class="h2">Curva de equity</h2><div class="sub" id="ct-eq-s">—</div></div><div class="lgd"><span><i></i>' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</span><span><i class="bh"></i>B&amp;H BTC</span></div></div><svg class="chart" id="ct-eq" role="img" aria-label="Curva de equity"></svg></section>' +
    '<section class="row-2"><article class="card"><div class="card-head"><h2 class="h2">DCA · acumulação</h2><span class="count">spot · sem alavancagem</span></div><div id="ct-dca"></div>' +
      '<form class="dca-form" id="ct-dca-f"><label class="fld">Ativo<select id="ct-dca-a"></select></label><label class="fld">R$ por aporte<input class="inp" id="ct-dca-v" type="number" min="1" step="1" value="50"></label><label class="fld">A cada (dias)<input class="inp" id="ct-dca-d" type="number" min="1" step="1" value="7"></label><button type="submit" class="btn primary">Criar plano</button></form>' +
      '<div class="mute" style="font-size:11.5px;margin-top:10px;font-family:var(--f-mono)">banca conceitualmente separada do day trade: o DCA não entra no teto de exposição nem na trava diária</div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Histórico mensal</h2><span class="count mute" id="ct-mes-t">—</span></div><div id="ct-mes"><div class="skel"></div></div></article></section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Métricas da banca</h2><span class="count mute" id="ct-mt-t">—</span></div><div class="mt" id="ct-mt"></div><div id="ct-conv" style="margin-top:14px"></div></section>' +
  '</div>';

  var S = null;
  function $(id) { return S && S.root.querySelector('#' + id); }
  function pares(e) { return String(((e || {}).config || {}).ativos || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean); }
  var CORES = ['accent', 'info', 'pos', 'warn', 'txt2'];

  /* ---------- bolhas: empacotamento por relaxação, arrastáveis ---------- */
  function itens(e) {
    var l = (e.posicoes || []).map(function (p) { return { id: 'p' + p.id, nome: F.base(p.ativo), v: p.valor_reais || 0, pnl: p.pnl || 0, sub: p.direcao + ' ' + p.alavancagem + 'x', tipo: 'pos' }; });
    (e.dca || []).forEach(function (d) { if (d.status && d.status !== 'ativo') return; l.push({ id: 'd' + d.id, nome: F.base(d.ativo), v: d.valor_atual || d.total_investido || 0, pnl: d.pnl || 0, sub: 'DCA', tipo: 'dca' }); });
    var livre = Math.max(0, (e.banca ? e.banca.atual : 0) - ((e.risco || {}).margem_aberta || 0));
    l.push({ id: 'livre', nome: 'Livre', v: livre, pnl: 0, sub: 'sem margem', tipo: 'livre' });
    return l.filter(function (x) { return x.v > 0; });
  }
  function bolhas(e) {
    var box = $('ct-bo'), W = box.clientWidth || 600, H = box.clientHeight || 380, l = itens(e);
    var tot = l.reduce(function (a, x) { return a + x.v; }, 0) || 1, area = W * H * .42;
    var chave = l.map(function (x) { return x.id; }).join(',');
    l.forEach(function (x) { x.r = Math.max(22, Math.sqrt(area * x.v / tot / Math.PI)); });
    var maxR = Math.min(W, H) * .42; l.forEach(function (x) { if (x.r > maxR) x.r = maxR; });
    if (chave !== S.boChave || !S.bo) {
      S.boChave = chave; var ant = S.bo || {};
      S.bo = {}; l.forEach(function (x, i) { var a = ant[x.id]; S.bo[x.id] = a ? { x: a.x, y: a.y } : { x: W / 2 + Math.cos(i * 2.4) * W * .18, y: H / 2 + Math.sin(i * 2.4) * H * .18 }; });
    }
    for (var it = 0; it < 220; it++) {
      l.forEach(function (a) { var p = S.bo[a.id]; if (p.fixo) return; p.x += (W / 2 - p.x) * .01; p.y += (H / 2 - p.y) * .01; });
      for (var i = 0; i < l.length; i++) for (var j = i + 1; j < l.length; j++) {
        var a = S.bo[l[i].id], b = S.bo[l[j].id], dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || .01, min = l[i].r + l[j].r + 6;
        if (d < min) { var k = (min - d) / d / 2; if (!a.fixo) { a.x -= dx * k; a.y -= dy * k; } if (!b.fixo) { b.x += dx * k; b.y += dy * k; } }
      }
      l.forEach(function (x) { var p = S.bo[x.id]; p.x = Math.max(x.r + 2, Math.min(W - x.r - 2, p.x)); p.y = Math.max(x.r + 2, Math.min(H - x.r - 2, p.y)); });
    }
    if (l.length === 1 && l[0].id === 'livre' && !(e.dca || []).length) {
      box.innerHTML = '<div class="mapa-v">Nenhuma posição aberta nem plano de DCA: a banca inteira está livre (' + F.brl(l[0].v) + ').</div>';
      return;
    }
    box.innerHTML = l.map(function (x) {
      var p = S.bo[x.id], pct = x.v / tot * 100, cls = x.tipo === 'livre' ? 'livre' : (x.tipo === 'dca' ? 'dca ' : '') + (x.pnl > 0 ? 'pos' : x.pnl < 0 ? 'neg' : '');
      return '<div class="bo ' + cls + '" data-id="' + x.id + '" style="left:' + p.x.toFixed(1) + 'px;top:' + p.y.toFixed(1) + 'px;width:' + (2 * x.r).toFixed(0) + 'px;height:' + (2 * x.r).toFixed(0) + 'px;--fs:' + Math.max(11, Math.min(22, x.r / 3.2)).toFixed(0) + 'px" title="' + A.esc(x.nome + ' · ' + x.sub + ' · ' + F.brl(x.v) + (x.tipo === 'livre' ? '' : ' · P&L ' + F.money(x.pnl))) + '"><div><b>' + A.esc(x.nome) + '</b><span>' + F.f0(pct) + '%</span></div></div>';
    }).join('');
  }
  function arrasto(box) {
    var drag = null;
    box.addEventListener('pointerdown', function (ev) { var b = ev.target.closest('.bo'); if (!b || !S) return; drag = { el: b, id: b.dataset.id }; b.setPointerCapture(ev.pointerId); });
    box.addEventListener('pointermove', function (ev) { if (!drag || !S) return; var r = box.getBoundingClientRect(), p = S.bo[drag.id]; if (!p) return; p.x = ev.clientX - r.left; p.y = ev.clientY - r.top; p.fixo = true; drag.el.style.left = p.x + 'px'; drag.el.style.top = p.y + 'px'; });
    var solta = function () { if (!drag || !S) { drag = null; return; } var p = S.bo[drag.id]; if (p) p.fixo = false; drag = null; if (S.estado) bolhas(S.estado); };
    box.addEventListener('pointerup', solta); box.addEventListener('pointercancel', solta);
  }
  function lado(e) {
    var rg = e.risco || {}, pos = e.posicoes || [], aberto = pos.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
    var livre = Math.max(0, (e.banca ? e.banca.atual : 0) - (rg.margem_aberta || 0)), eq = e.equity_total || 0;
    $('ct-side').innerHTML = '<div class="box"><div class="k">cripto · binance futures (paper)</div><div class="v">' + F.brl(eq) + '</div><div class="s">' + pos.length + (pos.length === 1 ? ' posição' : ' posições') + ' · ' + F.f0(eq ? livre / eq * 100 : 0) + '% livre · <span class="' + F.cls(aberto) + '">' + F.money(aberto) + '</span> em aberto' + ((e.dca || []).length ? '<br>' + e.dca.length + ' plano(s) de DCA à parte' : '') + '</div></div>' +
      '<div class="box dash"><div class="k">ações BR · em construção (F8)</div><div class="s" style="margin-top:6px">Quando a B3 entrar, a carteira passa a ser multimercado e o teto de exposição vale para o total, não por mercado.</div></div>';
  }

  /* ---------- contas ---------- */
  function contas(e) {
    var eu = A.CONTA, h = e.equity_hist || [], ini = (e.banca || {}).inicial, cfg = e.config || {};
    var d0 = h.length ? A.ddmm(h[0].ts) : '—', ret = ini ? (e.equity_total / ini - 1) * 100 : 0;
    var desc = 'risco ' + F.f2((parseFloat(cfg.risco_por_trade) || 0) * 100) + '% · teto ' + F.f0((parseFloat(cfg.risco_aberto_max) || 0) * 100) + '% · TP ' + (String(cfg.tp_ativo) === '1' ? 'por estrutura' : 'off') + ' · trailing ' + (String(cfg.trailing_ativo) === '1' ? 'em ' + (cfg.trailing_unidade === 'R' ? 'R' : '%') : 'off') + (cfg.tendencia_filtro && cfg.tendencia_filtro !== 'off' ? ' · lado pelo diário' : '');
    var minha = '<div class="card ct-conta is-on"><div class="card-head"><h2 class="h2">' + (eu === 'B' ? 'Conta B' : 'Paper A') + '</h2><span class="count">esta</span></div><div class="v"><span class="cur">R$</span>' + F.f2(e.equity_total) + '</div>' +
      '<div class="s"><span class="' + F.cls(ret) + '">' + F.money(e.equity_total - ini) + ' · ' + F.pct(ret) + '</span> sobre ' + F.brl(ini) + ' (curva desde ' + d0 + ')<br>' + A.esc(desc) + '</div></div>';
    var outra = '<div class="card ct-conta"><div class="card-head"><h2 class="h2">' + (eu === 'B' ? 'Paper A' : 'Conta B') + '</h2><span class="count mute">' + (eu === 'B' ? 'produção' : 'teste A/B') + '</span></div><div class="s" style="margin:8px 0 12px">Outro backend, outro banco. Os números dela só aparecem com ela selecionada.</div><button type="button" class="btn ghost sm" data-conta="' + (eu === 'B' ? 'A' : 'B') + '">trocar para ' + (eu === 'B' ? 'Paper A' : 'Conta B') + '</button></div>';
    var real = '<div class="card ct-conta"><div class="card-head"><h2 class="h2">Real · Binance</h2><span class="soon">esteira</span></div><div class="esteira"><span>testnet</span>→<span>dry-run</span>→<span>live</span></div><div class="s">Mede execução antes de encostar em dinheiro. Quando esta conta existir, a moldura inteira fica vermelha: dinheiro de verdade nunca parece paper.</div></div>';
    $('ct-contas').innerHTML = minha + outra + real;
  }

  /* ---------- alocação ---------- */
  function alocacao(e) {
    var pos = e.posicoes || [], rg = e.risco || {}, eq = e.equity_total || 0;
    var livre = Math.max(0, (e.banca ? e.banca.atual : 0) - (rg.margem_aberta || 0));
    var l = pos.map(function (p, i) { return { n: F.par(p.ativo), v: p.valor_reais || 0, c: CORES[i % CORES.length], d: p.direcao + ' ' + p.alavancagem + 'x' }; });
    var tot = l.reduce(function (a, x) { return a + x.v; }, 0) + livre || 1;
    $('ct-al-n').textContent = pos.length + (pos.length === 1 ? ' posição' : ' posições') + ' · ' + F.f0((tot - livre) / tot * 100) + '% em margem';
    var C = 2 * Math.PI * 58, acc = 0, segs = l.map(function (x) { var f = x.v / tot, s = '<circle cx="75" cy="75" r="58" fill="none" stroke="var(--' + x.c + ')" stroke-width="16" stroke-dasharray="' + (f * C).toFixed(2) + ' ' + C.toFixed(2) + '" stroke-dashoffset="' + (-acc * C).toFixed(2) + '"/>'; acc += f; return s; }).join('');
    var long = pos.filter(function (p) { return p.direcao === 'LONG'; }), short = pos.filter(function (p) { return p.direcao !== 'LONG'; });
    var nl = long.reduce(function (a, p) { return a + p.valor_reais * p.alavancagem; }, 0), ns = short.reduce(function (a, p) { return a + p.valor_reais * p.alavancagem; }, 0), mx = Math.max(nl, ns, 1);
    $('ct-al').innerHTML = '<div class="aloc"><div class="donut"><svg viewBox="0 0 150 150" aria-hidden="true"><circle cx="75" cy="75" r="58" fill="none" stroke="rgba(var(--txt-rgb),.07)" stroke-width="16"/>' + segs + '</svg><div><span><b>' + F.f0((tot - livre) / tot * 100) + '%</b><small>em margem</small></span></div></div>' +
      '<ul class="leg">' + l.map(function (x) { return '<li><i style="background:var(--' + x.c + ')"></i><span class="mono">' + A.esc(x.n) + ' <span class="mute">' + x.d + '</span></span><span class="m">' + F.brl(x.v) + '</span><span class="m">' + F.f0(x.v / tot * 100) + '%</span></li>'; }).join('') +
      '<li><i style="background:rgba(var(--txt-rgb),.12)"></i><span>Livre</span><span class="m">' + F.brl(livre) + '</span><span class="m">' + F.f0(livre / tot * 100) + '%</span></li></ul></div>' +
      '<div class="exp"><div><span>risco aberto · teto ' + F.f0(rg.risco_aberto_max_rs && eq ? rg.risco_aberto_max_rs / (eq - (rg.pnl_dia || 0)) * 100 : 0) + '%</span><div class="bar"><i style="--w:' + Math.min(100, rg.risco_aberto_max_rs ? rg.risco_aberto_rs / rg.risco_aberto_max_rs * 100 : 0).toFixed(1) + '%;--c:var(--warn)"></i></div><span>' + F.brl(rg.risco_aberto_rs) + ' / ' + F.brl(rg.risco_aberto_max_rs) + '</span></div>' +
      '<div><span>long · ' + long.length + ' pos</span><div class="bar"><i style="--w:' + (nl / mx * 100).toFixed(1) + '%;--c:var(--pos)"></i></div><span>' + F.brl(nl) + '</span></div>' +
      '<div><span>short · ' + short.length + ' pos</span><div class="bar"><i style="--w:' + (ns / mx * 100).toFixed(1) + '%;--c:var(--neg)"></i></div><span>' + F.brl(ns) + '</span></div>' +
      '<div><span>margem usada</span><span>' + F.brl(rg.margem_aberta) + ' · ' + F.f2(eq ? (rg.margem_aberta || 0) / eq * 100 : 0) + '% do equity</span><span>' + (nl > ns ? 'net LONG' : ns > nl ? 'net SHORT' : '—') + '</span></div>' +
      '<div class="mute" style="display:block;font-family:var(--f-ui);font-size:11px;text-transform:none;letter-spacing:0">nocional = margem × alavancagem</div></div>';
  }

  /* ---------- correlação 30 dias (retornos de 1h) e B&H BTC ---------- */
  async function lerVelas() {
    var e = S.estado || {}, alvo = ['BTC/USDT'];
    (e.posicoes || []).forEach(function (p) { if (alvo.indexOf(p.ativo) < 0) alvo.push(p.ativo); });
    var me = S, out = {};
    await Promise.all(alvo.map(function (a) { return A.api('/candles?ativo=' + encodeURIComponent(a) + '&tf=1h&limite=720').then(function (c) { out[a] = c || []; }).catch(function () {}); }));
    if (S !== me) return; S.velas = out; S.velasEm = Date.now(); correlacao(); curva(S.estado);
  }
  function correlacao() {
    var e = S.estado || {}, l = []; (e.posicoes || []).forEach(function (p) { if (l.indexOf(p.ativo) < 0) l.push(p.ativo); });
    var el = $('ct-corr');
    if (l.length < 2) { el.innerHTML = '<div class="empty">Correlação precisa de pelo menos duas posições abertas em pares diferentes. Hoje: ' + l.length + '.</div>'; return; }
    if (!S.velas) { el.innerHTML = '<div class="skel"></div>'; return; }
    var ret = {}; l.forEach(function (a) { var m = {}, c = S.velas[a] || []; for (var i = 1; i < c.length; i++) m[c[i].time] = Math.log(c[i].close / c[i - 1].close); ret[a] = m; });
    function rho(a, b) { var xs = [], ys = []; Object.keys(ret[a]).forEach(function (t) { if (t in ret[b]) { xs.push(ret[a][t]); ys.push(ret[b][t]); } }); var n = xs.length; if (n < 30) return null; var mx = 0, my = 0; for (var i = 0; i < n; i++) { mx += xs[i]; my += ys[i]; } mx /= n; my /= n; var sxy = 0, sx = 0, sy = 0; for (var j = 0; j < n; j++) { var dx = xs[j] - mx, dy = ys[j] - my; sxy += dx * dy; sx += dx * dx; sy += dy * dy; } return sxy / Math.sqrt(sx * sy); }
    var g = 'grid-template-columns:auto repeat(' + l.length + ',minmax(0,1fr))', h = '<div class="corr" style="' + g + '"><span></span>' + l.map(function (a) { return '<span class="h">' + A.esc(F.base(a)) + '</span>'; }).join('');
    var soma = 0, n = 0;
    l.forEach(function (a) { h += '<span class="h">' + A.esc(F.base(a)) + '</span>'; l.forEach(function (b) { var r = a === b ? 1 : rho(a, b); if (a < b && r != null) { soma += r; n++; } h += '<span class="c" style="background:' + (a === b ? 'rgba(var(--txt-rgb),.04)' : 'rgba(var(--accent-rgb),' + (r == null ? .04 : (.08 + Math.max(0, r) * .55)).toFixed(2) + ')') + ';color:' + (a === b ? 'var(--mute)' : 'var(--txt)') + '">' + (r == null ? '—' : F.f2(r)) + '</span>'; }); });
    h += '</div>';
    var med = n ? soma / n : null, mesmo = (e.posicoes || []).every(function (p) { return p.direcao === e.posicoes[0].direcao; });
    if (med != null && med > .5 && mesmo) h += '<div class="nota"><b>' + e.posicoes.length + ' posições no mesmo lado com correlação média ' + F.f2(med) + ' são quase uma aposta só.</b> O T12 mediu −1,9 log de vazamento por correlação: o risco por trade vira mais do que parece quando os pares andam juntos.</div>';
    else if (med != null) h += '<div class="mute" style="font-size:11.5px;margin-top:10px">correlação média entre as posições: ' + F.f2(med) + ' · ' + (mesmo ? 'todas no mesmo lado' : 'lados misturados') + '</div>';
    el.innerHTML = h;
  }
  function curva(e) {
    var h = (e.equity_hist || []).filter(function (x) { return typeof x.equity_total === 'number'; }), svg = $('ct-eq');
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (h.length < 2) { $('ct-eq-s').textContent = 'a curva aparece com dois pontos gravados'; return; }
    var W = Math.max(300, svg.clientWidth || 800), H = 240, pl = 66, pr = 14, pt = 12, pb = 24, n = h.length;
    var t0 = A.ts(h[0].ts), tN = A.ts(h[n - 1].ts), tx = function (d) { return pl + (d - t0) / ((tN - t0) || 1) * (W - pl - pr); };
    /* régua: quanto a equity inicial valeria comprada em BTC no primeiro ponto e segurada. Vela de 1h
       (epoch UTC) casada pelo instante do ponto (hora de SP, lida pelo relógio do navegador). */
    var bh = [], c = (S.velas || {})['BTC/USDT'] || [];
    if (c.length) {
      var at = function (d) { var s = d.getTime() / 1000, best = null; for (var i = 0; i < c.length; i++) { if (c[i].time <= s) best = c[i]; else break; } return best; };
      var c0 = at(t0);
      if (c0) h.forEach(function (x) { var d = A.ts(x.ts), ci = at(d); if (ci) bh.push({ d: d, v: h[0].equity_total * ci.close / c0.close }); });
    }
    var vs = h.map(function (x) { return x.equity_total; }).concat(bh.map(function (x) { return x.v; })), lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs), sp = hi - lo || hi * .01 || 1; lo -= sp * .1; hi += sp * .1;
    var ty = function (v) { return pt + (1 - (v - lo) / (hi - lo)) * (H - pt - pb); };
    var NS = 'http://www.w3.org/2000/svg', mk = function (t, a) { var el = document.createElementNS(NS, t); for (var k in a) el.setAttribute(k, a[k]); svg.appendChild(el); return el; };
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    for (var g = 0; g < 4; g++) { var v = lo + (hi - lo) * (g + .5) / 4; mk('line', { x1: pl, x2: W - pr, y1: ty(v), y2: ty(v), 'class': 'g' }); mk('text', { x: pl - 8, y: ty(v) + 3.5, 'class': 'ax', 'text-anchor': 'end' }).textContent = sp < 20 ? F.f2(v) : F.f0(v); }
    [0, Math.floor((n - 1) / 2), n - 1].forEach(function (i, k) { mk('text', { x: tx(A.ts(h[i].ts)), y: H - 6, 'class': 'ax', 'text-anchor': k === 0 ? 'start' : k === 2 ? 'end' : 'middle' }).textContent = A.ddmm(h[i].ts); });
    var d = h.map(function (x, i) { return (i ? 'L' : 'M') + tx(A.ts(x.ts)).toFixed(1) + ' ' + ty(x.equity_total).toFixed(1); }).join(' ');
    mk('path', { d: d + ' L' + (W - pr) + ' ' + (H - pb) + ' L' + pl + ' ' + (H - pb) + ' Z', 'class': 'ar' });
    if (bh.length > 1) mk('path', { d: bh.map(function (x, i) { return (i ? 'L' : 'M') + tx(x.d).toFixed(1) + ' ' + ty(x.v).toFixed(1); }).join(' '), 'class': 'bh' });
    mk('path', { d: d, 'class': 'eq' });
    var fim = h[n - 1].equity_total, bhF = bh.length ? bh[bh.length - 1].v : null;
    $('ct-eq-s').innerHTML = A.ddmm(h[0].ts) + ' → ' + A.ddmm(h[n - 1].ts) + ' · equity ' + F.brl(h[0].equity_total) + ' → ' + F.brl(fim) + ' (<span class="' + F.cls(fim - h[0].equity_total) + '">' + F.pct((fim / h[0].equity_total - 1) * 100) + '</span>)' +
      (bhF != null ? ' · B&amp;H BTC no mesmo período: <span class="' + F.cls(bhF - h[0].equity_total) + '">' + F.pct((bhF / h[0].equity_total - 1) * 100) + '</span>' : c.length ? ' · B&amp;H BTC: as velas de 1h não cobrem o início da curva' : ' · B&amp;H BTC: lendo velas…');
  }

  /* ---------- DCA ---------- */
  function dca(e) {
    var l = e.dca || [], el = $('ct-dca');
    el.innerHTML = l.length ? '<div style="display:grid;gap:10px">' + l.map(function (d) {
      var prox = d.ultimo_aporte ? (function () { var t = A.ts(d.ultimo_aporte); if (!t) return '—'; t = new Date(t.getTime() + d.freq_dias * 86400000); return ('0' + t.getDate()).slice(-2) + '/' + ('0' + (t.getMonth() + 1)).slice(-2); })() : 'no próximo ciclo';
      return '<div class="dca-it"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="mono strong">' + A.esc(F.par(d.ativo)) + '</span><span class="chip neutro">' + F.brl(d.valor_aporte) + ' a cada ' + d.freq_dias + ' d</span><span class="mono ' + F.cls(d.pnl) + '" style="margin-left:auto">' + F.money(d.pnl) + ' · ' + F.pct(d.pnl_pct) + '</span></div>' +
        '<div class="dca-g"><div><div class="k">acumulado</div><div class="v">' + F.f2(d.unidades) + ' ' + A.esc(F.base(d.ativo)) + '</div></div><div><div class="k">investido → hoje</div><div class="v">' + F.brl(d.total_investido) + ' → ' + F.brl(d.valor_atual) + '</div></div><div><div class="k">preço médio</div><div class="v">' + F.px(d.preco_medio) + '</div></div>' +
        '<div><div class="k">aportes</div><div class="v">' + d.n_aportes + '</div></div><div><div class="k">último</div><div class="v">' + (d.ultimo_aporte ? A.ddmm(d.ultimo_aporte) : '—') + '</div></div><div><div class="k">próximo</div><div class="v">' + prox + '</div></div></div>' +
        '<div class="sg-act" style="display:flex;gap:8px"><button type="button" class="btn ghost sm" data-aportar="' + d.id + '">Aportar agora</button><button type="button" class="btn danger sm" data-remover="' + d.id + '">Remover plano</button></div></div>';
    }).join('') + '</div>' : '<div class="empty">Nenhum plano de DCA. Crie um abaixo: compra spot periódica, sem alavancagem.</div>';
    var sel = $('ct-dca-a');
    if (!sel.options.length) pares(e).forEach(function (a) { var o = document.createElement('option'); o.value = a; o.textContent = F.par(a); sel.appendChild(o); });
  }
  async function criaDca(ev) {
    ev.preventDefault();
    var a = $('ct-dca-a').value, v = +$('ct-dca-v').value, d = +$('ct-dca-d').value;
    if (!a || !(v > 0) || !(d >= 1)) { A.toast('Preencha ativo, valor e frequência', 'warn'); return; }
    var ok = await A.dialogo({ titulo: 'Criar plano de DCA', ok: 'Criar plano', corpo: '<p>Compra spot de <b>' + F.brl(v) + '</b> em <b>' + A.esc(F.par(a)) + '</b> a cada <b>' + d + (d === 1 ? ' dia' : ' dias') + '</b>, sem alavancagem, na ' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '. O primeiro aporte sai no próximo ciclo do worker.</p>' });
    if (!ok) return;
    try { await A.api('/dca', { ativo: a, valor_aporte: v, freq_dias: d }); A.toast('Plano DCA criado: ' + F.par(a) + ' ' + F.brl(v) + ' / ' + d + ' d'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }
  async function aportar(d) {
    try { var r = await A.api('/dca/aportar', { id: d.id }); A.toast(r.ok ? 'Aporte feito em ' + F.par(d.ativo) + ' @ ' + F.px(r.preco) : 'Aporte recusado: ' + (r.erro || 'sem detalhe'), r.ok ? '' : 'neg'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }
  async function remover(d) {
    var ok = await A.dialogo({ titulo: 'Remover plano de DCA', ok: 'Remover', perigo: true, corpo: '<p>Remove o plano de <b>' + A.esc(F.par(d.ativo)) + '</b> (' + d.n_aportes + ' aportes, ' + F.brl(d.total_investido) + ' investidos, hoje ' + F.brl(d.valor_atual) + ').</p>' });
    if (!ok) return;
    try { await A.api('/dca/remover', { id: d.id }); A.toast('Plano removido'); A.carregar(); } catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }

  /* ---------- histórico mensal e métricas ---------- */
  async function mensal() {
    var tr; try { tr = await A.api('/trades?limite=500'); } catch (err) { if (S) $('ct-mes').innerHTML = '<div class="empty">Não consegui ler o /trades.</div>'; return; }
    if (!S) return;
    tr = (tr || []).filter(function (t) { return t.fechado_em; });
    if (!tr.length) { $('ct-mes').innerHTML = '<div class="empty">Nenhum trade fechado ainda.</div>'; $('ct-mes-t').textContent = '—'; return; }
    var m = {}, ord = [], teto = tr.length >= 500, menor = tr.reduce(function (a, t) { return t.fechado_em < a ? t.fechado_em : a; }, tr[0].fechado_em).slice(0, 7);
    tr.forEach(function (t) { var k = t.fechado_em.slice(0, 7); if (!m[k]) { m[k] = { p: 0, n: 0, g: 0 }; ord.push(k); } m[k].p += t.pnl_reais || 0; m[k].n++; if (t.pnl_reais > 0) m[k].g++; });
    ord.sort();
    var MN = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'], ini = (S.estado.banca || {}).inicial || 0;
    $('ct-mes-t').textContent = MN[+ord[0].slice(5) - 1] + ' → ' + MN[+ord[ord.length - 1].slice(5) - 1] + ' ' + ord[ord.length - 1].slice(0, 4);
    $('ct-mes').innerHTML = '<div class="tablewrap"><table class="tbl"><thead><tr><th>Mês</th><th class="num">P&amp;L</th><th class="num">% da banca inicial</th><th class="num">Trades</th><th class="num">Win rate</th></tr></thead><tbody>' +
      ord.slice().reverse().map(function (k) { var x = m[k], parc = teto && k === menor; return '<tr><td class="mono">' + MN[+k.slice(5) - 1] + '/' + k.slice(2, 4) + (parc ? ' <span class="mute">(parcial)</span>' : '') + '</td><td class="mono num ' + F.cls(x.p) + '">' + F.money(x.p) + '</td><td class="mono num ' + F.cls(x.p) + '">' + (ini ? F.pct(x.p / ini * 100) : '—') + '</td><td class="mono num">' + x.n + '</td><td class="mono num">' + F.f0(x.g / x.n * 100) + '%</td></tr>'; }).join('') +
      '</tbody></table></div><div class="mute" style="font-size:11px;margin-top:8px;font-family:var(--f-mono)">P&amp;L fechado por mês, dos ' + tr.length + ' trades mais recentes' + (teto ? ' (o mês mais antigo pode estar incompleto)' : '') + ' · o reset zera o histórico</div>';
  }
  function metricas(e) {
    var m = e.metricas || {};
    $('ct-mt-t').textContent = (m.n_trades || 0) + ' trades fechados · toda a vida da banca';
    var it = [['Trades', m.n_trades || 0, ''], ['Win rate', m.n_trades ? F.f0(m.win_rate) + '%' : '—', ''], ['P&L total', F.money(m.pnl_total), F.cls(m.pnl_total)], ['Taxas pagas', F.brl(m.taxa_total), ''],
      ['Profit factor', m.n_trades ? F.f2(m.profit_factor) : '—', ''], ['Ganho médio', F.money(m.ganho_medio), 'pos'], ['Perda média', F.money(m.perda_media), 'neg'], ['Expectativa', m.n_trades ? F.money(m.expectancia) : '—', F.cls(m.expectancia)],
      ['Expectativa (R)', m.n_trades ? F.f2(m.expectancia_r) + 'R' : '—', F.cls(m.expectancia_r)], ['SQN (R)', m.n_trades ? F.f2(m.sqn_r) : '—', ''], ['Sharpe', m.n_trades ? F.f2(m.sharpe) : '—', ''], ['Sortino', m.n_trades ? F.f2(m.sortino) : '—', ''],
      ['Drawdown máx.', F.money(-(m.max_drawdown || 0)) + ' · ' + F.f2(m.max_drawdown_pct) + '%', 'neg'], ['DD marcado a mercado', F.f2(m.max_dd_mtm_pct) + '%', 'neg'], ['Calmar', m.n_trades ? F.f2(m.calmar) : '—', ''], ['Sem P&L gravado', m.n_sem_pnl || 0, '']];
    $('ct-mt').innerHTML = it.map(function (x) { return '<div><div class="k">' + x[0] + '</div><div class="v ' + x[2] + '">' + x[1] + '</div></div>'; }).join('');
    var pc = m.por_conviccao || [];
    $('ct-conv').innerHTML = pc.length ? '<div class="sub" style="margin-bottom:6px">Win rate por faixa de convicção</div><div class="tablewrap"><table class="tbl"><thead><tr><th>Faixa</th><th class="num">Trades</th><th class="num">Win rate</th><th class="num">P&amp;L</th><th>Barra</th></tr></thead><tbody>' +
      pc.map(function (x) { return '<tr><td class="mono">' + A.esc(x.faixa) + '</td><td class="mono num">' + x.n + '</td><td class="mono num">' + F.f0(x.win_rate) + '%</td><td class="mono num ' + F.cls(x.pnl) + '">' + F.money(x.pnl) + '</td><td style="min-width:120px"><div class="bar"><i style="--w:' + Math.max(0, Math.min(100, x.win_rate)) + '%"></i></div></td></tr>'; }).join('') + '</tbody></table></div><div class="mute" style="font-size:11px;margin-top:6px">O [Q-13] mediu: a convicção não prevê acerto. A tabela mostra, não promete.</div>' : '';
  }

  function render(e) {
    if (!S) return; var primeira = !S.estado; S.estado = e;
    bolhas(e); lado(e); contas(e); alocacao(e); dca(e); metricas(e);
    var ids = (e.posicoes || []).map(function (p) { return p.ativo; }).sort().join(',');
    if (primeira || ids !== S.posIds) { S.posIds = ids; lerVelas(); if (!primeira) correlacao(); }
    if (primeira) { curva(e); mensal(); } else if ((e.equity_hist || []).length !== S.nEq) curva(e);
    S.nEq = (e.equity_hist || []).length;
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.carteira = {
    id: 'carteira', titulo: 'Carteira', html: html,
    init: function (root) {
      S = { root: root, estado: null, timers: [], offs: [], bo: null };
      S.offs.push(A.on('estado', render));
      arrasto($('ct-bo'));
      root.addEventListener('click', function (ev) {
        var t = ev.target.closest('button'); if (!t || !S) return;
        var e = S.estado || {}, acha = function (id) { return (e.dca || []).find(function (x) { return String(x.id) === id; }); };
        if (t.dataset.conta) A.trocaConta(t.dataset.conta);
        else if (t.dataset.aportar) { var d = acha(t.dataset.aportar); if (d) aportar(d); }
        else if (t.dataset.remover) { var d2 = acha(t.dataset.remover); if (d2) remover(d2); }
      });
      $('ct-dca-f').addEventListener('submit', criaDca);
      var rt = 0; S.ro = new ResizeObserver(function () { clearTimeout(rt); rt = setTimeout(function () { if (S && S.estado) { bolhas(S.estado); curva(S.estado); } }, 150); }); S.ro.observe($('ct-bo'));
      S.timers.push(setInterval(function () { if (!document.hidden) mensal(); }, 300000), setInterval(function () { if (!document.hidden) lerVelas(); }, 600000));
      if (A.estado) render(A.estado);
    },
    destroy: function () { if (!S) return; S.timers.forEach(clearInterval); S.offs.forEach(function (f) { f(); }); if (S.ro) S.ro.disconnect(); S = null; }
  };
})();
