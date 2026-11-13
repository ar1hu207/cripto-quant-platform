/* Apollux · regras compartilhadas entre o app de computador (index.html + app/casca.js) e o app do
   celular (m.html + app/m/app.js).

   Mora aqui o que é REGRA, não tela: o tamanho de um trade pelo risco, a prévia de perda no pior caso,
   o julgamento "ainda dá pra entrar" de um sinal, a aplicação de uma paleta e os dois desenhos pequenos
   que as duas casas usam (sparkline, contador). Cada uma das duas telas desenha à sua maneira; o número
   que ela desenha sai daqui. Com duas cópias, um ajuste no ticket do desktop deixaria o celular abrindo
   trade com outro tamanho para o mesmo sinal, e nada na tela diria qual dos dois está certo.

   Depende de app/api.js (window.APX) e de app/paletas.js (window.APOLLUX_PALETAS). */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt, root = document.documentElement;
  var hasGsap = function () { return typeof window.gsap !== 'undefined'; };

  /* ================= paleta (fonte única dos valores: app/paletas.js) ================= */
  var PAL = window.APOLLUX_PALETAS || [];
  function hexRgb(h) { h = String(h).replace('#', ''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  function byId(id) { for (var i = 0; i < PAL.length; i++) if (PAL[i].id === id) return PAL[i]; return null; }
  /* escreve os tokens da paleta no :root; quem chama cuida dos próprios controles e do evento */
  function pintaPaleta(p) {
    var t = p.t, s = root.style;
    var map = { '--bg': t.bg, '--panel': t.panel, '--panel2': t.panel2, '--line': t.line, '--line2': t.line2, '--txt': t.text, '--txt2': t.text2, '--mute': t.mute,
      '--accent': t.accent, '--accent-ink': t.on, '--pos': t.pos, '--neg': t.neg, '--warn': t.warn, '--info': t.info };
    for (var k in map) s.setProperty(k, map[k]);
    var rgb = { '--bg-rgb': t.bg, '--panel-rgb': t.panel, '--txt-rgb': t.text, '--line-rgb': t.line, '--accent-rgb': t.accent, '--pos-rgb': t.pos, '--neg-rgb': t.neg, '--warn-rgb': t.warn };
    for (var r in rgb) s.setProperty(r, hexRgb(rgb[r]).join(','));
    var g = Math.max(0, Math.min(1, +t.glow || .5));
    s.setProperty('--glow', g.toFixed(3)); s.setProperty('--glow-hi', Math.min(1, g * 1.6).toFixed(3));
    s.setProperty('--glow-lo', (g * .5).toFixed(3)); s.setProperty('--glow-xlo', (g * .25).toFixed(3));
    var mt = document.querySelector('meta[name="theme-color"]'); if (mt) mt.setAttribute('content', t.bg);
  }
  /* ?paleta= na query ou no hash vence o localStorage, que vence o padrão (Osso: o dono trocou o padrão do
     Elétrico para o Osso em 12/11, D-3). A MESMA chave nos dois apps: trocar no celular troca no desktop. */
  function paletaInicial() {
    var q = (location.search + '&' + location.hash).match(/[?&#]paleta=([a-z-]+)/);
    return (q && byId(q[1])) || byId(A.store.get('pulse.paleta')) || byId('osso') || PAL[0];
  }
  A.paletas = PAL; A.paletaPorId = byId; A.pintaPaleta = pintaPaleta; A.paletaInicial = paletaInicial;

  /* ================= ticket: tamanho pelo risco e prévia do pior caso =================
     Port literal do modal do painel clássico: risco% da banca, R efetivo = min(stop, liquidação), taxa nos
     dois lados. O risco digitado só dimensiona ESTE trade; não grava config. A liquidação é a mesma regra
     do simulador.abrir (0,9 / alavancagem): a essa distância o backend recusa o trade, então mandar seria só
     colher a recusa. */
  function calc(s, lev, riscoPct) {
    var e = A.estado || {}, cfg = e.config || {};
    var banca = e.banca ? e.banca.atual : 0;
    var taxa = parseFloat(cfg.taxa_por_lado) || 0.0005;
    var sd = s.preco ? Math.abs(s.preco - s.stop_sugerido) / s.preco : 0.03;
    var l = lev || 1, risco = (riscoPct || 1) / 100;
    var sdEf = Math.min(sd, 0.9 / l);
    var valor = Math.max(1, Math.round(banca * risco / Math.max((sdEf + 2 * taxa) * l, 0.0001)));
    return { valor: valor, sd: sd, sdEf: sdEf, taxa: taxa, banca: banca, risco: risco, l: l };
  }
  /* maior alavancagem em que a liquidação ainda vem DEPOIS do stop */
  function levMax(sd) { return Math.floor(0.9 / (sd || 1)); }
  /* a liquidação (90% da margem) chega antes do stop: o backend recusa o trade */
  function liqAntes(sd, l) { return 0.9 / (l || 1) < sd; }
  /* Números da prévia para um valor e uma alavancagem digitados. `expo` é nulo quando o backend não
     publicou o teto; `nOrd` avisa que o teto que o backend aplica conta as ordens descansando. */
  function previa(s, v, l, riscoPct) {
    var c = calc(s, l, riscoPct), e = A.estado || {}, rg = e.risco || {};
    var liq = 0.9 / (l || 1), la = liqAntes(c.sd, l), sdEf = Math.min(c.sd, liq);
    var perdaBruta = v * l * (sdEf + 2 * c.taxa), perda = Math.min(perdaBruta, v), perdaPct = c.banca ? perda / c.banca * 100 : 0;
    var wr = ((e.metricas || {}).por_conviccao || []).find(function (x) { var p = String(x.faixa).split('-').map(Number); return s.conviccao >= p[0] && s.conviccao < p[1]; });
    var expo = rg.risco_aberto_max_rs ? { nt: rg.risco_aberto_rs + perda, tt: rg.risco_aberto_max_rs } : null;
    if (expo) expo.estoura = expo.nt > expo.tt;
    return { c: c, liq: liq, liqAntes: la, sdEf: sdEf, perdaBruta: perdaBruta, perda: perda, perdaPct: perdaPct, margemInteira: perdaBruta >= v,
      nocional: v * l, expo: expo, nOrd: (e.ordens || []).length, wr: wr || null, trava: !!rg.trava_dia, levMax: levMax(c.sd) };
  }
  A.ticket = { calc: calc, previa: previa, levMax: levMax, liqAntes: liqAntes };

  /* status do sinal: o MESMO julgamento do clássico (statusEntrada), lógica intocada */
  A.statusEntrada = function (s, pa) {
    if (!pa) return { txt: 'aguardando preço ao vivo', cls: 'neutro' };
    var d = s.direcao === 'LONG' ? 1 : -1, favor = (pa - s.preco) / s.preco * 100 * d;
    var stopDist = Math.abs(s.preco - s.stop_sugerido) / s.preco * 100 || 1;
    var t = A.ts(s.ts), ageMin = t ? (Date.now() - t) / 60000 : 0;
    var tfMin = { '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440 }[s.tf] || 15;
    if (favor <= -stopDist) return { txt: 'invalidado: já teria batido o stop', cls: 'short' };
    if (favor >= stopDist * 0.8) return { txt: 'já correu: movimento já aconteceu', cls: 'warn' };
    if (ageMin / tfMin >= 4) return { txt: 'expirou: sinal antigo, reavalie', cls: 'warn' };
    if (favor <= -stopDist * 0.4) return { txt: 'janela apertada: preço andou contra', cls: 'warn' };
    return { txt: 'ainda dá pra entrar', cls: 'long' };
  };

  /* sparkline SVG a partir de uma série (string; a linha da tabela é template) */
  A.spark = function (vals, cls) {
    var v = (vals || []).filter(function (x) { return typeof x === 'number' && isFinite(x); });
    if (v.length < 2) return '<span class="mute">—</span>';
    var w = 72, h = 22, lo = Math.min.apply(null, v), hi = Math.max.apply(null, v), sp = (hi - lo) || 1;
    var X = function (i) { return (i * (w - 4) / (v.length - 1) + 2).toFixed(1); }, Y = function (x) { return ((1 - (x - lo) / sp) * (h - 6) + 3).toFixed(1); };
    var d = v.map(function (x, i) { return (i ? 'L' : 'M') + X(i) + ' ' + Y(x); }).join(' ');
    var c = cls || (v[v.length - 1] > v[0] ? 'pos' : v[v.length - 1] < v[0] ? 'neg' : 'flat');
    return '<svg class="spark ' + c + '" viewBox="0 0 ' + w + ' ' + h + '" aria-hidden="true"><path d="' + d + '"/><circle cx="' + X(v.length - 1) + '" cy="' + Y(v[v.length - 1]) + '" r="2"/></svg>';
  };

  /* contador: conta na PRIMEIRA carga; nos polls seguintes só troca o texto com um flash curto */
  A.contar = function (el, valor, render) {
    if (!el) return;
    var ant = el._v;
    el._v = valor;
    if (ant === undefined && !A.RM && hasGsap()) {
      var o = { v: 0 }; gsap.to(o, { v: valor, duration: 1.4, ease: 'power3.out', onUpdate: function () { el.innerHTML = render(o.v); } });
      return;
    }
    el.innerHTML = render(valor);
    if (ant !== undefined && ant !== valor && !A.RM) { el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
  };
})();
