/* Apollux · view Painel (#painel). Dado real: /estado (poll da casca, 3 s) + /trades?limite=500 (Dia a
   dia, 60 s) + /sentimento e /funding (Mercado, 60 s) + /saidas (8 s), todos só enquanto a view está
   montada. Nada aqui é número de mock: o que não tem rota sai, ou vira estado vazio declarado.
   Fora do mock, declarado: linha B&H BTC da curva (nenhuma rota entrega), dominância BTC (idem), win rate
   "30d" (o /metricas é da vida da banca; o rótulo diz isso) e a marcação de trava em dias passados (o
   banco só guarda a trava de HOJE em `trava_dia_em`). */
(function () {
  'use strict';
  function p1(v) { v = +v || 0; return (Math.round(v * 10) / 10).toLocaleString('pt-BR', { maximumFractionDigits: 1 }); }
  var A = window.APX, F = A.fmt;
  var NS = 'http://www.w3.org/2000/svg';
  function svgEl(t, a) { var e = document.createElementNS(NS, t); for (var k in a) e.setAttribute(k, a[k]); return e; }
  var css = '<style>' +
  '.v-painel{display:grid;gap:18px;min-width:0}' +
  '.v-painel .row-hero{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:18px}' +
  '.v-painel .hero{min-height:470px;padding:0;overflow:hidden;display:flex;flex-direction:column}' +
  '.v-painel .terrain{position:absolute;inset:0;width:100%;height:100%;display:block}' +
  '.v-painel .hero-fade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(var(--panel-rgb),0) 48%,rgba(var(--panel-rgb),.8) 70%,var(--panel) 100%);pointer-events:none}' +
  '.v-painel .hero-head{position:relative;z-index:2;display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:18px 18px 0;flex-wrap:wrap}' +
  '.v-painel .legend{display:flex;gap:14px;font-family:var(--f-mono);font-size:11.5px;color:var(--txt2)}' +
  '.v-painel .lg{display:inline-flex;align-items:center;gap:6px}' +
  '.v-painel .lg-line{width:18px;height:2px;border-radius:2px;background:var(--accent);box-shadow:0 0 8px rgba(var(--accent-rgb),var(--glow-hi))}' +
  '.v-painel .chart-wrap{position:relative;z-index:2;margin-top:auto;padding:0 10px 8px}' +
  '.v-painel .chart{display:block;width:100%;height:210px;overflow:visible}' +
  '.v-painel .chart .grid{stroke:rgba(var(--txt-rgb),.07);stroke-width:1}' +
  '.v-painel .chart .ax{fill:var(--mute);font-family:var(--f-mono);font-size:10px}' +
  '.v-painel .chart .ln-eq{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round;filter:url(#pn-glow)}' +
  '.v-painel .chart .area{fill:url(#pn-area)}' +
  '.v-painel .chart .end{fill:var(--accent);filter:url(#pn-glow)}' +
  '.v-painel .chart .end-halo{fill:rgba(var(--accent-rgb),var(--glow));animation:pnhalo 2s ease-out infinite;transform-origin:center;transform-box:fill-box}' +
  '@keyframes pnhalo{0%{transform:scale(.6);opacity:.9}100%{transform:scale(2.6);opacity:0}}' +
  '.v-painel .chart .xh{stroke:rgba(var(--accent-rgb),var(--glow));stroke-width:1;stroke-dasharray:2 3}' +
  '.v-painel .chart .hd{fill:var(--bg);stroke:var(--accent);stroke-width:2}' +
  '.v-painel .tip{position:absolute;top:8px;left:0;transform:translateX(-50%);background:rgba(var(--bg-rgb),.94);border:1px solid rgba(var(--accent-rgb),var(--glow));border-radius:8px;padding:8px 10px;font-family:var(--f-mono);font-size:11.5px;line-height:1.55;pointer-events:none;white-space:nowrap;z-index:3}' +
  '.v-painel .tip-k{display:inline-block;min-width:68px;color:var(--txt2)}' +
  '.v-painel .hero-vazio{position:relative;z-index:2;margin:auto 18px 24px;}' +
  '.v-painel .gauge-card{display:grid;grid-template-columns:110px minmax(0,1fr);gap:14px;align-items:center}' +
  '.v-painel .gauge{width:110px;height:110px;position:relative}' +
  '.v-painel .gauge svg{width:100%;height:100%;transform:rotate(135deg);overflow:visible}' +
  '.v-painel .g-bg{fill:none;stroke:rgba(var(--txt-rgb),.08);stroke-width:9;stroke-linecap:round}' +
  '.v-painel .g-fg{fill:none;stroke:var(--accent);stroke-width:9;stroke-linecap:round;filter:drop-shadow(0 0 6px rgba(var(--accent-rgb),var(--glow-hi)))}' +
  '.v-painel .gauge-val{position:absolute;inset:0;display:grid;place-items:center;text-align:center}' +
  '.v-painel .gauge-val b{display:block;font-family:var(--f-mono);font-size:24px;font-weight:600;line-height:1}' +
  '.v-painel .gauge-val small{display:block;font-family:var(--f-mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);margin-top:4px}' +
  '.v-painel .gauge-meta{display:grid;gap:6px;font-size:12px}' +
  '.v-painel .gauge-meta .row{display:flex;justify-content:space-between;gap:8px}' +
  '.v-painel .gauge-meta .row span:first-child{color:var(--txt2)} .v-painel .gauge-meta .row span:last-child{font-family:var(--f-mono)}' +
  '.v-painel .robo-state{display:flex;align-items:center;gap:8px;font-family:var(--f-mono);font-size:12px;color:var(--txt2)}' +
  '.v-painel .robo-state b{letter-spacing:.1em;font-weight:600}' +
  '.v-painel .robo-act{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}' +
  '.v-painel .mkt{display:grid;gap:9px;font-size:12.5px}' +
  '.v-painel .mkt-row{display:flex;justify-content:space-between;align-items:center;gap:10px}' +
  '.v-painel .mkt-row .k{color:var(--txt2)} .v-painel .mkt-row .v{font-family:var(--f-mono);text-align:right}' +
  '.v-painel .fg{height:4px;border-radius:2px;background:rgba(var(--txt-rgb),.08);position:relative;margin-top:-3px}' +
  '.v-painel .fg i{position:absolute;left:0;top:0;bottom:0;width:var(--w);background:linear-gradient(90deg,var(--neg),var(--warn),var(--pos));border-radius:2px}' +
  '.v-painel .mkt-sub{font-family:var(--f-mono);font-size:11px;color:var(--mute);line-height:1.6}' +
  /* [CLS] com o /estado o sub dos KPIs quebra em 2 linhas (o do mês, com o DD, em 3) e empurrava a tela: reservar desde o "—" */
  '.v-painel .kpi-sub{line-height:1.45;min-height:2.9em} .v-painel #pn-mes-s{min-height:4.35em}' +
  '.v-painel .dd-res{min-height:607px;display:grid;gap:14px;align-content:start}' +
  '.v-painel .dd{display:grid;gap:14px}' +
  '.v-painel .dd-stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}' +
  '.v-painel .dd-stat{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel2);min-width:0}' +
  '.v-painel .dd-stat .k{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
  '.v-painel .dd-stat .v{font-family:var(--f-mono);font-size:17px;font-weight:600;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
  '.v-painel .dd-stat .s{font-family:var(--f-mono);font-size:11px;color:var(--txt2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
  '.v-painel .dd-cal-wrap{overflow-x:auto;padding:2px 2px 6px;scrollbar-width:thin}' +
  '.v-painel .dd-cal{display:grid;grid-template-columns:auto auto;justify-content:start;gap:6px 8px;width:max-content;--cell:30px}' +
  '.v-painel .dd-months{grid-column:2;display:grid;grid-auto-flow:column;grid-auto-columns:var(--cell);gap:4px;font-family:var(--f-mono);font-size:10.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.08em;white-space:nowrap}' +
  '.v-painel .dd-days{display:grid;grid-template-rows:repeat(7,var(--cell));gap:4px;font-family:var(--f-mono);font-size:10px;color:var(--mute);align-items:center;padding-right:2px}' +
  '.v-painel .dd-cells{display:grid;grid-auto-flow:column;grid-template-rows:repeat(7,var(--cell));grid-auto-columns:var(--cell);gap:4px}' +
  '.v-painel .dd-c{width:var(--cell);height:var(--cell);border-radius:5px;border:1px solid transparent;background:rgba(var(--txt-rgb),.07);padding:0;position:relative;transition:transform .15s,box-shadow .15s;cursor:default}' +
  '.v-painel .dd-c.z{background:rgba(var(--txt-rgb),.035);border-color:rgba(var(--txt-rgb),.06)}' +
  '.v-painel .dd-c.p1{background:rgba(var(--pos-rgb),.22)} .v-painel .dd-c.p2{background:rgba(var(--pos-rgb),.5)} .v-painel .dd-c.p3{background:rgba(var(--pos-rgb),.85)}' +
  '.v-painel .dd-c.n1{background:rgba(var(--neg-rgb),.22)} .v-painel .dd-c.n2{background:rgba(var(--neg-rgb),.5)} .v-painel .dd-c.n3{background:rgba(var(--neg-rgb),.85)}' +
  '.v-painel .dd-c.trava::after{content:"";position:absolute;right:2px;top:2px;width:5px;height:5px;border-radius:50%;background:var(--warn)}' +
  '.v-painel .dd-c.today{box-shadow:0 0 0 2px var(--accent),0 0 14px rgba(var(--accent-rgb),var(--glow))}' +
  '.v-painel .dd-c:hover,.v-painel .dd-c:focus-visible{outline:none;transform:scale(1.14);z-index:2;box-shadow:0 0 0 1px rgba(var(--txt-rgb),.55)}' +
  '.v-painel .dd-c.fora{visibility:hidden}' +
  '.v-painel .dd-legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-family:var(--f-mono);font-size:10.5px;color:var(--mute)}' +
  '.v-painel .dd-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;vertical-align:-1px;margin-right:5px}' +
  '.v-painel .dd-lg-p{background:rgba(var(--pos-rgb),.85)} .v-painel .dd-lg-n{background:rgba(var(--neg-rgb),.85)} .v-painel .dd-lg-z{background:rgba(var(--txt-rgb),.07)} .v-painel .dd-lg-h{box-shadow:0 0 0 2px var(--accent)}' +
  '.v-painel .dd-sub{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute)}' +
  '.v-painel .dd-bars{display:grid;grid-template-columns:repeat(14,minmax(0,1fr));gap:6px;align-items:end}' +
  '.v-painel .dd-b{display:grid;grid-template-rows:auto 84px auto;gap:4px;justify-items:center;min-width:0}' +
  '.v-painel .dd-b .v{font-family:var(--f-mono);font-size:10px;white-space:nowrap}' +
  '.v-painel .dd-b .t{position:relative;width:100%;height:84px}' +
  '.v-painel .dd-b .t::before{content:"";position:absolute;left:0;right:0;top:50%;height:1px;background:rgba(var(--txt-rgb),.14)}' +
  '.v-painel .dd-b i{position:absolute;left:22%;width:56%;border-radius:3px;display:block;min-height:2px}' +
  '.v-painel .dd-b i.pos{bottom:50%;background:var(--pos)} .v-painel .dd-b i.neg{top:50%;background:var(--neg)}' +
  '.v-painel .dd-b .d{font-family:var(--f-mono);font-size:10px;color:var(--mute);white-space:nowrap}' +
  '.v-painel .dd-b.today .d{color:var(--accent)}' +
  '.v-painel .dd-tot{display:flex;flex-wrap:wrap;gap:8px 18px;font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);border-top:1px solid var(--line);padding-top:10px}' +
  '.v-painel .dd-tot b{color:var(--txt);font-weight:600} .v-painel .dd-tot b.pos{color:var(--pos)} .v-painel .dd-tot b.neg{color:var(--neg)}' +
  '.v-painel .sig-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}' +
  '.v-painel .sig{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2)}' +
  '.v-painel .sig:hover{border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-painel .sig-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}' +
  '.v-painel .sig-exp{margin-left:auto;font-family:var(--f-mono);font-size:11px;color:var(--txt2)}' +
  '.v-painel .sig-conv{display:grid;grid-template-columns:auto auto minmax(0,1fr);gap:10px;align-items:center;margin-top:10px;font-family:var(--f-mono);font-size:10.5px;color:var(--mute);letter-spacing:.06em;text-transform:uppercase}' +
  '.v-painel .conv-num{font-size:18px;font-weight:600;color:var(--txt);letter-spacing:0}' +
  '.v-painel .sig-why{font-size:12.5px;color:var(--txt2);margin-top:8px}' +
  '.v-painel .sig-act{display:flex;gap:8px;margin-top:10px}' +
  '.v-painel .saida td{white-space:normal;font-size:11.5px;color:var(--warn);padding-top:0}' +
  '.v-painel .ord{display:grid;gap:10px}' +
  '.v-painel .ord-item{display:grid;gap:7px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel2)}' +
  '.v-painel .ord-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:12.5px}' +
  '.v-painel .ord-top .px{margin-left:auto;font-family:var(--f-mono)}' +
  '.v-painel .ord-meta{font-family:var(--f-mono);font-size:11px;color:var(--txt2)}' +
  '.v-painel .ord-note{font-family:var(--f-mono);font-size:10.5px;color:var(--mute);margin-top:4px}' +
  '.v-painel .trava-val{font-family:var(--f-mono);font-size:22px;font-weight:600;margin-top:2px}' +
  '.v-painel .trava-rows{display:grid;gap:6px;margin-top:10px;font-size:12.5px}' +
  '.v-painel .trava-rows div{display:flex;justify-content:space-between;gap:8px}' +
  '.v-painel .trava-rows span:first-child{color:var(--txt2)} .v-painel .trava-rows span:last-child{font-family:var(--f-mono);text-align:right}' +
  '.v-painel .jr{list-style:none;margin:0;padding:0;display:grid}' +
  '.v-painel .jr li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(var(--line-rgb),.6);font-size:12.5px}' +
  '.v-painel .jr li:last-child{border-bottom:0}' +
  '.v-painel .jr .when{font-family:var(--f-mono);font-size:11px;color:var(--mute);white-space:nowrap}' +
  '.v-painel .jr .what{display:flex;gap:6px;align-items:center;flex-wrap:wrap;min-width:0}' +
  '.v-painel .jr .amt{font-family:var(--f-mono);font-weight:600;white-space:nowrap}' +
  '.v-painel .jr .how{font-family:var(--f-mono);font-size:10.5px;color:var(--mute)}' +
  '.v-painel .build{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}' +
  '.v-painel .bcard{border:1px dashed var(--line2);border-radius:12px;padding:14px;background:rgba(var(--panel-rgb),.5);display:grid;gap:8px;align-content:start}' +
  '.v-painel .bcard h3{font-family:var(--f-display);font-size:14px;font-weight:700;margin:0}' +
  '.v-painel .bcard p{margin:0;font-size:12px;color:var(--txt2)}' +
  '.v-painel .bcard .soon{margin-left:0;width:max-content}' +
  '@media (max-width:1300px){.v-painel .build{grid-template-columns:repeat(3,minmax(0,1fr))}}' +
  '@media (max-width:1100px){.v-painel .row-hero{grid-template-columns:1fr}.v-painel .side-stack{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}.v-painel .dd-stats{grid-template-columns:repeat(3,minmax(0,1fr))}}' +
  '@media (max-width:760px){.v-painel .build{grid-template-columns:1fr}.v-painel .hero{min-height:400px}.v-painel .gauge-card{grid-template-columns:1fr;justify-items:center}}' +
  '@media (max-width:640px){.v-painel .dd-stat .k,.v-painel .dd-stat .s{white-space:normal}.v-painel .dd-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.v-painel .dd-bars{grid-template-columns:repeat(7,minmax(0,1fr))}.v-painel .dd-b{grid-template-rows:auto 44px auto}.v-painel .dd-b .t{height:44px}.v-painel .dd-b .v{font-size:9px}.v-painel .dd-cal{--cell:26px}}' +
  '@media (prefers-reduced-motion:reduce){.v-painel .chart .end-halo{animation:none}}' +
  '.v-painel .pc-list{display:grid;gap:10px}' +
  '.v-painel .pc{border:1px solid var(--line);border-radius:12px;padding:12px;background:var(--panel2);display:grid;gap:10px}' +
  '.v-painel .pc-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}' +
  '.v-painel .pc-pnl{margin-left:auto;font-family:var(--f-mono);font-weight:600;font-size:16px;text-align:right;line-height:1.15}' +
  '.v-painel .pc-pnl small{display:block;font-size:11px;font-weight:500}' +
  '.v-painel .pc-kv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 10px;margin:0}' +
  '.v-painel .pc-kv dt{font-family:var(--f-mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}' +
  '.v-painel .pc-kv dd{margin:2px 0 0;font-family:var(--f-mono);font-size:12.5px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}' +
  '.v-painel .pc-saida{font-size:11.5px;color:var(--warn);border:1px solid rgba(var(--warn-rgb),.35);border-radius:8px;padding:5px 8px}' +
  '.v-painel .pc .btn{justify-self:start}' +
  /* o Fechar fica preso na borda direita: a tabela rola por baixo dele, mas o botão nunca some */
  '.v-painel #pn-pos tr:not(.saida)>td:last-child,.v-painel #pn-pos th:last-child{position:sticky;right:0;background:var(--panel);box-shadow:-10px 0 10px -6px rgba(var(--bg-rgb),.9)}' +
  '</style>';

  var html = css + '<div class="v-painel">' +
    '<section class="kpis" aria-label="Conta">' +
      '<div class="kpi"><div class="kpi-lbl">Equity</div><div class="kpi-val" id="pn-eq">—</div><div class="kpi-sub" id="pn-eq-s">—</div></div>' +
      '<div class="kpi"><span class="kpi-div" aria-hidden="true"></span><div class="kpi-lbl">P&amp;L do dia</div><div class="kpi-val" id="pn-dia">—</div><div class="kpi-sub" id="pn-dia-s" title="P&amp;L do dia = equity de agora − equity do primeiro retrato do dia (a mesma base da trava). São duas partes: o que FECHOU hoje (inclusive a parte de ontem de um trade que atravessou a meia-noite) e quanto o P&amp;L das posições abertas andou desde 00h.">—</div></div>' +
      '<div class="kpi"><span class="kpi-div" aria-hidden="true"></span><div class="kpi-lbl">P&amp;L do mês</div><div class="kpi-val" id="pn-mes">—</div><div class="kpi-sub" id="pn-mes-s">—</div></div>' +
      '<div class="kpi"><span class="kpi-div" aria-hidden="true"></span><div class="kpi-lbl">Win rate</div><div class="kpi-val" id="pn-wr">—</div><div class="kpi-sub" id="pn-wr-s">—</div></div>' +
    '</section>' +
    '<section class="row-hero">' +
      '<article class="card hero" id="pn-hero"><canvas class="terrain" id="pn-terrain" aria-hidden="true"></canvas><div class="hero-fade" aria-hidden="true"></div>' +
        '<div class="hero-head"><div><h2 class="h2">Curva de capital</h2><div class="sub mono" id="pn-range">—</div></div>' +
        '<div class="legend"><span class="lg"><i class="lg-line"></i>Equity</span></div></div>' +
        '<div class="chart-wrap"><svg id="pn-eq-svg" class="chart" role="img" aria-label="Curva de equity"></svg><div class="tip" id="pn-tip" hidden></div></div></article>' +
      '<div class="stack side-stack">' +
        '<article class="card gauge-card"><div class="gauge" role="img" id="pn-gauge-lbl" aria-label="Win rate"><svg viewBox="0 0 120 120" aria-hidden="true"><circle class="g-bg" cx="60" cy="60" r="50" stroke-dasharray="235.6 314.2"/><circle class="g-fg" id="pn-gfg" cx="60" cy="60" r="50" stroke-dasharray="0 314.2"/></svg>' +
          '<div class="gauge-val" aria-hidden="true"><div><b id="pn-g-v">—</b><small>win rate</small></div></div></div>' +
          '<div class="gauge-meta" id="pn-g-meta">' + ['Payoff', 'Trades', 'Expectativa', 'Pior sequência'].map(function (k) { return '<div class="row"><span>' + k + '</span><span>—</span></div>'; }).join('') +
          '<div class="row"><span class="mute" style="font-size:10.5px">sequência nos últimos … trades</span><span></span></div></div></article>' +
        '<article class="card"><div class="card-head"><h2 class="h2">Apollo</h2><span class="robo-state" id="pn-robo-st"></span></div>' +
          '<dl class="kv" id="pn-robo-kv">' + ['Modo', 'Risco / trade', 'Alavancagem', 'Conv. mínima', 'Última ação'].map(function (k) { return '<dt>' + k + '</dt><dd>—</dd>'; }).join('') + '</dl>' +
          '<div class="guards" id="pn-guards" style="margin-top:12px" aria-label="Guardas">' + ['teto de risco aberto —', 'trava diária —', 'margem máx. —', 'trailing —'].map(function (k) { return '<span class="guard off">' + k + '</span>'; }).join('') + '</div>' +
          '<div class="robo-act"><button type="button" class="btn ghost" id="pn-auto">—</button><button type="button" class="btn danger" id="pn-panico">Pânico</button><a class="btn ghost" href="#apollo">Configurar</a></div></article>' +
        '<article class="card"><div class="card-head"><h2 class="h2">Mercado</h2><span class="count mute" id="pn-mkt-t">—</span></div><div class="mkt" id="pn-mkt"><div class="skel"></div><div class="skel"></div></div></article>' +
      '</div>' +
    '</section>' +
    '<section class="card dd" id="pn-dd"><div class="card-head" style="margin-bottom:0"><div><h2 class="h2">Dia a dia</h2><div class="sub mono" id="pn-dd-sub">P&amp;L fechado por dia</div></div><span class="count" id="pn-dd-streak">—</span></div>' +
      '<div id="pn-dd-body"><div class="dd-res"><div class="skel"></div><div class="skel" style="width:60%"></div></div></div><div class="tip" id="pn-dd-tip" hidden></div></section>' +
    '<section class="row-2">' +
      '<article class="card"><div class="card-head"><h2 class="h2">Sinais na fila</h2><span class="count" id="pn-sig-n">0</span></div><div id="pn-sinais"></div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Posições abertas</h2><span class="count" id="pn-pos-n">0</span></div><div id="pn-pos"></div></article>' +
    '</section>' +
    '<section class="row-3">' +
      '<article class="card"><div class="card-head"><h2 class="h2">Ordens pendentes</h2><span class="count" id="pn-ord-n">0</span></div><div id="pn-ord"></div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Trava diária</h2><span class="state" id="pn-trava-st">—</span></div><div id="pn-trava"></div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Journal</h2><a class="count" href="#apollo">últimos 5 · ver tudo</a></div><ul class="jr" id="pn-jr"></ul></article>' +
    '</section>' +
    '<section aria-label="Em construção"><div class="card-head"><h2 class="h2">Em construção</h2><span class="count mute">5 módulos</span></div><div class="build">' +
      '<a class="bcard" href="#acoes"><h3>Ações BR</h3><p>B3: ações, índice, mini dólar. O mesmo Apollo, outro mercado.</p><span class="soon">em breve</span></a>' +
      '<a class="bcard" href="#fundamentos"><h3>Fundamentos com LLM</h3><p>Pergunte sobre um ativo e receba a leitura com o porquê e a fonte.</p><span class="soon">em breve</span></a>' +
      '<a class="bcard" href="#noticias"><h3>Notícias</h3><p>Consolidação por ativo, com efeito medido sobre o preço.</p><span class="soon">em breve</span></a>' +
      '<a class="bcard" href="#mobile"><h3>App mobile + push</h3><p>Lucro do dia, prejuízo e oportunidades no bolso.</p><span class="soon">em breve</span></a>' +
      '<div class="bcard"><h3>Conta real Binance</h3><p>Esteira testnet → dry-run → live. Mede execução antes de encostar em dinheiro.</p><span class="soon">esteira</span></div>' +
    '</div></section>' +
  '</div>';

  var S = null; /* estado da instância montada (zerado no destroy) */

  function $(id) { return S && S.root.querySelector('#' + id); }

  /* ---------- KPIs ---------- */
  function cur(v, sinal) { var a = Math.abs(v); return (sinal ? (v > 0 ? '+' : v < 0 ? '−' : '') : (v < 0 ? '−' : '')) + '<span class="cur">R$</span>' + F.f2(a); }
  function kpis(e) {
    var rg = e.risco || {}, m = e.metricas || {}, eq = e.equity_total, pd = rg.pnl_dia || 0, base = eq - pd;
    A.contar($('pn-eq'), eq, function (v) { return cur(v); });
    $('pn-eq-s').textContent = 'início do dia ' + F.brl(base) + ' · saldo realizado ' + F.brl(e.banca && e.banca.atual);
    var d = $('pn-dia'); d.className = 'kpi-val ' + F.cls(pd);
    /* [dia] O P&L do dia é o do backend (equity agora − 1º retrato do dia, a base da trava). Ele não bate com
       o "hoje" do Dia a dia, que é só o FECHADO, e a tela não dizia por quê: um trade aberto ontem que fecha
       hoje entra inteiro no fechado, mas a parte dele que andou até 00h já estava no equity de ontem. A
       identidade é exata: pnl_dia = realizado_hoje + (P&L aberto agora − P&L aberto às 00h). */
    var real = rg.realizado_hoje || 0, dAb = Math.round((pd - real) * 100) / 100;
    $('pn-dia-s').innerHTML = 'fechado hoje <span class="' + F.cls(real) + '">' + F.money(real) + '</span> · aberto <span class="' + F.cls(dAb) + '">' + F.money(dAb) + '</span> desde 00h';
    A.contar(d, pd, function (v) { return cur(v, true) + '<span class="pct">' + (base > 0 ? F.pct(pd / base * 100) : '') + '</span>'; });
    /* mês: equity de agora contra o último ponto da curva ANTES do dia 1. Sem ponto antes (curva nasceu
       neste mês, ou reset), compara com o primeiro ponto e o rótulo diz desde quando. */
    var h = e.equity_hist || [], ini = A.hoje().slice(0, 8) + '01', ref = null, desde = null;
    for (var i = h.length - 1; i >= 0; i--) if (A.dia(h[i].ts) < ini) { ref = h[i].equity_total; break; }
    if (ref == null && h.length) { ref = h[0].equity_total; desde = A.ddmm(h[0].ts); }
    /* [mês] Com o /trades lido (Dia a dia), o mês é EXATO: soma do P&L fechado no mês — o mesmo número
       da Carteira — e o P&L em aberto vai à parte. Pela curva amostrada (~1 ponto a cada 10 h) o ponto
       "antes do dia 1" pode ser de horas antes, e o Painel chegou a dizer R$ 1.535 onde eram R$ 1.455,
       com a Carteira dizendo R$ 1.385 para o mesmo mês. A curva só vale enquanto o /trades não chegou. */
    var mes = $('pn-mes'), unreal = eq - ((e.banca || {}).atual || 0), aberto = ' · em aberto agora <span class="' + F.cls(unreal) + '">' + F.money(unreal) + '</span>';
    var pm = null, baseM = null, sub = '';
    if (S.mesReal != null) {
      pm = S.mesReal; baseM = ((e.banca || {}).atual || 0) - pm;
      sub = 'fechado no mês' + (S.mesCompleto ? '' : ' (desde ' + S.mesDesde + ', limite de 500 trades)') + aberto;
    } else if (ref != null) { pm = eq - ref; baseM = ref; sub = (desde ? 'desde ' + desde + ', ' : '') + 'pela curva amostrada ≈'; }
    if (pm != null) {
      mes.className = 'kpi-val ' + F.cls(pm);
      A.contar(mes, pm, function (v) { return cur(v, true) + '<span class="pct">' + (baseM > 0 ? F.pct(pm / baseM * 100) : '') + '</span>'; });
    } else mes.textContent = '—';
    var pico = h.reduce(function (a, x) { return Math.max(a, x.equity_total); }, eq), ddA = pico ? (eq / pico - 1) * 100 : 0;
    $('pn-mes-s').innerHTML = sub + '<br>DD atual <span class="' + (ddA < 0 ? 'neg' : '') + '">' + F.pct(ddA, 1) + '</span> <span title="o DD atual sai da curva amostrada do /estado (~125 pontos): aproximado">≈</span> · máx. ' + F.pct(-(m.max_dd_mtm_pct || 0), 1);
    var wr = $('pn-wr');
    if (m.n_trades) {
      A.contar(wr, m.win_rate || 0, function (v) { return F.f0(v) + '<span class="txt2" style="font-size:.55em;font-weight:500;margin-left:1px">%</span>'; });
      var payoff = m.perda_media ? Math.abs(m.ganho_medio / m.perda_media) : 0;
      $('pn-wr-s').textContent = 'payoff ' + F.f2(payoff) + ' · ' + m.n_trades + ' trades (toda a banca)';
    } else { wr.innerHTML = '<span class="txt2">—</span>'; $('pn-wr-s').textContent = 'nenhum trade fechado ainda'; }
  }

  /* ---------- curva de capital ---------- */
  function curva(e, animar) {
    var h = (e.equity_hist || []).filter(function (x) { return typeof x.equity_total === 'number'; });
    var svg = $('pn-eq-svg'), wrap = svg.parentNode;
    var chave = h.length + ':' + (h.length ? h[h.length - 1].ts + h[h.length - 1].equity_total : '');
    if (!animar && S.curvaChave === chave && S.curvaW === svg.clientWidth) return;
    S.curvaChave = chave; S.curvaW = svg.clientWidth;
    $('pn-range').textContent = h.length ? A.ddmm(h[0].ts) + ' → ' + A.ddmm(h[h.length - 1].ts) + ' · ' + h.length + ' pontos amostrados' : 'sem pontos ainda';
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (h.length < 2) { S.geo = null; return; }
    var W = Math.max(300, svg.clientWidth || wrap.clientWidth - 20), H = 210, pad = { l: 66, r: 16, t: 18, b: 24 }, n = h.length;
    var vs = h.map(function (x) { return x.equity_total; }), lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
    var span = hi - lo || Math.max(1, hi * 0.01); lo -= span * 0.12; hi += span * 0.12;
    /* [curva] eixo X por TEMPO, não por índice. O /estado amostra a série por posição, e a série tem 15 s
       nas últimas 48 h e 5 min antes (poda do P2-11): ~80% dos pontos caem nos 2 últimos dias. Por índice,
       2 dias ocupavam 3/4 do gráfico, os 9 anteriores se espremiam no primeiro quarto e o eixo repetia
       datas ("12/11 · 12/11"). A Carteira já desenhava por tempo; agora as duas contam a mesma história. */
    var tms = h.map(function (p) { var d = A.ts(p.ts); return d ? d.getTime() : NaN; });
    for (var q = 0; q < n; q++) if (isNaN(tms[q])) tms[q] = q ? tms[q - 1] : 0;
    var t0 = tms[0], tN = tms[n - 1], dur = (tN - t0) || 1;
    var x = function (i) { return pad.l + (tms[i] - t0) / dur * (W - pad.l - pad.r); };
    var y = function (v) { return pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b); };
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var defs = svgEl('defs', {});
    defs.innerHTML = '<linearGradient id="pn-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:rgb(var(--accent-rgb));stop-opacity:.32"/><stop offset="1" style="stop-color:rgb(var(--accent-rgb));stop-opacity:0"/></linearGradient><filter id="pn-glow" x="-10%" y="-60%" width="120%" height="220%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>';
    svg.appendChild(defs);
    for (var g = 0; g < 4; g++) {
      var v = lo + (hi - lo) * (g + 0.5) / 4;
      svg.appendChild(svgEl('line', { x1: pad.l, x2: W - pad.r, y1: y(v).toFixed(1), y2: y(v).toFixed(1), 'class': 'grid' }));
      var t = svgEl('text', { x: pad.l - 8, y: (y(v) + 3.5).toFixed(1), 'class': 'ax', 'text-anchor': 'end' }); t.textContent = (hi - lo) < 20 ? F.f2(v) : F.f0(v); svg.appendChild(t);
    }
    /* marcas em instantes igualmente espaçados; com menos de 2 dias de curva a marca leva a hora */
    var nm = W < 480 ? 3 : 5, curto = dur < 2 * 86400000, usados = {};
    for (var k = 0; k < nm; k++) {
      var tk = t0 + dur * k / (nm - 1), dk = new Date(tk), txt = ('0' + dk.getDate()).slice(-2) + '/' + ('0' + (dk.getMonth() + 1)).slice(-2);
      /* a data/hora sai no relógio de SP (A.ts ancora em −03:00); getDate() local só serve se o aparelho estiver em SP */
      try { txt = new Intl.DateTimeFormat('pt-BR', curto ? { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' } : { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit' }).format(dk); } catch (e2) {}
      if (usados[txt]) continue; usados[txt] = 1;
      var t2 = svgEl('text', { x: (pad.l + (tk - t0) / dur * (W - pad.l - pad.r)).toFixed(1), y: H - 6, 'class': 'ax', 'text-anchor': k === 0 ? 'start' : k === nm - 1 ? 'end' : 'middle' }); t2.textContent = txt; svg.appendChild(t2);
    }
    var d = vs.map(function (v2, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v2).toFixed(1); }).join(' ');
    var area = svgEl('path', { d: d + ' L' + x(n - 1).toFixed(1) + ' ' + (H - pad.b) + ' L' + x(0).toFixed(1) + ' ' + (H - pad.b) + ' Z', 'class': 'area' });
    var eq = svgEl('path', { d: d, 'class': 'ln-eq' });
    var halo = svgEl('circle', { cx: x(n - 1).toFixed(1), cy: y(vs[n - 1]).toFixed(1), r: 5, 'class': 'end-halo' });
    var end = svgEl('circle', { cx: x(n - 1).toFixed(1), cy: y(vs[n - 1]).toFixed(1), r: 4, 'class': 'end' });
    var xh = svgEl('line', { x1: 0, x2: 0, y1: pad.t, y2: H - pad.b, 'class': 'xh' }); xh.style.opacity = 0;
    var hd = svgEl('circle', { r: 4, 'class': 'hd' }); hd.style.opacity = 0;
    [area, eq, halo, end, xh, hd].forEach(function (el) { svg.appendChild(el); });
    S.geo = { x: x, y: y, W: W, pad: pad, n: n, h: h, xh: xh, hd: hd };
    svg.setAttribute('aria-label', 'Curva de equity de ' + A.ddmm(h[0].ts) + ' a ' + A.ddmm(h[n - 1].ts) + ', de ' + F.brl(vs[0]) + ' a ' + F.brl(vs[n - 1]));
    if (animar && window.gsap && !A.RM) {
      var L = eq.getTotalLength(); eq.style.strokeDasharray = L; eq.style.strokeDashoffset = L;
      gsap.set(area, { opacity: 0 }); gsap.set([end, halo], { opacity: 0 });
      gsap.to(eq, { strokeDashoffset: 0, duration: 2, ease: 'power2.inOut', delay: .3, onComplete: function () { eq.style.strokeDasharray = ''; eq.style.strokeDashoffset = ''; } });
      gsap.to(area, { opacity: 1, duration: 1.2, delay: 1.2 }); gsap.to([end, halo], { opacity: 1, duration: .4, delay: 2.2 });
    }
  }
  function tipCurva(ev) {
    var g = S && S.geo; if (!g) return;
    var svg = $('pn-eq-svg'), tip = $('pn-tip'), r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * (g.W / r.width);
    /* ponto mais próximo no eixo de TEMPO (o espaçamento entre pontos não é uniforme) */
    var i = 0, best = Infinity; for (var j = 0; j < g.n; j++) { var dj = Math.abs(g.x(j) - px); if (dj < best) { best = dj; i = j; } }
    var p = g.h[i], X = g.x(i);
    g.xh.setAttribute('x1', X); g.xh.setAttribute('x2', X); g.xh.style.opacity = 1;
    g.hd.setAttribute('cx', X); g.hd.setAttribute('cy', g.y(p.equity_total)); g.hd.style.opacity = 1;
    tip.innerHTML = '<div class="mute">' + A.ddmm(p.ts) + ' ' + A.hhmm(p.ts) + '</div><div><span class="tip-k">Equity</span>' + F.brl(p.equity_total) + '</div><div><span class="tip-k">Realizado</span>' + F.brl(p.banca) + '</div>';
    tip.hidden = false;
    var left = svg.offsetLeft + X * (r.width / g.W), tw = tip.offsetWidth, ww = svg.parentNode.clientWidth, tx = '-50%';
    if (left - tw / 2 < 4) tx = '0%'; else if (left + tw / 2 > ww - 4) tx = '-100%';
    tip.style.left = left + 'px'; tip.style.transform = 'translateX(' + tx + ')';
  }
  function tipFora() { var g = S && S.geo; if (g) { g.xh.style.opacity = 0; g.hd.style.opacity = 0; } var t = $('pn-tip'); if (t) t.hidden = true; }

  /* ---------- constelação (decorativa; para fora da tela, com a aba escondida e no destroy) ----------
     Rede de pontos sobre a curva: de tempo em tempo um "pensamento" percorre as arestas e termina num nó.
     A etiqueta do fim só existe quando há dado real para ela (sinal na fila ou posição aberta, vindos do
     /estado); sem isso o percurso termina mudo. Nenhum nome ou número aqui é inventado. */
  function constelacao() {
    var cv = $('pn-terrain'), hero = $('pn-hero'), ctx = cv.getContext('2d');
    var PASSO = 230, ESFRIA = 2200, MARCA = 2600;
    var T = { cw: 0, ch: 0, t: 0, last: 0, raf: 0, visivel: true, acc: [77, 163, 255], nos: [], ar: {}, andando: [], marcas: [], prox: 0, seed: 7, k: 0 };
    function rnd() { T.seed |= 0; T.seed = T.seed + 0x6D2B79F5 | 0; var x = Math.imul(T.seed ^ T.seed >>> 15, 1 | T.seed); x = x + Math.imul(x ^ x >>> 7, 61 | x) ^ x; return ((x ^ x >>> 14) >>> 0) / 4294967296; }
    function c01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
    function rgba(a) { return 'rgba(' + T.acc[0] + ',' + T.acc[1] + ',' + T.acc[2] + ',' + a.toFixed(3) + ')'; }
    function lerTokens() { var a = A.cor('accent-rgb').split(',').map(Number); if (a.length === 3) T.acc = a; }
    /* a rede fica ACIMA do gráfico (210 px de SVG + folga); em hero baixo demais ela ocupa o que houver */
    function zona() { var topo = 58, base = T.ch - 236; if (base - topo < 80) base = T.ch - 12; return { topo: topo, alt: Math.max(20, base - topo) }; }
    function monta() {
      var N = T.cw < 640 ? 60 : 120, z = zona(), asp = T.cw / Math.max(1, z.alt), i;
      T.seed = 7; T.nos = []; T.ar = {}; T.andando = []; T.marcas = [];
      for (i = 0; i < N; i++) T.nos.push({ fx: rnd(), fy: rnd(), ph: rnd() * 6.28, sz: .8 + rnd() * 1.2, q: -1e9, viz: [] });
      T.nos.forEach(function (a, i) {
        T.nos.map(function (b, j) { return { j: j, d: Math.hypot((a.fx - b.fx) * asp, a.fy - b.fy) }; })
          .filter(function (o) { return o.j !== i; }).sort(function (p, q) { return p.d - q.d; }).slice(0, 3)
          .forEach(function (o) { var lo = Math.min(i, o.j), hi = Math.max(i, o.j); T.ar[lo + '-' + hi] = { a: lo, b: hi, q: -1e9 }; });
      });
      Object.keys(T.ar).forEach(function (k) { var e = T.ar[k]; T.nos[e.a].viz.push(e.b); T.nos[e.b].viz.push(e.a); });
    }
    function size() { var dpr = Math.min(2, window.devicePixelRatio || 1); T.cw = hero.clientWidth; T.ch = hero.clientHeight; cv.width = Math.max(1, Math.round(T.cw * dpr)); cv.height = Math.max(1, Math.round(T.ch * dpr)); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); monta(); }
    /* o que o percurso "decidiu": roda pelos sinais da fila e pelas posições abertas do /estado, nessa ordem */
    function etiqueta() {
      var e = (S && S.estado) || {}, l = (e.pendentes || []).map(function (s) { return F.par(s.ativo) + ' · ' + String(s.direcao || '').toLowerCase() + ' · ' + Math.round(s.conviccao || 0); })
        .concat((e.posicoes || []).map(function (p) { return F.par(p.ativo) + ' · ' + String(p.direcao || '').toLowerCase() + ' · aberta'; }));
      return l.length ? l[T.k++ % l.length] : '';
    }
    function ponto(x, y, r, a) { ctx.fillStyle = rgba(a); ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill(); }
    function reta(x1, y1, x2, y2, a, w) { ctx.strokeStyle = rgba(a); ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); }
    function draw() {
      var t = T.t * 1000, z = zona(), nos = T.nos, k;
      ctx.clearRect(0, 0, T.cw, T.ch);
      nos.forEach(function (n) { n.x = 30 + n.fx * (T.cw - 60) + Math.sin(t * .0005 + n.ph) * 7; n.y = z.topo + n.fy * z.alt + Math.cos(t * .0004 + n.ph * 1.7) * 7; });
      if (t > T.prox && T.andando.length < 3 && nos.length) {
        T.prox = t + 600 + rnd() * 900;
        var cur = Math.floor(rnd() * nos.length), cam = [cur], len = 5 + Math.floor(rnd() * 4);
        while (cam.length < len) { var op = nos[cur].viz.filter(function (j) { return cam.indexOf(j) < 0; }); if (!op.length) break; cur = op[Math.floor(rnd() * op.length)]; cam.push(cur); }
        if (cam.length >= 3) { nos[cam[0]].q = t; T.andando.push({ cam: cam, t0: t, feito: 0 }); }
      }
      for (k in T.ar) { var e = T.ar[k]; reta(nos[e.a].x, nos[e.a].y, nos[e.b].x, nos[e.b].y, .06 + .6 * c01(1 - (t - e.q) / ESFRIA), 1); }
      T.andando = T.andando.filter(function (w) {
        var kk = Math.floor((t - w.t0) / PASSO), f = ((t - w.t0) % PASSO) / PASSO, fim = w.cam.length - 1;
        while (w.feito < Math.min(kk, fim)) { var a = w.cam[w.feito], b = w.cam[w.feito + 1]; T.ar[Math.min(a, b) + '-' + Math.max(a, b)].q = t; nos[b].q = t; w.feito++; }
        if (kk >= fim) { T.marcas.push({ n: w.cam[fim], t: t, txt: etiqueta() }); return false; }
        var p = nos[w.cam[kk]], q = nos[w.cam[kk + 1]], x = p.x + (q.x - p.x) * f, y = p.y + (q.y - p.y) * f;
        reta(p.x, p.y, x, y, .8, 1.2);
        ctx.save(); ctx.shadowColor = rgba(.9); ctx.shadowBlur = 10; ponto(x, y, 2.4, 1); ctx.restore();
        return true;
      });
      nos.forEach(function (n) { var h = c01(1 - (t - n.q) / ESFRIA); ponto(n.x, n.y, n.sz + h * 1.6, .3 + .7 * h); });
      T.marcas = T.marcas.filter(function (m) {
        var p = (t - m.t) / MARCA; if (p >= 1) return false;
        var n = nos[m.n], a = Math.min(1, p * 6) * c01((1 - p) * 3);
        ctx.strokeStyle = rgba((1 - p) * .7); ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(n.x, n.y, 5 + p * 18, 0, 6.2832); ctx.stroke();
        ponto(n.x, n.y, 3.2, a);
        if (m.txt) {
          var dir = n.x > T.cw - 200;
          ctx.font = '11px ' + (A.cor('f-mono') || 'ui-monospace,Consolas,monospace'); ctx.textBaseline = 'middle'; ctx.textAlign = dir ? 'right' : 'left';
          ctx.fillStyle = rgba(a * .95); ctx.fillText(m.txt, dir ? n.x - 14 : n.x + 14, n.y - 12);
        }
        return true;
      });
    }
    function rodando() { return !A.RM && T.visivel && !document.hidden && S && !S.morto; }
    function frame(now) { T.raf = 0; if (!rodando()) return; var dt = T.last ? Math.min(.05, (now - T.last) / 1000) : .016; T.last = now; T.t += dt; draw(); T.raf = requestAnimationFrame(frame); }
    function liga() { if (rodando() && !T.raf) { T.last = 0; T.raf = requestAnimationFrame(frame); } }
    function desliga() { if (T.raf) cancelAnimationFrame(T.raf); T.raf = 0; }
    var vis = function () { if (document.hidden) desliga(); else liga(); };
    document.addEventListener('visibilitychange', vis);
    var io = window.IntersectionObserver ? new IntersectionObserver(function (es) { T.visivel = es[es.length - 1].isIntersecting; if (T.visivel) liga(); else desliga(); }) : null;
    if (io) io.observe(hero);
    var rt = 0, ro = window.ResizeObserver ? new ResizeObserver(function () { clearTimeout(rt); rt = setTimeout(function () { if (!S) return; size(); draw(); if (S.estado) curva(S.estado, false); }, 120); }) : null;
    if (ro) ro.observe(hero);
    var offPal = A.on('paleta', function () { lerTokens(); draw(); });
    lerTokens(); size(); draw(); liga();
    return function () { desliga(); clearTimeout(rt); if (io) io.disconnect(); if (ro) ro.disconnect(); offPal(); document.removeEventListener('visibilitychange', vis); };
  }

  /* ---------- win rate, Apollo, trava ---------- */
  function gauge(e) {
    var m = e.metricas || {}, wr = m.n_trades ? (m.win_rate || 0) : 0;
    var C = 2 * Math.PI * 50, FILL = C * .75 * Math.min(1, wr / 100), g = $('pn-gfg');
    if (S.gaugeV !== FILL) {
      if (S.gaugeV == null && window.gsap && !A.RM) { var o = { v: 0 }; gsap.to(o, { v: FILL, duration: 1.5, ease: 'power3.out', onUpdate: function () { g.setAttribute('stroke-dasharray', o.v.toFixed(2) + ' ' + C.toFixed(1)); } }); }
      else g.setAttribute('stroke-dasharray', FILL.toFixed(2) + ' ' + C.toFixed(1));
      g.style.opacity = FILL > 0 ? 1 : 0;
      S.gaugeV = FILL;
    }
    $('pn-g-v').textContent = m.n_trades ? F.f0(wr) + '%' : '—';
    $('pn-gauge-lbl').setAttribute('aria-label', m.n_trades ? 'Win rate de ' + F.f0(wr) + '% em ' + m.n_trades + ' trades' : 'Sem trades fechados');
    var payoff = m.perda_media ? Math.abs(m.ganho_medio / m.perda_media) : 0, xr = A.expR(m);
    var rows = [['Payoff', m.n_trades ? F.f2(payoff) : '—', ''], ['Trades', String(m.n_trades || 0), ''],
      ['Expectativa' + (xr.n ? ' <span class="mute" style="font-size:10.5px">(' + xr.n + ')</span>' : ''), xr.txt, F.cls(xr.v)],
      ['Pior sequência', S.piorSeq == null ? '…' : S.piorSeq + (S.piorSeq === 1 ? ' perda' : ' perdas'), S.piorSeq ? 'neg' : '']];
    $('pn-g-meta').innerHTML = rows.map(function (r) { return '<div class="row"><span>' + r[0] + '</span><span class="' + r[2] + '">' + r[1] + '</span></div>'; }).join('') +
      /* [CLS] enquanto o /trades não chega (piorSeq == null, o mesmo "…" de cima) a linha fica, para o card não encolher e crescer de novo */
      (S.piorSeqN || S.piorSeq == null ? '<div class="row"><span class="mute" style="font-size:10.5px">sequência nos últimos ' + (S.piorSeqN || '…') + ' trades</span><span></span></div>' : '');
  }
  function robo(e) {
    var cfg = e.config || {}, on = String(cfg.auto_trade) === '1', rg = e.risco || {};
    $('pn-robo-st').innerHTML = '<span class="led' + (on ? '' : ' off') + '" aria-hidden="true"></span><b style="color:' + (on ? 'var(--accent)' : 'var(--mute)') + '">' + (on ? 'LIGADO' : 'DESLIGADO') + '</b>';
    var a = e.auto || {}, ult = '—';
    if (a.ts) ult = A.hhmm(a.ts) + ' · ' + ((a.abertos || []).length ? a.abertos.length + ' aberto(s)' : (a.fechados || []).length ? a.fechados.length + ' fechado(s)' : (a.motivo || 'nada a fazer'));
    else if (a.motivo) ult = a.motivo;
    var lev = cfg.auto_lev_modo === 'fixo' ? cfg.alavancagem_padrao + 'x fixa' : cfg.auto_lev_modo === 'risco' ? 'pela conta (' + cfg.auto_lev_min + '–' + cfg.auto_lev_max + 'x)' : 'por convicção (' + cfg.auto_lev_min + '–' + cfg.auto_lev_max + 'x)';
    var kv = [['Modo', cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado'], ['Risco / trade', F.f2((parseFloat(cfg.risco_por_trade) || 0) * 100) + '%'], ['Alavancagem', lev], ['Conv. mínima', cfg.auto_conviccao_min], ['Última ação', ult]];
    $('pn-robo-kv').innerHTML = kv.map(function (k) { return '<dt>' + k[0] + '</dt><dd>' + A.esc(k[1]) + '</dd>'; }).join('');
    $('pn-guards').innerHTML =
      '<span class="guard' + (rg.teto_aberto ? ' hot' : '') + '">teto de risco aberto ' + p1(rg.risco_aberto_pct) + '%</span>' +
      '<span class="guard' + (rg.trava_dia ? ' hot' : '') + '">trava diária ' + p1(rg.limite_pct) + '%</span>' +
      '<span class="guard">margem máx. ' + p1((parseFloat(cfg.exposicao_max) || 0) * 100) + '%</span>' +
      '<span class="guard' + (String(cfg.trailing_ativo) === '1' ? '' : ' off') + '">trailing ' + (String(cfg.trailing_ativo) === '1' ? (cfg.trailing_unidade === 'R' ? cfg.trailing_arma_r + 'R/' + cfg.trailing_dist_r + 'R' : '%') : 'desligado') + '</span>';
    var b = $('pn-auto'); b.textContent = on ? 'Pausar' : 'Ligar'; b.className = 'btn ' + (on ? 'ghost' : 'primary');
  }
  async function toggleAuto() {
    var e = A.estado; if (!e) return; var cfg = e.config || {}, on = String(cfg.auto_trade) === '1';
    if (!on) {
      var ok = await A.dialogo({ titulo: 'Ligar o Apollo', ok: 'Ligar',
        corpo: '<p>Ele passa a abrir e fechar posições sozinho na <b>' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</b>, com a config de agora:</p><div class="diff">' +
          '<div><span>risco por trade</span><b>' + F.f2((parseFloat(cfg.risco_por_trade) || 0) * 100) + '%</b></div><div><span>convicção mínima</span><b>' + A.esc(cfg.auto_conviccao_min) + '</b></div>' +
          '<div><span>máx. posições</span><b>' + A.esc(cfg.auto_max_posicoes) + '</b></div><div><span>alavancagem</span><b>' + A.esc(cfg.auto_lev_modo) + '</b></div><div><span>execução</span><b>' + A.esc(cfg.exec_modo) + '</b></div></div>' +
          '<p class="mute">Trava diária e teto de risco aberto continuam valendo. Para mudar a config, use o módulo Apollo antes de ligar.</p>' });
      if (!ok) return;
    }
    try { await A.api('/auto', { auto_trade: on ? '0' : '1' }); A.toast(on ? 'Apollo pausado: posições abertas seguem com stop' : 'Apollo ligado'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }
  function trava(e) {
    var rg = e.risco || {}, perda = Math.max(0, -(rg.pnl_dia || 0)), pct = rg.limite_rs ? Math.min(100, perda / rg.limite_rs * 100) : 0;
    var st = $('pn-trava-st'); st.textContent = rg.trava_dia ? 'disparada' : 'livre'; st.className = 'state' + (rg.trava_dia ? ' neg' : '');
    var base = e.equity_total - (rg.pnl_dia || 0);
    $('pn-trava').innerHTML = '<div class="kpi-lbl">consumido hoje</div><div class="trava-val ' + (perda > 0 ? 'neg' : '') + '">' + F.brl(perda) + ' <span class="txt2" style="font-size:13px;font-weight:400">de ' + F.brl(rg.limite_rs) + '</span></div>' +
      '<div class="prog neg" style="margin-top:10px" aria-hidden="true"><i style="--w:' + pct.toFixed(1) + '%"></i></div>' +
      '<div class="trava-rows"><div><span>Limite</span><span>−' + p1(rg.limite_pct) + '% do equity do início do dia</span></div><div><span>Base do dia</span><span>' + F.brl(base) + '</span></div>' +
      '<div><span>Risco aberto</span><span>' + F.brl(rg.risco_aberto_rs) + ' de ' + F.brl(rg.risco_aberto_max_rs) + '</span></div><div><span>Solta</span><span>na virada do dia (só leitura)</span></div></div>';
  }

  /* ---------- sinais, posições, ordens, journal ---------- */
  function sinais(e) {
    var l = e.pendentes || []; $('pn-sig-n').textContent = l.length;
    var el = $('pn-sinais');
    if (!l.length) { el.innerHTML = '<div class="empty">Nenhum sinal na fila. O motor está varrendo; quando um passar nos portões ele aparece aqui.</div>'; return; }
    var ttl = (parseFloat((e.config || {}).auto_freshness_min) || 12);
    el.innerHTML = '<ul class="sig-list">' + l.slice(0, 6).map(function (s) {
      var c = Math.round(s.conviccao || 0);
      return '<li class="sig"><div class="sig-top"><span class="mono strong">' + A.esc(F.par(s.ativo)) + '</span><span class="chip ' + (s.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(s.direcao) + '</span><span class="chip neutro">' + A.esc(s.tf || '') + '</span>' +
        '<span class="sig-exp" title="o auto-trade só opera sinal com até ' + ttl + ' min">há ' + A.idade(s.ts) + '</span></div>' +
        '<div class="sig-conv"><span>convicção</span><span class="conv-num">' + c + '</span><div class="bar"><i style="--w:' + c + '%"></i></div></div>' +
        '<div class="sig-why">' + A.esc((s.motivos || '').split(', ').slice(0, 3).join(' · ') || s.tipo || '') + '</div>' +
        '<div class="sig-act"><button type="button" class="btn primary sm" data-conf="' + s.id + '">Confirmar</button><button type="button" class="btn ghost sm" data-pular="' + s.id + '">Pular</button><a class="btn ghost sm" href="#operar">ver no Operar</a></div></li>';
    }).join('') + '</ul>' + (l.length > 6 ? '<div class="mute" style="font-size:11.5px;margin-top:8px">+' + (l.length - 6) + ' na fila · <a href="#operar" style="color:var(--accent)">todos no Operar</a></div>' : '');
  }
  function anotaPnl(e) {
    var vivos = {};
    (e.posicoes || []).forEach(function (p) { vivos[p.id] = 1; var v = S.pnlHist[p.id] || (S.pnlHist[p.id] = [0]); if (v[v.length - 1] !== p.pnl) v.push(p.pnl || 0); if (v.length > 60) v.splice(1, v.length - 60); });
    Object.keys(S.pnlHist).forEach(function (k) { if (!vivos[k]) delete S.pnlHist[k]; });
  }
  function posicoes(e) {
    var l = e.posicoes || [], tot = l.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
    $('pn-pos-n').innerHTML = l.length + (l.length ? ' · <span class="' + F.cls(tot) + '">' + F.money(tot) + '</span>' : '');
    var el = $('pn-pos');
    if (!l.length) { el.innerHTML = '<div class="empty">Nenhuma posição aberta.</div>'; return; }
    /* [celular] Na tabela de 10 colunas o Fechar (preso à direita) cobria a coluna de P&L, que é o número
       que importa: em 390 px sobravam Par, Lado, Lev e Entrada. Abaixo de 640 px cada posição vira um
       cartão com o P&L em destaque. O poll redesenha a cada 3 s, então girar o aparelho troca o formato. */
    if (window.matchMedia && matchMedia('(max-width: 640px)').matches) {
      el.innerHTML = '<div class="pc-list">' + l.map(function (p) {
        var roe = p.valor_reais ? p.pnl / p.valor_reais * 100 : 0, sd = S.saidas[p.id];
        var mov = p.stop_abertura != null && Math.abs(p.stop - p.stop_abertura) > 1e-12;
        return '<div class="pc"><div class="pc-top"><span class="mono strong">' + A.esc(F.par(p.ativo)) + '</span><span class="chip ' + (p.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(p.direcao) + ' ' + A.esc(p.alavancagem) + 'x</span>' +
          '<span class="pc-pnl ' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '<small>' + F.pct(roe, 1) + ' ROE</small></span></div>' +
          '<dl class="pc-kv"><div><dt>entrada</dt><dd>' + F.px(p.entrada) + '</dd></div><div><dt>atual</dt><dd>' + F.px(p.preco_atual) + '</dd></div><div><dt>stop' + (mov ? ' · trailing' : '') + '</dt><dd class="neg">' + F.px(p.stop) + '</dd></div>' +
          '<div><dt>margem</dt><dd>' + F.brl(p.valor_reais) + '</dd></div><div><dt>idade</dt><dd>' + A.idade(p.aberto_em) + '</dd></div><div><dt>evolução</dt><dd>' + A.spark(S.pnlHist[p.id]) + '</dd></div></dl>' +
          (sd && sd.acao ? '<div class="pc-saida">' + A.esc(sd.acao) + '</div>' : '') +
          '<button type="button" class="btn danger sm" data-fechar="' + p.id + '">Fechar a mercado</button></div>';
      }).join('') + '</div>';
      return;
    }
    el.innerHTML = '<div class="tablewrap"><table class="tbl"><thead><tr><th>Par</th><th>Lado</th><th>Lev</th><th class="num">Entrada</th><th class="num">Atual</th><th class="num">P&amp;L · ROE</th><th class="num">Stop</th><th>Idade</th><th>Evolução</th><th></th></tr></thead><tbody>' +
      l.map(function (p) {
        var roe = p.valor_reais ? p.pnl / p.valor_reais * 100 : 0, sd = S.saidas[p.id];
        var mov = p.stop_abertura != null && Math.abs(p.stop - p.stop_abertura) > 1e-12;
        return '<tr><td class="mono strong">' + A.esc(F.par(p.ativo)) + '</td><td><span class="chip ' + (p.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(p.direcao) + '</span></td><td class="mono">' + A.esc(p.alavancagem) + 'x</td>' +
          '<td class="mono num">' + F.px(p.entrada) + '</td><td class="mono num">' + F.px(p.preco_atual) + '</td>' +
          '<td class="mono num ' + F.cls(p.pnl) + '">' + F.money(p.pnl) + ' · ' + F.pct(roe, 1) + '</td>' +
          '<td class="mono num">' + F.px(p.stop) + (mov ? '<span class="sub">movido pelo trailing</span>' : '') + '</td><td class="mono">' + A.idade(p.aberto_em) + '</td>' +
          '<td>' + A.spark(S.pnlHist[p.id]) + '</td><td><button type="button" class="btn danger sm" data-fechar="' + p.id + '">Fechar</button></td></tr>' +
          (sd && sd.acao ? '<tr class="saida"><td colspan="10">' + A.esc(sd.acao) + '</td></tr>' : '');
      }).join('') + '</tbody></table></div>';
  }
  function ordens(e) {
    var l = e.ordens || []; $('pn-ord-n').textContent = l.length + ' · post-only';
    var el = $('pn-ord');
    if (!l.length) { el.innerHTML = '<div class="empty">Nenhuma ordem descansando.' + ((e.config || {}).exec_modo === 'post_only' ? '' : ' Execução atual: a mercado.') + '</div>'; return; }
    el.innerHTML = '<div class="ord">' + l.map(function (o) {
      var c = A.ts(o.criada_em), x = A.ts(o.expira_em), tot = c && x ? x - c : 0, pas = c ? Date.now() - c : 0, falta = x ? Math.max(0, Math.round((x - Date.now()) / 60000)) : null;
      return '<div class="ord-item"><div class="ord-top"><span class="mono strong">' + A.esc(F.par(o.ativo)) + '</span><span class="chip ' + (o.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(o.direcao) + '</span><span class="px">' + F.px(o.preco_limite) + '</span></div>' +
        '<div class="ord-meta">descansa há ' + A.idade(o.criada_em) + (falta != null ? ' · expira em ' + falta + ' min' : '') + ' · R$ ' + F.f0(o.valor_reais) + ' · ' + A.esc(o.alavancagem) + 'x</div>' +
        '<div class="prog" aria-hidden="true"><i style="--w:' + (tot ? Math.min(100, pas / tot * 100) : 0).toFixed(1) + '%"></i></div></div>';
    }).join('') + '<div class="ord-note">ordem que expira não devolve o sinal · maker só na entrada · já conta nos tetos</div></div>';
  }
  function journal(e) {
    var l = (e.trades || []).slice(0, 5), el = $('pn-jr');
    if (!l.length) { el.innerHTML = '<li><span class="mute">Nenhum trade fechado ainda.</span></li>'; return; }
    el.innerHTML = l.map(function (t) {
      return '<li><span class="when">' + A.ddmm(t.fechado_em) + ' ' + A.hhmm(t.fechado_em) + '</span><span class="what"><span class="mono strong">' + A.esc(F.par(t.ativo)) + '</span><span class="chip ' + (t.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(t.direcao) + '</span><span class="how">' + A.esc(t.motivo_saida || '') + '</span></span><span class="amt ' + F.cls(t.pnl_reais) + '">' + F.money(t.pnl_reais) + '</span></li>';
    }).join('');
  }

  /* ---------- Mercado (60 s, só montado) ---------- */
  async function mercado() {
    var r = await Promise.all([A.api('/sentimento').catch(function () { return null; }), A.api('/funding').catch(function () { return null; })]);
    if (!S) return;
    var s = r[0], fu = r[1], h = '';
    if (s && s.fear_greed) h += '<div class="mkt-row"><span class="k">Fear &amp; Greed</span><span class="v">' + s.fear_greed.valor + ' <span class="txt2">' + A.esc(s.fear_greed.label) + '</span></span></div><div class="fg" aria-hidden="true"><i style="--w:' + s.fear_greed.valor + '%"></i></div>';
    if (s && s.breadth) h += '<div class="mkt-row"><span class="k">Breadth</span><span class="v">' + s.breadth.pct_subindo + '% <span class="txt2">das ' + s.breadth.n + ' subindo hoje</span></span></div><div class="mkt-row"><span class="k">Variação média</span><span class="v ' + F.cls(s.breadth.variacao_media) + '">' + F.pct(s.breadth.variacao_media) + '</span></div>';
    if (fu && fu.length) {
      var med = fu.reduce(function (a, x) { return a + (x.funding_pct || 0); }, 0) / fu.length;
      var neg = fu.slice().sort(function (a, b) { return a.funding_pct - b.funding_pct; }).slice(0, 2);
      h += '<div class="mkt-row"><span class="k">Funding médio</span><span class="v">' + F.pct(med, 4) + ' <span class="txt2">/ 8h</span></span></div>';
      h += '<div class="mkt-sub">funding mais negativo: ' + neg.map(function (x) { return A.esc(F.base(x.ativo)) + ' ' + F.pct(x.funding_pct, 4); }).join(' · ') + '</div>';
    }
    $('pn-mkt').innerHTML = h || '<div class="empty">Sentimento e funding indisponíveis agora.</div>';
    $('pn-mkt-t').textContent = 'às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }

  /* ---------- Dia a dia (P&L FECHADO por dia, de /trades) ----------
     Agrupado pelo PREFIXO AAAA-MM-DD de `fechado_em` (hora de São Paulo, naive): toISOString() mudaria o
     dia depois das 21h. Se o /trades veio no teto (500), o dia do trade mais antigo pode estar incompleto,
     então a cobertura começa no dia SEGUINTE e o período coberto é escrito na tela. Dia fora da cobertura
     não é desenhado: dia vazio fingindo zero seria número inventado. */
  var LIM = 500, WD = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'], MN = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  function chaveD(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function dataDe(k) { return new Date(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8, 10)); }
  /* /trades?limite=500 é a resposta mais pesada da tela: só relê quando um trade fechou (o /estado
     já traz o último id e a contagem) ou o dia virou. Antes era a cada 60 s, mudando ou não. */
  function diaADiaSeMudou() {
    var e = S && (S.estado || A.estado); if (!e) return;
    var sig = ((e.metricas || {}).n_trades || 0) + '|' + (((e.trades || [])[0] || {}).id || '') + '|' + A.hoje();
    if (sig === S.sigTr) return; S.sigTr = sig; diaADia();
  }
  async function diaADia() {
    if (S && !S.sigTr) { var e0 = S.estado || A.estado || {}; S.sigTr = ((e0.metricas || {}).n_trades || 0) + '|' + (((e0.trades || [])[0] || {}).id || '') + '|' + A.hoje(); }
    var tr;
    try { tr = await A.api('/trades?limite=' + LIM); } catch (err) { if (S) $('pn-dd-body').innerHTML = '<div class="empty">Não consegui ler o /trades agora (' + A.esc(A.erroTxt(err)) + ').</div>'; return; }
    if (!S) return;
    var e = S.estado || A.estado || {};
    tr = (tr || []).filter(function (t) { return t.fechado_em; }).sort(function (a, b) { return a.fechado_em < b.fechado_em ? -1 : 1; });
    /* pior sequência de perdas consecutivas, sobre os trades lidos */
    var run = 0, pior = 0; tr.forEach(function (t) { if (t.pnl_reais < 0) { run++; if (run > pior) pior = run; } else run = 0; });
    S.piorSeq = pior; S.piorSeqN = tr.length; if (S.estado) gauge(S.estado);
    var mk = A.hoje().slice(0, 7);
    S.mesReal = tr.reduce(function (a, t) { return t.fechado_em.slice(0, 7) === mk ? a + (t.pnl_reais || 0) : a; }, 0);
    S.mesCompleto = tr.length < LIM || tr[0].fechado_em.slice(0, 7) < mk; S.mesDesde = tr.length ? A.ddmm(tr[0].fechado_em) : '';
    if (S.estado) kpis(S.estado);
    var por = {};
    tr.forEach(function (t) { var k = A.dia(t.fechado_em); var d = por[k] || (por[k] = { pnl: 0, n: 0 }); d.pnl += t.pnl_reais || 0; d.n++; });
    var hojeK = A.hoje(), hojeD = dataDe(hojeK);
    var noTeto = tr.length >= LIM, ini;
    if (!tr.length) {
      var h0 = (e.equity_hist || [])[0]; ini = h0 ? A.dia(h0.ts) : hojeK;
    } else if (noTeto) { var d0 = dataDe(A.dia(tr[0].fechado_em)); d0.setDate(d0.getDate() + 1); ini = chaveD(d0); }
    else { var h1 = (e.equity_hist || [])[0]; ini = A.dia(tr[0].fechado_em); if (h1 && A.dia(h1.ts) < ini) ini = A.dia(h1.ts); }
    var min = new Date(hojeD); min.setDate(min.getDate() - 69); if (dataDe(ini) < min) ini = chaveD(min);
    var dias = [], cur = dataDe(ini);
    while (cur <= hojeD) { var k = chaveD(cur), x = por[k] || { pnl: 0, n: 0 }; dias.push({ k: k, d: new Date(cur), pnl: Math.round(x.pnl * 100) / 100, n: x.n }); cur.setDate(cur.getDate() + 1); }
    var rg = e.risco || {};
    dias.forEach(function (x) { x.trava = x.k === hojeK && !!rg.trava_dia; });
    var N = dias.length, last = dias[N - 1];
    $('pn-dd-sub').textContent = 'P&L fechado por dia (hoje: só o que já fechou; o P&L do dia lá em cima soma o aberto) · ' + A.ddmm(ini) + ' → ' + A.ddmm(hojeK) + (noTeto ? ' · cobertura dos 500 trades mais recentes' : '') + ' · fonte /trades';
    var com = dias.filter(function (x) { return x.n; });
    if (!com.length) { $('pn-dd-streak').textContent = 'sem trade no período'; $('pn-dd-body').innerHTML = '<div class="empty">Nenhum trade fechado entre ' + A.ddmm(ini) + ' e hoje. O calendário aparece com o primeiro fechamento.</div>'; return; }
    /* sequência atual: dias com trade de mesmo sinal, contando de trás; dia sem trade é pulado */
    var dir = 0, cnt = 0;
    for (var j = N - 1; j >= 0; j--) { var dj = dias[j]; if (!dj.n) continue; var sg = dj.pnl > 0 ? 1 : dj.pnl < 0 ? -1 : 0; if (!dir) dir = sg; if (sg !== dir || !sg) break; cnt++; }
    var best = 0, r2 = 0, posN = 0, negN = 0, bestD = com[0], worstD = com[0], somaPos = 0;
    com.forEach(function (x) { if (x.pnl > 0) { r2++; posN++; if (r2 > best) best = r2; } else { r2 = 0; if (x.pnl < 0) negN++; } if (x.pnl > bestD.pnl) bestD = x; if (x.pnl < worstD.pnl) worstD = x; somaPos += x.pnl; });
    var stk = $('pn-dd-streak'); stk.textContent = cnt ? 'sequência: ' + cnt + (dir > 0 ? (cnt > 1 ? ' dias positivos' : ' dia positivo') : (cnt > 1 ? ' dias negativos' : ' dia negativo')) : '—'; stk.className = 'count' + (dir < 0 ? ' neg' : '');
    var stats = [['sequência atual', cnt + (cnt === 1 ? ' dia' : ' dias'), dir > 0 ? 'positiva' : dir < 0 ? 'negativa' : '—', dir > 0 ? 'pos' : dir < 0 ? 'neg' : ''],
      ['melhor sequência', best + (best === 1 ? ' dia' : ' dias'), 'positivos seguidos', 'pos'],
      ['dias + × −', posN + ' × ' + negN, (N - com.length) + ' sem trade', ''],
      ['melhor dia', F.money(bestD.pnl), A.ddmm(bestD.k) + ' · ' + bestD.n + ' trades', 'pos'],
      ['pior dia', F.money(worstD.pnl), A.ddmm(worstD.k) + ' · ' + worstD.n + ' trades', 'neg'],
      ['média por dia', F.money(somaPos / com.length), com.length + ' dias com trade', F.cls(somaPos)]];
    var mx = Math.max.apply(null, com.map(function (x) { return Math.abs(x.pnl); })) || 1;
    var cls = function (x) { if (!x.n || !x.pnl) return 'z'; var a = Math.abs(x.pnl) / mx, k2 = a < .25 ? 1 : a < .6 ? 2 : 3; return (x.pnl > 0 ? 'p' : 'n') + k2; };
    /* calendário: colunas = semanas seg→dom; células antes do início e depois de hoje ficam invisíveis */
    var off = (dias[0].d.getDay() + 6) % 7, cells = '', months = '', lastM = -1, totalCells = off + N, weeks = Math.ceil(totalCells / 7);
    for (var w = 0; w < weeks; w++) { var di = Math.max(0, w * 7 - off), m = dias[Math.min(N - 1, di)].d.getMonth(); months += '<span>' + (m !== lastM ? MN[m] : '') + '</span>'; lastM = m; }
    for (var c = 0; c < weeks * 7; c++) {
      var i2 = c - off, x2 = dias[i2];
      if (!x2) { cells += '<span class="dd-c fora" aria-hidden="true"></span>'; continue; }
      var lab = WD[x2.d.getDay()] + ' ' + A.ddmm(x2.k) + ': ' + (x2.n ? F.money(x2.pnl) + ', ' + x2.n + (x2.n === 1 ? ' trade' : ' trades') : 'sem trade') + (x2.trava ? ', trava disparada' : '');
      cells += '<button type="button" class="dd-c ' + cls(x2) + (x2.trava ? ' trava' : '') + (x2.k === hojeK ? ' today' : '') + '" data-i="' + i2 + '" aria-label="' + lab + '"></button>';
    }
    var cal = '<div></div><div class="dd-months">' + months + '</div><div class="dd-days">' + ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'].map(function (x) { return '<span>' + x + '</span>'; }).join('') + '</div><div class="dd-cells">' + cells + '</div>';
    var L14 = dias.slice(-14), mx14 = Math.max.apply(null, L14.map(function (x) { return Math.abs(x.pnl); })) || 1;
    var bars = L14.map(function (x, i) {
      var hh = x.pnl === 0 ? 0 : Math.max(3, Math.round(Math.abs(x.pnl) / mx14 * 50));
      var b = x.pnl === 0 ? '' : '<i class="' + (x.pnl > 0 ? 'pos' : 'neg') + '" style="height:' + hh + '%"></i>';
      return '<div class="dd-b' + (i === L14.length - 1 ? ' today' : '') + '"><span class="v ' + (x.pnl > 0 ? 'pos' : x.pnl < 0 ? 'neg' : 'mute') + '">' + (x.n ? F.money(x.pnl).replace(/R\$\s/, '') : '·') + '</span><div class="t">' + b + '</div><span class="d">' + A.ddmm(x.k) + '</span></div>';
    }).join('');
    /* totais: últimas 4 semanas (seg→dom) e os meses do período; mês que começa antes da cobertura é parcial */
    var wk = {}, ord = [];
    dias.forEach(function (x) { var mon = new Date(x.d); mon.setDate(x.d.getDate() - ((x.d.getDay() + 6) % 7)); var kk = chaveD(mon); if (!wk[kk]) { wk[kk] = { de: x.k, ate: x.k, s: 0 }; ord.push(kk); } wk[kk].ate = x.k; wk[kk].s += x.pnl; });
    var tot = ord.slice(-4).reverse().map(function (kk) { var s = wk[kk]; return '<span>sem. ' + A.ddmm(s.de) + '–' + A.ddmm(s.ate) + ' <b class="' + F.cls(s.s) + '">' + F.money(s.s) + '</b></span>'; });
    var meses = {}, mOrd = [];
    dias.forEach(function (x) { var mk = x.k.slice(0, 7); if (!meses[mk]) { meses[mk] = { s: 0, parcial: x.k.slice(8) !== '01' }; mOrd.push(mk); } meses[mk].s += x.pnl; });
    mOrd.slice(-2).forEach(function (mk) { var mm = meses[mk]; tot.push('<span>' + MN[+mk.slice(5) - 1] + (mm.parcial ? ' (parcial)' : '') + ' <b class="' + F.cls(mm.s) + '">' + F.money(mm.s) + '</b></span>'); });
    $('pn-dd-body').innerHTML = '<div class="dd-stats" style="margin-bottom:14px">' + stats.map(function (s) { return '<div class="dd-stat"><div class="k">' + s[0] + '</div><div class="v ' + s[3] + '">' + s[1] + '</div><div class="s">' + s[2] + '</div></div>'; }).join('') + '</div>' +
      '<div class="dd-cal-wrap"><div class="dd-cal">' + cal + '</div></div>' +
      '<div class="dd-legend" aria-hidden="true" style="margin:8px 0 14px"><span><i class="dd-lg-p"></i>lucro</span><span><i class="dd-lg-n"></i>prejuízo</span><span><i class="dd-lg-z"></i>sem trade</span><span><i class="dd-lg-h"></i>hoje</span><span>intensidade = tamanho do resultado no período</span>' + (rg.trava_dia ? '<span><i style="background:var(--warn)"></i>trava disparada hoje</span>' : '') + '</div>' +
      '<div class="dd-sub" style="margin-bottom:8px">últimos 14 dias</div><div class="dd-bars">' + bars + '</div><div class="dd-tot" style="margin-top:12px">' + tot.join('') + '</div>';
    S.dias = dias;
    if (!S.ddAnimado && window.gsap && !A.RM) { S.ddAnimado = true; gsap.from(S.root.querySelectorAll('#pn-dd .dd-c:not(.fora)'), { scale: .5, opacity: 0, duration: .45, stagger: .006, ease: 'power2.out', clearProps: 'transform,opacity' }); }
  }
  function ddTip(ev) {
    var b = ev.target.closest && ev.target.closest('.dd-c'); if (!b || b.classList.contains('fora') || !S || !S.dias) return;
    var x = S.dias[+b.getAttribute('data-i')]; if (!x) return;
    var tip = $('pn-dd-tip'), dd = $('pn-dd');
    tip.innerHTML = '<div class="mute">' + WD[x.d.getDay()] + ' · ' + A.ddmm(x.k) + '</div>' + (x.n ? '<div class="' + F.cls(x.pnl) + '"><span class="tip-k">P&amp;L</span>' + F.money(x.pnl) + '</div><div><span class="tip-k">trades</span>' + x.n + '</div>' : '<div><span class="tip-k">P&amp;L</span>sem trade</div>') + (x.trava ? '<div class="warn"><span class="tip-k">trava</span>disparada</div>' : '');
    tip.hidden = false;
    var br = b.getBoundingClientRect(), dr = dd.getBoundingClientRect(), left = br.left - dr.left + br.width / 2, top = br.top - dr.top - tip.offsetHeight - 8;
    var tw = tip.offsetWidth, tx = '-50%'; if (left - tw / 2 < 6) tx = '0%'; else if (left + tw / 2 > dd.clientWidth - 6) tx = '-100%';
    tip.style.left = left + 'px'; tip.style.top = Math.max(4, top) + 'px'; tip.style.transform = 'translateX(' + tx + ')';
  }

  /* ---------- /saidas (8 s): recomendação de saída por posição ---------- */
  async function saidas() {
    if (!S || !(S.estado && (S.estado.posicoes || []).length)) return;
    try { var l = await A.api('/saidas'); if (!S) return; S.saidas = {}; (l || []).forEach(function (s) { S.saidas[s.posicao_id] = s; }); posicoes(S.estado); } catch (e) {}
  }

  function render(e) {
    if (!S) return;
    var primeira = !S.estado; S.estado = e;
    kpis(e); curva(e, primeira); gauge(e); robo(e); trava(e); sinais(e); anotaPnl(e); posicoes(e); ordens(e); journal(e);
    if (primeira) { diaADia(); }
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.painel = {
    id: 'painel', titulo: 'Painel', html: html,
    init: function (root) {
      S = { root: root, estado: null, pnlHist: {}, saidas: {}, timers: [], offs: [], piorSeq: null, gaugeV: null };
      S.offs.push(A.on('estado', render));
      S.stopTerreno = constelacao();
      /* pointer, não mouse: no celular o toque também mostra o valor do ponto */
      var svg = $('pn-eq-svg'); svg.addEventListener('pointermove', tipCurva); svg.addEventListener('pointerdown', tipCurva); svg.addEventListener('pointerleave', tipFora);
      var cells = $('pn-dd'); cells.addEventListener('mouseover', ddTip); cells.addEventListener('focusin', ddTip);
      cells.addEventListener('mouseleave', function () { $('pn-dd-tip').hidden = true; }); cells.addEventListener('focusout', function () { var t = $('pn-dd-tip'); if (t) t.hidden = true; });
      root.addEventListener('click', function (ev) {
        var t = ev.target.closest('button'); if (!t || !S) return;
        var e = S.estado || {};
        if (t.dataset.conf) { var s = (e.pendentes || []).find(function (x) { return String(x.id) === t.dataset.conf; }); if (s) A.operarSinal(s); }
        else if (t.dataset.pular) { var s2 = (e.pendentes || []).find(function (x) { return String(x.id) === t.dataset.pular; }); if (s2) A.pularSinal(s2); }
        else if (t.dataset.fechar) { var p = (e.posicoes || []).find(function (x) { return String(x.id) === t.dataset.fechar; }); if (p) A.fecharPosicao(p); }
        else if (t.id === 'pn-auto') toggleAuto();
        else if (t.id === 'pn-panico') A.panico();
      });
      S.timers.push(setInterval(function () { if (!document.hidden) mercado(); }, 60000), setInterval(function () { if (!document.hidden) diaADiaSeMudou(); }, 60000), setInterval(function () { if (!document.hidden) saidas(); }, 8000));
      mercado();
      if (A.estado) render(A.estado);
    },
    destroy: function () {
      if (!S) return;
      S.morto = true; S.timers.forEach(clearInterval); S.offs.forEach(function (f) { f(); });
      if (S.stopTerreno) S.stopTerreno();
      S = null;
    }
  };
})();
