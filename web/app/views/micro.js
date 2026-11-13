/* Apollux · view Microtrades (#micro) [MICRO-1]: o laboratório de microtrades.

   Motor, banca e banco próprios (micro.py / micro.db): nada aqui toca o Apollo, as posições ou a trava
   do bot. Fala SEMPRE com a conta A (A.BASE, sem /testeB): o laboratório é um só, e não faz parte do
   teste A/B. Poll próprio de 2 s que só existe com esta view aberta e morre no destroy, para não
   engordar o /estado (CLAUDE.md §2).

   A peça central é a decomposição por trade: sinal (meio → meio, sem custo) → spread e latência →
   taxa nas duas pernas → líquido. É a diferença entre as camadas que o laboratório mede; a tela não
   esconde a camada ruim nem a pinta de outra cor. */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt;

  var css = '<style>' +
  '.v-micro{display:grid;gap:18px;min-width:0}' +
  '.v-micro .mc-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}' +
  '.v-micro .mc-lead{margin:0;font-size:13px;color:var(--txt2);line-height:1.6;max-width:760px}' +
  '.v-micro .mc-st{font-family:var(--f-mono);font-size:11.5px;color:var(--txt2);margin-top:8px;overflow-wrap:anywhere}' +
  '.v-micro .mc-st .vivo{color:var(--pos);font-weight:600}' +
  '.v-micro .mc-st .neg{color:var(--neg)}' +
  '.v-micro .mc-acts{display:flex;gap:8px;flex-wrap:wrap}' +
  '.v-micro .mc-wf{display:grid;grid-template-columns:minmax(150px,auto) minmax(0,1fr) 84px;grid-auto-flow:row dense;gap:10px 14px;align-items:center}' +
  '.v-micro .mc-wf .r{grid-column:1;font-size:12.5px;color:var(--txt2)}' +
  '.v-micro .mc-wf .r.tot{color:var(--txt);font-weight:700}' +
  '.v-micro .mc-wf .v{grid-column:3;text-align:right;font-family:var(--f-mono);font-weight:600;font-size:13px}' +
  '.v-micro .mc-wf .bar{grid-column:2;height:10px;border-radius:999px;background:var(--panel2);position:relative;overflow:hidden}' +
  '.v-micro .mc-wf .bar i{position:absolute;top:0;bottom:0}' +
  '.v-micro .mc-wf .bar i.p{background:var(--pos)}' +
  '.v-micro .mc-wf .bar i.n{background:var(--neg)}' +
  '.v-micro .mc-wf .bar i.z{left:50%;width:1px;background:var(--mute)}' +
  '.v-micro .mc-nota{font-size:12.5px;color:var(--txt2);line-height:1.6;margin:14px 0 0}' +
  '.v-micro .mc-graf{position:relative;height:240px}' +
  '.v-micro .mc-cfg{display:flex;gap:12px 16px;flex-wrap:wrap;align-items:flex-end}' +
  '.v-micro .mc-cfg label{display:flex;flex-direction:column;gap:5px;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}' +
  '.v-micro .mc-cfg input{width:104px}' +
  '.v-micro .mc-cfg .full{flex-basis:100%}' +
  '.v-micro .mc-cfg .full input{width:100%;max-width:640px}' +
  '.v-micro details.mc-exp{margin-top:16px}' +
  '.v-micro details.mc-exp summary{cursor:pointer;font-size:12.5px;color:var(--txt2);font-weight:600}' +
  '.v-micro details.mc-exp div{font-size:12.5px;color:var(--txt2);line-height:1.7;margin-top:10px;max-width:820px}' +
  '.v-micro .tbl td,.v-micro .tbl th{white-space:nowrap}' +
  '@media (max-width:640px){.v-micro .mc-wf{grid-template-columns:minmax(0,1fr) 72px;gap:4px 12px}.v-micro .mc-wf .v{grid-column:2}.v-micro .mc-wf .bar{grid-column:1/-1;margin-bottom:8px}}' +
  '</style>';

  var html = css + '<div class="v-micro">' +
    '<section class="card"><div class="mc-top"><div>' +
      '<p class="mc-lead">Laboratório em papel sobre o livro real da Binance Futuros: centenas de trades por minuto, segurando segundos. Banca e motor próprios, sem tocar no Apollo nem nas contas A e B.</p>' +
      '<div class="mc-st" id="mc-st">carregando…</div></div>' +
      '<div class="mc-acts"><button type="button" class="btn primary sm" id="mc-ligar">Ligar</button><button type="button" class="btn ghost sm" id="mc-zerar">Zerar…</button></div>' +
    '</div></section>' +
    '<section class="kpis" aria-label="Números do laboratório">' +
      '<div class="kpi"><div class="kpi-lbl">trades por minuto</div><div class="kpi-val" id="mc-tpm">—</div><div class="kpi-sub" id="mc-tpm-s">últimos 60 s</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">trades no total</div><div class="kpi-val" id="mc-n">—</div><div class="kpi-sub" id="mc-n-s">—</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">banca do laboratório</div><div class="kpi-val" id="mc-banca">—</div><div class="kpi-sub" id="mc-banca-s">—</div></div>' +
      '<div class="kpi"><div class="kpi-lbl">líquido por trade</div><div class="kpi-val" id="mc-liq">—</div><div class="kpi-sub" id="mc-liq-s">—</div></div>' +
    '</section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Para onde vai cada trade</h2><span class="count mute">média por trade · bps do notional</span></div>' +
      '<div class="mc-wf" id="mc-wf"></div><p class="mc-nota" id="mc-ver"></p></section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Resultado acumulado</h2><span class="count mute">US$ · últimas 3 h · por minuto</span></div>' +
      '<div class="mc-graf"><canvas id="mc-cv" aria-label="Curva acumulada das três camadas"></canvas></div></section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Por ativo</h2><span class="count mute" id="mc-na">—</span></div><div class="tablewrap" id="mc-at"></div></section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Últimos trades</h2><span class="count mute">25 mais recentes</span></div><div class="tablewrap" id="mc-ul"></div></section>' +
    '<section class="card"><div class="card-head"><h2 class="h2">Parâmetros</h2><span class="count mute">salvar com o motor ligado reinicia o motor</span></div>' +
      '<div class="mc-cfg" id="mc-cfg">' +
        '<label class="full">Ativos (pares USDT-M, separados por vírgula)<input class="inp" data-k="ativos" type="text" spellcheck="false" autocapitalize="off"></label>' +
        '<label>z de entrada<input class="inp" data-k="z_entrada" type="number" step="0.1" min="0.5" max="10"></label>' +
        '<label>janela OFI (ms)<input class="inp" data-k="janela_ofi_ms" type="number" step="100" min="100" max="10000"></label>' +
        '<label>horizonte (ms)<input class="inp" data-k="horizonte_ms" type="number" step="100" min="200" max="120000"></label>' +
        '<label>máx. por ativo<input class="inp" data-k="max_por_ativo" type="number" step="1" min="1" max="10"></label>' +
        '<label>intervalo mín. (ms)<input class="inp" data-k="intervalo_min_ms" type="number" step="50" min="0" max="60000"></label>' +
        '<label>latência (ms)<input class="inp" data-k="latencia_ms" type="number" step="10" min="0" max="2000"></label>' +
        '<label>notional (US$)<input class="inp" data-k="notional" type="number" step="10" min="10" max="100000"></label>' +
        '<label>banca inicial (US$)<input class="inp" data-k="banca_inicial" type="number" step="100" min="100"></label>' +
        '<button type="button" class="btn ghost sm" id="mc-salvar">Salvar</button>' +
      '</div>' +
      '<details class="mc-exp"><summary>Como a estratégia decide</summary><div>' +
        '<b>Order Flow Imbalance</b> (Cont, Kukanov &amp; Stoikov, 2014). A cada mudança no topo do livro, o motor mede quanto a pressão de compra cresceu contra a de venda: lance subindo ou engordando soma, oferta descendo ou engordando subtrai. Essa soma na janela, dividida pela profundidade média do ativo, vira um z-score contra o próprio histórico do último minuto. Com z acima do limiar e o livro mais pesado do lado da compra (microprice acima do meio), ele <b>compra no ask</b>; no simétrico, <b>vende no bid</b>. Sai depois do horizonte, ou antes se o fluxo virar, sempre pelo lado oposto do livro. Entre decidir e executar passa a latência configurada, e o preço usado é o do livro depois dela.<br><br>' +
        '<b>As três camadas.</b> <i>Sinal</i>: o meio do livro na entrada contra o meio na saída, ou seja, quanto o fluxo previu, sem custo. <i>Executado</i>: os preços reais de ask e bid, já com spread e latência. <i>Líquido</i>: o executado menos a taxa taker nas duas pernas, a mesma <span class="mono">taxa_por_lado</span> que o bot paga.' +
      '</div></details></section>' +
  '</div>';

  function usd(v) { v = +v || 0; return (v < 0 ? '−' : '') + 'US$ ' + F.f2(Math.abs(v)); }
  function usdS(v) { v = +v || 0; return (v > 0 ? '+' : v < 0 ? '−' : '') + 'US$ ' + F.f2(Math.abs(v)); }
  function bps(v) { if (v == null) return '—'; return (v > 0 ? '+' : v < 0 ? '−' : '') + F.f2(Math.abs(v)); }
  function pct(v) { return F.f0((+v || 0) * 100) + '%'; }
  function cls(v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }

  var S = null;
  function $(id) { return S.root.querySelector('#' + id); }
  function chamar(path, body) { return A.api(path, body, A.BASE); }

  async function carregar() {
    if (!S || document.hidden) return;
    var me = S;
    try { var e = await chamar('/micro/estado'); if (S !== me) return; S.e = e; pinta(e); }
    catch (err) { if (S === me) $('mc-st').textContent = 'sem resposta do laboratório: ' + A.erroTxt(err); }
  }

  function pinta(e) {
    var st = $('mc-st');
    if (e.ligado) {
      st.innerHTML = (e.conectado ? '<span class="vivo">● ao vivo</span>' : '<span class="neg">● reconectando</span>') +
        ' · ' + F.f0(e.eventos_s) + ' atualizações de livro/s · fila ' + (e.fila_ms == null ? '—' : F.f0(e.fila_ms)) + ' ms · ligado desde ' + A.esc(String(e.desde || '').slice(0, 16));
    } else {
      st.innerHTML = 'desligado' + (e.parado_por ? ' · <span class="neg">parou sozinho: ' + A.esc(e.parado_por) + '</span>' : '') + (e.erro ? ' · último erro: ' + A.esc(e.erro) : '');
    }
    var b = $('mc-ligar'); b.textContent = e.ligado ? 'Desligar' : 'Ligar'; b.className = 'btn sm ' + (e.ligado ? 'danger' : 'primary');

    $('mc-tpm').textContent = F.f0(e.trades_min);
    $('mc-tpm-s').textContent = 'últimos 60 s · ' + F.f0(e.abertas) + ' abertas agora';
    $('mc-n').textContent = F.f0(e.n);
    $('mc-n-s').textContent = 'sinal acertou a direção em ' + pct(e.acerto_sinal) + ' · líquido positivo em ' + pct(e.acerto_liq);
    $('mc-banca').textContent = usd(e.banca);
    var d = e.banca - e.banca_inicial, bs = $('mc-banca-s');
    bs.textContent = usdS(d) + ' desde ' + usd(e.banca_inicial); bs.className = 'kpi-sub ' + cls(d);
    var m = e.media_bps, lq = $('mc-liq');
    lq.textContent = bps(m.liq) + ' bps'; lq.className = 'kpi-val ' + cls(m.liq);
    $('mc-liq-s').textContent = 'taxa ' + F.f2(e.taxa_lado_bps) + ' bps por perna · ' + usd(+e.cfg.notional) + ' por trade';

    var linhas = [['Sinal (meio → meio)', m.sinal, 0], ['Spread e latência', m.exec - m.sinal, 0], ['Taxa nas duas pernas', m.liq - m.exec, 0], ['Líquido', m.liq, 1]];
    var mx = Math.max.apply(null, linhas.map(function (l) { return Math.abs(l[1]); }).concat([0.01]));
    $('mc-wf').innerHTML = e.n ? linhas.map(function (l) {
      var v = l[1], w = Math.abs(v) / mx * 50, left = v >= 0 ? 50 : 50 - w;
      return '<div class="r' + (l[2] ? ' tot' : '') + '">' + l[0] + '</div><div class="v ' + cls(v) + '">' + bps(v) + '</div>' +
        '<div class="bar"><i class="' + (v >= 0 ? 'p' : 'n') + '" style="left:' + left + '%;width:' + w + '%"></i><i class="z"></i></div>';
    }).join('') : '<div class="empty" style="grid-column:1/-1">Sem trades ainda. Ligue o motor: cada ativo precisa de ~30 s de histórico antes do primeiro trade.</div>';
    var custo = m.sinal - m.liq;
    $('mc-ver').innerHTML = e.n ? 'Cada trade custa em média <b>' + F.f2(custo) + ' bps</b> entre spread, latência e taxa. O sinal prevê <b>' + bps(m.sinal) + ' bps</b>' +
      (m.sinal > 0 ? ': para empatar, ele precisaria prever <b>' + F.f1(custo / m.sinal) + '×</b> o que prevê hoje. ' : ', ou seja, não está prevendo a direção. ') +
      'A camada “sinal” diz se existe informação no fluxo; a “líquido” diz se ela paga a conta.' : '';

    grafico(e.curva);

    $('mc-na').textContent = e.por_ativo.length + ' ativos';
    $('mc-at').innerHTML = e.por_ativo.length ? '<table class="tbl"><thead><tr><th>Ativo</th><th class="num">Trades</th><th class="num">Acerto do sinal</th><th class="num">Sinal</th><th class="num">Executado</th><th class="num">Líquido</th><th class="num">Spread agora</th><th class="num">z agora</th></tr></thead><tbody>' +
      e.por_ativo.map(function (a) {
        return '<tr><td class="mono strong">' + A.esc(String(a.ativo).toUpperCase()) + '</td><td class="mono num">' + F.f0(a.n) + '</td><td class="mono num">' + pct(a.acerto_sinal) + '</td>' +
          '<td class="mono num ' + cls(a.bps_sinal) + '">' + bps(a.bps_sinal) + '</td><td class="mono num ' + cls(a.bps_exec) + '">' + bps(a.bps_exec) + '</td><td class="mono num ' + cls(a.bps_liq) + '">' + bps(a.bps_liq) + '</td>' +
          '<td class="mono num">' + (a.spread_bps == null ? '—' : F.f2(a.spread_bps)) + '</td><td class="mono num">' + (a.z == null ? '—' : F.f2(a.z)) + '</td></tr>';
      }).join('') + '</tbody></table><div class="mute" style="font-size:11.5px;margin-top:8px">sinal, executado e líquido em bps por trade; spread em bps do meio do livro</div>' : '<div class="empty">Nenhum trade ainda.</div>';

    /* [hora, ativo, lado, dur_ms, sinal, exec, liq, motivo] */
    $('mc-ul').innerHTML = e.ultimos.length ? '<table class="tbl"><thead><tr><th>Hora</th><th>Ativo</th><th>Lado</th><th class="num">Duração</th><th class="num">Sinal</th><th class="num">Executado</th><th class="num">Líquido</th><th>Saída</th></tr></thead><tbody>' +
      e.ultimos.map(function (u) {
        return '<tr><td class="mono">' + A.esc(u[0]) + '</td><td class="mono strong">' + A.esc(String(u[1]).toUpperCase()) + '</td><td><span class="chip ' + (u[2] === 1 ? 'long' : 'short') + '">' + (u[2] === 1 ? 'compra' : 'venda') + '</span></td>' +
          '<td class="mono num">' + F.f1(u[3] / 1000) + ' s</td><td class="mono num ' + cls(u[4]) + '">' + bps(u[4]) + '</td><td class="mono num ' + cls(u[5]) + '">' + bps(u[5]) + '</td><td class="mono num ' + cls(u[6]) + '">' + bps(u[6]) + '</td>' +
          '<td class="mute">' + (u[7] === 'virada' ? 'fluxo virou' : 'tempo') + '</td></tr>';
      }).join('') + '</tbody></table>' : '<div class="empty">Nenhum trade ainda.</div>';

    if (!S.sujo) Array.prototype.forEach.call(S.root.querySelectorAll('#mc-cfg input'), function (i) { var v = e.cfg[i.dataset.k]; if (v != null) i.value = v; });
  }

  function grafico(c) {
    A.lib('chart.umd.min.js', 'Chart').then(function (ok) {
      if (!ok || !S) return;
      var cv = $('mc-cv'); if (!cv) return;
      if (!S.ch) {
        var t = { txt: A.cor('mute'), txt2: A.cor('txt2'), line: A.rgba('line', .55), acc: A.cor('accent'), pos: A.cor('pos'), neg: A.cor('neg') };
        S.cores = t;
        S.ch = new Chart(cv.getContext('2d'), { type: 'line', data: { labels: [], datasets: [
          { label: 'Sinal (sem custo)', data: [], borderColor: t.txt2, borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, tension: .2 },
          { label: 'Executado (com spread)', data: [], borderColor: t.acc, borderWidth: 1.5, pointRadius: 0, tension: .2 },
          { label: 'Líquido (com taxa)', data: [], borderColor: t.neg, borderWidth: 2, pointRadius: 0, tension: .2 }] },
          options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: t.txt2, boxWidth: 14 } }, tooltip: { callbacks: { label: function (x) { return x.dataset.label + ': ' + usd(x.parsed.y); } } } },
            scales: { x: { ticks: { color: t.txt, maxTicksLimit: 8 }, grid: { display: false } },
              y: { position: 'right', grid: { color: t.line }, ticks: { color: t.txt, callback: function (v) { return usd(v); } } } } } });
      }
      var ch = S.ch, l = c.liq.length ? c.liq[c.liq.length - 1] : 0;
      ch.data.labels = c.t; ch.data.datasets[0].data = c.sinal; ch.data.datasets[1].data = c.exec; ch.data.datasets[2].data = c.liq;
      ch.data.datasets[2].borderColor = l >= 0 ? S.cores.pos : S.cores.neg;
      ch.update('none');
    });
  }

  async function ligar() {
    if (!S || S.ocupado) return; S.ocupado = true;
    var on = S.e && S.e.ligado;
    try {
      var e = await chamar(on ? '/micro/desligar' : '/micro/ligar', {});
      if (!S) return; S.e = e; pinta(e);
      A.toast(e.ligado ? 'Laboratório ligado: cada ativo aquece ~30 s antes de operar' : 'Laboratório desligado');
    } catch (err) { A.toast('Não foi: ' + A.erroTxt(err), 'warn'); }
    finally { if (S) S.ocupado = false; }
  }

  async function zerar() {
    if (!S) return;
    var ok = await A.dialogo({ titulo: 'Zerar o laboratório', ok: 'Zerar', perigo: true,
      corpo: '<p>Apaga todos os microtrades e volta a banca do laboratório a <b>' + usd(S.e ? S.e.banca_inicial : 10000) + '</b>. O Apollo, as contas A e B e o histórico do bot não são afetados.</p>' });
    if (!ok || !S) return;
    try {
      var e = await chamar('/micro/zerar', {});
      if (!S) return;
      if (S.ch) { S.ch.destroy(); S.ch = null; }
      S.e = e; pinta(e); A.toast('Laboratório zerado');
    } catch (err) { A.toast('Não foi: ' + A.erroTxt(err), 'warn'); }
  }

  async function salvar() {
    if (!S) return;
    var body = {};
    Array.prototype.forEach.call(S.root.querySelectorAll('#mc-cfg input'), function (i) { if (i.value !== '') body[i.dataset.k] = i.dataset.k === 'ativos' ? i.value : Number(i.value); });
    try {
      var e = await chamar('/micro/config', body);
      if (!S) return; S.sujo = false; S.e = e; pinta(e);
      A.toast('Parâmetros salvos' + (e.ligado ? ' · motor reiniciado' : ''));
    } catch (err) { A.toast('Recusado: ' + A.erroTxt(err), 'warn'); }
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.micro = {
    id: 'micro', titulo: 'Microtrades', html: html,
    init: function (root) {
      S = { root: root, e: null, ch: null, sujo: false, ocupado: false, timer: 0 };
      root.querySelector('#mc-ligar').addEventListener('click', ligar);
      root.querySelector('#mc-zerar').addEventListener('click', zerar);
      root.querySelector('#mc-salvar').addEventListener('click', salvar);
      root.querySelector('#mc-cfg').addEventListener('input', function () { if (S) S.sujo = true; });
      carregar();
      S.timer = setInterval(carregar, 2000);
    },
    destroy: function () {
      if (!S) return;
      clearInterval(S.timer);
      if (S.ch) { try { S.ch.destroy(); } catch (e) {} }
      S = null;
    }
  };
})();
