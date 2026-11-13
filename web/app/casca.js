/* Apollux · casca: paleta, roteador por hash, sidebar/topbar, pânico, reset, diálogo de confirmação,
   o ticket de confirmar sinal (compartilhado por Painel, Operar, Análise e Apollo) e o widget global
   do Apollo.

   Contrato das views (DS/mockups/pulse-views/CONTRATO.md, mantido em produção):
     window.PULSE_VIEWS.<id> = { id, titulo, html, init(root), destroy() }
   CSS da view escopado em .v-<id>, só tokens. A view assina APX.on('estado') no init e solta no destroy;
   rota que só a view usa é chamada só enquanto ela está montada. Diferença declarada em relação ao mock:
   o Painel também é uma view (app/views/painel.js) em vez de markup fixo na casca, para que o terreno de
   partículas e as rotas do painel (/trades, /sentimento, /funding) parem no destroy como as outras. As
   views carregam sob demanda, na primeira visita à rota. */
(function () {
  'use strict';
  var A = window.APX, F = A.fmt, root = document.documentElement;
  var hasGsap = function () { return typeof window.gsap !== 'undefined'; };
  var $ = function (id) { return document.getElementById(id); };
  window.PULSE_VIEWS = window.PULSE_VIEWS || {};

  /* ================= paleta (fonte única: app/paletas.js; tokens e escolha inicial em app/comum.js) ================= */
  var PAL = A.paletas;
  var palBtns = PAL.map(function (p) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'acc'; b.setAttribute('aria-pressed', 'false');
    b.title = p.historia; var i = document.createElement('i'); i.style.setProperty('--c', p.t.accent);
    b.appendChild(i); b.appendChild(document.createTextNode(p.nome));
    b.addEventListener('click', function () { aplicaPaleta(p, true); });
    $('pal-list').appendChild(b); return b;
  });
  function aplicaPaleta(p, guardar) {
    A.pintaPaleta(p);
    palBtns.forEach(function (b, i) { var on = PAL[i] === p; b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
    $('pal-nome').textContent = p.nome; $('pal-dot').style.setProperty('--c', p.t.accent); $('pal-foot').textContent = 'Paleta ' + p.nome;
    if (guardar) A.store.set('pulse.paleta', p.id);
    A.emit('paleta', p);
  }
  var pal0 = A.paletaInicial();
  if (pal0) aplicaPaleta(pal0, false);

  /* ================= menus da topbar ================= */
  function menu(btnId, popId) {
    var b = $(btnId), p = $(popId);
    function fecha() { p.hidden = true; b.setAttribute('aria-expanded', 'false'); }
    b.addEventListener('click', function (e) { e.stopPropagation(); var abrir = p.hidden; fechaMenus(); if (abrir) { p.hidden = false; b.setAttribute('aria-expanded', 'true'); } });
    p.addEventListener('click', function (e) { if (e.target.closest('.mi')) fecha(); e.stopPropagation(); });
    return fecha;
  }
  var fechas = [menu('pal-btn', 'pal-pop'), menu('menu-btn', 'menu-pop')];
  function fechaMenus() { fechas.forEach(function (f) { f(); }); }
  document.addEventListener('click', fechaMenus);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') fechaMenus(); });

  /* ================= conta (A / B / Real em esteira) ================= */
  Array.prototype.forEach.call(document.querySelectorAll('.conta[data-conta]'), function (b) {
    b.setAttribute('aria-pressed', String(b.dataset.conta === A.CONTA));
    b.addEventListener('click', function () { A.trocaConta(b.dataset.conta); });
  });
  if (A.CONTA === 'B') { document.body.classList.add('conta-b'); }
  $('menu-conta').textContent = A.CONTA === 'B' ? 'Conta B · teste A/B' : 'Paper A · produção';

  /* ================= diálogo de confirmação ================= */
  var dlgRes = null, dlgFoco = null;
  /* dialogo({titulo, corpo (html), ok, perigo, digitar}) → Promise<boolean>. `digitar` exige a palavra
     exata antes de liberar o botão: é como o reset pede, e como o contrato do /reset já exige no corpo. */
  function dialogo(o) {
    if (dlgRes) dlgRes(false);
    dlgFoco = document.activeElement;
    var box = $('dlg-box');
    box.className = 'dlg-box' + (o.perigo ? ' perigo' : '');
    box.innerHTML = '<h3 id="dlg-h">' + A.esc(o.titulo) + '</h3><div class="dlg-body">' + (o.corpo || '') +
      (o.digitar ? '<label class="fld"><span>Digite <b class="mono">' + A.esc(o.digitar) + '</b> para confirmar</span><input class="inp" id="dlg-in" autocomplete="off" spellcheck="false"></label>' : '') +
      '</div><div class="dlg-acts"><button type="button" class="btn ghost" data-r="0">Cancelar</button><button type="button" class="btn ' + (o.perigo ? 'danger solid' : 'primary') + '" data-r="1"' + (o.digitar ? ' disabled' : '') + '>' + A.esc(o.ok || 'Confirmar') + '</button></div>';
    $('dlg').hidden = false;
    var okBtn = box.querySelector('[data-r="1"]'), inp = $('dlg-in');
    if (inp) { inp.addEventListener('input', function () { okBtn.disabled = inp.value.trim() !== o.digitar; }); setTimeout(function () { inp.focus(); }, 30); }
    else setTimeout(function () { box.querySelector('[data-r="0"]').focus(); }, 30);
    if (o.aoAbrir) o.aoAbrir(box);
    return new Promise(function (res) {
      dlgRes = function (v) { dlgRes = null; $('dlg').hidden = true; box.innerHTML = ''; if (dlgFoco && dlgFoco.focus && document.body.contains(dlgFoco)) dlgFoco.focus(); res(v); };
      box.querySelectorAll('[data-r]').forEach(function (b) { b.addEventListener('click', function () { if (b.dataset.r === '1' && o.antes) { var v = o.antes(box); if (v === false) return; } dlgRes(b.dataset.r === '1'); }); });
    });
  }
  $('dlg').addEventListener('click', function (e) { if (e.target === $('dlg') && dlgRes) dlgRes(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && dlgRes) dlgRes(false); });

  /* ================= pânico (sempre a um clique, confirmação na página) ================= */
  async function panico() {
    var e = A.estado || {}, n = (e.posicoes || []).length, no = (e.ordens || []).length;
    var on = String((e.config || {}).auto_trade) === '1';
    var corpo = '<p>O backend grava <b>auto_trade = 0 primeiro</b> e só depois fecha ' +
      (n ? '<b>' + n + (n === 1 ? ' posição' : ' posições') + '</b> a mercado.' : 'as posições abertas (agora: nenhuma).') + '</p>' +
      '<div class="diff"><div><span>Apollo (auto-trade)</span><span>' + (on ? 'ligado → <b class="neg">desligado</b>' : 'já desligado') + '</span></div>' +
      '<div><span>Posições abertas</span><span>' + n + ' → <b>0</b></span></div></div>' +
      (no ? '<div class="aviso">' + no + (no === 1 ? ' ordem post-only descansando NÃO é cancelada' : ' ordens post-only descansando NÃO são canceladas') + ' pelo /panico e ainda pode virar posição se o preço vier até ela.</div>' : '') +
      '<p class="mute">Religar o Apollo depois exige ação explícita no módulo Apollo.</p>';
    if (!(await dialogo({ titulo: 'Pânico', corpo: corpo, ok: 'Confirmar pânico', perigo: true }))) return;
    try {
      var r = await A.api('/panico', {});
      A.toast('Pânico: ' + r.fechadas + (r.fechadas === 1 ? ' posição fechada' : ' posições fechadas') + ' · P&L ' + F.money(r.pnl) + ' · auto desligado', 'neg');
      A.carregar();
    } catch (err) { A.toast('Pânico falhou: ' + A.erroTxt(err), 'neg'); }
  }
  A.panico = panico;
  $('btn-panico').addEventListener('click', panico);

  /* ================= menu da conta ================= */
  $('menu-pop').addEventListener('click', async function (ev) {
    var b = ev.target.closest('[data-acao]'); if (!b) return;
    var acao = b.dataset.acao;
    if (acao === 'sair') { A.sair(); return; }
    if (acao === 'scan') {
      A.toast('Escaneando o mercado…');
      try { var s = await A.api('/scan', {}); A.toast('Varridos ' + s.varridos + ' · ' + s.novos + (s.novos === 1 ? ' sinal novo' : ' sinais novos')); A.carregar(); }
      catch (err) { A.toast('Scan falhou: ' + A.erroTxt(err), 'neg'); }
      return;
    }
    if (acao === 'reset') {
      var corpo = '<p>Apaga <b>sinais, posições, trades e a curva de equity</b> da ' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + ', devolve a banca ao valor inicial e solta a trava do dia. Irreversível, sem backup.</p>' +
        '<p>Preserva a configuração. Os planos de DCA só são apagados se você marcar abaixo.</p>' +
        '<label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="dlg-dca"> apagar também os planos de DCA e o acumulado</label>';
      var incluirDca = false;
      var ok = await dialogo({ titulo: 'Resetar simulação', corpo: corpo, ok: 'Resetar', perigo: true, digitar: 'RESET', antes: function (box) { incluirDca = !!box.querySelector('#dlg-dca').checked; } });
      if (!ok) return;
      try { var r = await A.api('/reset', { confirmar: 'RESET', incluir_dca: incluirDca }); A.toast('Simulação resetada' + (r.dca_apagado ? ' (DCA incluído)' : ' (DCA preservado)')); A.carregar(); }
      catch (err) { A.toast('Reset recusado: ' + A.erroTxt(err), 'neg'); }
    }
  });

  /* ================= ticket: confirmar um sinal (sizing com prévia de risco) =================
     Port literal do modal do painel clássico: mesmos avisos (liquida antes do stop, estoura o teto de
     exposição) e mesma trava de duplo clique. O cálculo (tamanho pelo risco, R efetivo, perda no pior caso,
     exposição) mora em app/comum.js (A.ticket), o MESMO que o app do celular usa. */
  var busy = false, calc = A.ticket.calc;
  async function operarSinal(s) {
    var e = A.estado || {}, cfg = e.config || {};
    var lev0 = +cfg.alavancagem_padrao || 10, risco0 = (parseFloat(cfg.risco_por_trade) || 0.01) * 100;
    var exec = cfg.exec_modo === 'post_only' ? 'post-only (a ordem descansa e expira sem devolver o sinal)' : 'a mercado';
    var corpo = '<div class="mono" style="font-size:12px;color:var(--txt2)">' + A.esc(F.par(s.ativo)) + ' · ' + A.esc(s.direcao) + ' · convicção ' + Math.round(s.conviccao) + ' · ' + A.esc(s.tf || '') + ' · entrada ~' + F.px(s.preco) + ' · execução ' + exec + '</div>' +
      '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">' +
      '<label class="fld">Valor (R$)<input class="inp" id="tk-valor" type="number" min="1" step="1"></label>' +
      '<label class="fld">Alavancagem<input class="inp" id="tk-lev" type="number" min="1" max="125" step="1" value="' + lev0 + '"></label>' +
      '<label class="fld">Risco % banca<input class="inp" id="tk-risco" type="number" min="0.1" max="20" step="0.1" value="' + (+risco0.toFixed(2)) + '"></label></div>' +
      '<div class="prev" id="tk-prev"></div>';
    var valorFinal = 0, levFinal = 0;
    function previa(box) {
      var v = +box.querySelector('#tk-valor').value || 0, l = +box.querySelector('#tk-lev').value || 1;
      var P = A.ticket.previa(s, v, l, +box.querySelector('#tk-risco').value), c = P.c;
      var h = '<div class="r"><span>Stop sugerido</span><span>' + F.px(s.stop_sugerido) + ' (' + F.f2(c.sd * 100) + '%)</span></div>' +
        '<div class="r"><span>R efetivo (min stop/liq.)</span><span class="' + (P.liqAntes ? 'warn' : '') + '">' + F.f2(P.sdEf * 100) + '%</span></div>' +
        '<div class="r"><span>Nocional</span><span>' + F.brl(P.nocional) + '</span></div>' +
        '<div class="r"><span>Perda no pior caso (c/ taxa)</span><span class="neg">' + F.brl(P.perda) + ' · ' + F.f2(P.perdaPct) + '% da banca' + (P.margemInteira ? ' · margem inteira' : '') + '</span></div>';
      var nOrd = P.nOrd, x = P.expo;
      if (x) { h += '<div class="r"><span>Exposição após este trade</span><span class="' + (x.estoura ? 'neg' : '') + '">' + F.brl(x.nt) + ' / ' + F.brl(x.tt) + (x.estoura ? ' · estoura o teto' : '') + '</span></div>' + (nOrd ? '<div class="mute" style="font-size:11.5px">Sem contar ' + nOrd + (nOrd === 1 ? ' ordem descansando' : ' ordens descansando') + ': o backend conta, então pode recusar mesmo abaixo do teto.</div>' : ''); }
      h += '<div class="r"><span>Tamanho p/ arriscar ' + F.f2(c.risco * 100) + '%</span><span><b>' + F.brl(c.valor) + '</b> <button type="button" class="btn ghost sm" id="tk-usar">usar</button></span></div>';
      if (P.liqAntes) h += '<div class="aviso neg">Alavancagem alta para esse stop: a liquidação vem antes do stop e o backend recusa o trade. Baixe para ≤ ' + P.levMax + 'x.</div>';
      if (P.wr) h += '<div class="mute" style="font-size:11.5px">Win rate histórico nesta faixa de convicção: <b>' + P.wr.win_rate + '%</b> (' + P.wr.n + ' trades). Referência, não garantia.</div>';
      if (P.trava) h += '<div class="aviso neg">Trava diária ativa: o backend vai recusar.</div>';
      box.querySelector('#tk-prev').innerHTML = h;
      box.querySelector('#tk-usar').addEventListener('click', function () { box.querySelector('#tk-valor').value = c.valor; previa(box); });
    }
    var ok = await dialogo({
      titulo: 'Confirmar ' + A.esc(s.direcao) + ' ' + F.par(s.ativo), corpo: corpo, ok: 'Confirmar trade',
      aoAbrir: function (box) {
        var c = calc(s, lev0, risco0); box.querySelector('#tk-valor').value = c.valor;
        ['tk-valor', 'tk-lev', 'tk-risco'].forEach(function (id) { box.querySelector('#' + id).addEventListener('input', function () { previa(box); }); });
        previa(box); setTimeout(function () { var v = box.querySelector('#tk-valor'); v.focus(); v.select(); }, 40);
      },
      antes: function (box) {
        valorFinal = +box.querySelector('#tk-valor').value; levFinal = +box.querySelector('#tk-lev').value;
        if (!(valorFinal > 0) || !(levFinal >= 1)) { A.toast('Valor e alavancagem precisam ser positivos', 'warn'); return false; }
        /* mesma regra do simulador.abrir (geometria degenerada): mandar seria só colher a recusa */
        if (A.ticket.liqAntes(calc(s, levFinal, +box.querySelector('#tk-risco').value).sd, levFinal)) { A.toast('A essa alavancagem a liquidação vem antes do stop: baixe para ≤ ' + A.ticket.levMax(calc(s, levFinal, 1).sd) + 'x', 'warn'); return false; }
      }
    });
    if (!ok || busy) return null;
    busy = true;
    try {
      var r = await A.api('/confirmar', { sinal_id: s.id, valor_reais: valorFinal, alavancagem: levFinal });
      if (r && r.ok === false) { A.toast(r.erro, 'neg'); return r; }
      A.toast(r.tipo === 'ordem' ? 'Ordem post-only colocada: ' + F.par(s.ativo) + ' ' + A.esc(s.direcao) + ' · R$ ' + valorFinal + ' @ ' + levFinal + 'x' : s.direcao + ' ' + F.par(s.ativo) + ' aberto · R$ ' + valorFinal + ' @ ' + levFinal + 'x');
      A.carregar(); return r;
    } catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); return null; }
    finally { busy = false; }
  }
  async function pularSinal(s) {
    try { await A.api('/pular', { id: s.id }); A.toast('Sinal ' + F.par(s.ativo) + ' pulado'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }
  async function fecharPosicao(p) {
    var ok = await dialogo({ titulo: 'Fechar ' + F.par(p.ativo), corpo: '<p>Fecha a posição ' + A.esc(p.direcao) + ' ' + A.esc(p.alavancagem) + 'x a mercado. P&L agora: <b class="' + F.cls(p.pnl) + '">' + F.money(p.pnl) + '</b> (marcado no último ciclo).</p>', ok: 'Fechar a mercado', perigo: true });
    if (!ok) return;
    try { var r = await A.api('/fechar', { id: p.id }); if (r.ok === false) { A.toast(r.erro, 'neg'); return; } A.toast(r.pnl == null ? 'Posição já estava fechada' : 'Posição fechada · P&L ' + F.money(r.pnl)); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }
  A.dialogo = dialogo; A.operarSinal = operarSinal; A.pularSinal = pularSinal; A.fecharPosicao = fecharPosicao;
  /* A.statusEntrada, A.spark e A.contar moram em app/comum.js (compartilhados com o app do celular) */

  /* ================= páginas em construção (texto do mock, só o que não é número) ================= */
  var LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
  var UC = {
    acoes: { fase: 'F8', lead: 'O mesmo Apollo operando na B3 pela corretora: ações, índice e mini dólar, com calendário de pregão e a régua rodada do zero para este mercado.',
      itens: [['Conector B3', 'dados de pregão, book e execução pela corretora, no mesmo motor de hoje'], ['Calendário de pregão', 'leilão de abertura, after-market e feriados da B3 entram nas guardas do Apollo'], ['Screener de ações', 'os mesmos indicadores (EMA, ADX, Donchian, fluxo) sobre Ibovespa, small caps e BDRs'], ['Régua do zero', 'walk-forward + DSR em dados da B3; nenhum veredito de cripto é importado']],
      nota: 'sai do cadeado só com dado ao vivo e veredito próprio',
      sketch: '<div class="wf"><div class="wf-row c31"><div class="wf-b tall lines">screener · Ibovespa + small caps<br>convicção · ATR% · tendência 1d · fluxo</div><div class="wf-row"><div class="wf-b">comprar · vender</div><div class="wf-b">tamanho por risco</div><div class="wf-b">prévia: stop · perda máx.</div><div class="wf-b hot">enviar ordem</div></div></div><div class="wf-row c4"><div class="wf-b">IBOV</div><div class="wf-b">mini dólar</div><div class="wf-b">pregão</div><div class="wf-b">leilão</div></div></div>' },
    fundamentos: { fase: 'F7', lead: 'Pítia, o oráculo de análise (nome proposto): lê tokenomics, TVL, emissão e as notícias do ativo, e devolve a leitura com o porquê e a fonte à vista.',
      itens: [['Página do ativo', 'resumo em cima, os números embaixo, cada frase com a fonte ao lado'], ['Tokenomics, TVL, emissão', 'coletados por API, não digitados; atualizados com data visível'], ['Pergunte à Pítia', 'uma pergunta em português, uma resposta citando o que leu; nunca sem fonte'], ['Medido antes de decidir', 'a leitura entra na tela primeiro; na decisão do Apollo só com efeito medido na régua']],
      nota: 'custo de LLM por dia dentro de um teto; nenhuma chamada na thread do worker',
      sketch: '<div class="wf"><div class="wf-row c13"><div class="wf-row"><div class="wf-b">BTC</div><div class="wf-b hot">ETH</div><div class="wf-b">SOL</div></div><div class="wf-row"><div class="wf-b tall lines">leitura da Pítia<br>fonte em cada frase</div><div class="wf-row c3"><div class="wf-b mid">tokenomics</div><div class="wf-b mid">TVL</div><div class="wf-b mid">emissão</div></div></div></div><div class="wf-row c21"><div class="wf-b">fontes citadas</div><div class="wf-b hot">perguntar à Pítia</div></div></div>' },
    noticias: { fase: 'F7', lead: 'Notícias coletadas e consolidadas por ativo, com o impacto nas suas posições. O efeito no preço é medido na régua antes de entrar em qualquer decisão.',
      itens: [['Coleta e consolidação', 'várias fontes, uma linha por fato'], ['Impacto por posição', 'cada item diz quais das suas posições abertas ele toca'], ['Efeito medido', 'o que uma notícia fez com o preço nas últimas N vezes, não o que parece que faz'], ['Push de notícia', 'só com posição aberta no ativo, e dentro do horário silencioso']],
      nota: 'display primeiro; decisão só com evidência (NORTE.md)',
      sketch: '<div class="wf"><div class="wf-row c4"><div class="wf-b hot">todas</div><div class="wf-b">minhas posições</div><div class="wf-b">BTC</div><div class="wf-b">macro</div></div><div class="wf-row c21"><div class="wf-row"><div class="wf-b mid lines">fato · fonte · hora<br>impacto: posições</div><div class="wf-b mid lines">fato · fonte · hora<br>impacto: posições</div></div><div class="wf-b tall">impacto por posição</div></div></div>' },
    mobile: { fase: 'F5', lead: 'O app já é instalável (PWA). O que falta é o push do dia: fechamento com lucro ou prejuízo, trava disparada, oportunidade com convicção alta e ordem preenchida ou expirada.',
      itens: [['Push Web com VAPID', 'tabela de assinaturas no banco; o worker dispara, o celular recebe o mesmo número do /estado'], ['Preferências por tipo', 'o que é ruído você desliga; o que é risco (trava) nasce ligado'], ['Horário silencioso', 'só trava e pânico atravessam'], ['Nada sensível no push', 'nunca credencial, chave de API ou saldo da conta Real']],
      nota: 'a mesma hierarquia do desktop, empilhada: risco e P&L na primeira dobra',
      sketch: '<div class="wf"><div class="wf-row"><div class="wf-b">fechamento do dia · ligado</div><div class="wf-b">trava diária · sempre ligado</div><div class="wf-b">oportunidade · limiar de convicção</div><div class="wf-b">ordens · preenchida ou expirada</div><div class="wf-b">horário silencioso</div></div></div>' }
  };
  var TIT = { painel: 'Painel', operar: 'Operar', apollo: 'Apollo', analise: 'Análise', carteira: 'Carteira', pesquisa: 'Pesquisa', acoes: 'Ações BR', fundamentos: 'Fundamentos (LLM)', noticias: 'Notícias', mobile: 'Mobile & Push' };
  function ucHtml(route, c) {
    var lis = c.itens.map(function (it) { return '<li><span><b>' + it[0] + '</b> · ' + it[1] + '</span></li>'; }).join('');
    return '<section class="card uc" aria-label="' + TIT[route] + ', em construção"><div class="uc-info"><span class="uc-tag">' + LOCK + 'em construção · fase <b>' + c.fase + '</b></span>' +
      '<p class="uc-lead">' + c.lead + '</p><ul class="uc-list">' + lis + '</ul><span class="uc-note">' + c.nota + '</span></div>' +
      '<div class="uc-sketch"><span class="uc-sketch-lbl">esboço da tela</span>' + c.sketch + '</div></section>';
  }

  /* ================= roteador por hash ================= */
  var viewRoot = $('view-root'), navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav-item[data-route]'));
  var curRoute = null, curView = null, carregando = {};
  function rota() { var h = location.hash.replace(/^#/, '').split('?')[0]; return TIT[h] ? h : 'painel'; }
  function carregaView(id) {
    if (window.PULSE_VIEWS[id]) return Promise.resolve(window.PULSE_VIEWS[id]);
    if (carregando[id]) return carregando[id];
    return (carregando[id] = new Promise(function (res) {
      var s = document.createElement('script'); s.src = 'app/views/' + id + '.js';
      s.onload = function () { res(window.PULSE_VIEWS[id] || null); };
      s.onerror = function () { carregando[id] = null; res(null); };
      document.head.appendChild(s);
    }));
  }
  function head(route) {
    return '<div class="view-head"><div><div class="eyebrow">Apollux · ' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</div><h1>' + A.esc(TIT[route]) + '</h1></div>' +
      (route === 'painel' ? '' : '<div class="crumb"><a href="#painel">Painel</a> › ' + A.esc(TIT[route]) + '</div>') + '</div>';
  }
  var seq = 0;
  async function go(route) {
    if (route === curRoute) return;
    var meu = ++seq;
    if (curView && typeof curView.destroy === 'function') { try { curView.destroy(); } catch (e) { console.error('view ' + curRoute + ' destroy', e); } }
    curView = null; curRoute = route;
    navLinks.forEach(function (a) { var on = a.getAttribute('data-route') === route; a.classList.toggle('is-active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    document.title = (A.CONTA === 'B' ? '[Conta B] ' : '') + TIT[route] + ' · Apollux';
    widgetRota(route);
    window.scrollTo(0, 0);
    if (UC[route]) { viewRoot.innerHTML = head(route) + ucHtml(route, UC[route]); entrada(); return; }
    viewRoot.innerHTML = head(route) + '<div class="card"><div class="skel" style="width:40%"></div><div class="skel"></div><div class="skel" style="width:70%"></div></div>';
    var v = await carregaView(route);
    if (meu !== seq) return;
    if (!v || typeof v.html !== 'string') {
      viewRoot.innerHTML = head(route) + '<div class="view-erro"><span class="uc-tag">' + LOCK + 'módulo não carregou</span><p>O arquivo <span class="mono">app/views/' + route + '.js</span> não respondeu. Sem rede, o app só tem a casca guardada.</p><a class="btn ghost" href="#painel">Voltar ao Painel</a></div>';
      return;
    }
    curView = v;
    /* Cada montagem ganha um nó NOVO: as views delegam clique no root que recebem, e o #view-root é
       permanente. Passando o #view-root, cada visita somava um listener e um clique virava N POSTs
       (Pausar, Pular, Aportar). O nó novo morre no próximo innerHTML, e os listeners com ele. */
    viewRoot.innerHTML = head(route) + '<div class="view-mount"></div>';
    var mount = viewRoot.lastElementChild; mount.innerHTML = v.html;
    try { v.init(mount); } catch (e) { console.error('view ' + route + ' init', e); }
    entrada();
  }
  function entrada() {
    if (!hasGsap() || A.RM) return;
    var alvos = []; Array.prototype.forEach.call(viewRoot.children, function (c) { if (c.classList.contains('view-mount')) alvos.push.apply(alvos, c.children); else alvos.push(c); });
    gsap.from(alvos, { y: 14, opacity: 0, duration: .5, stagger: .06, ease: 'power2.out', clearProps: 'transform,opacity' }); }
  window.addEventListener('hashchange', function () { go(rota()); });

  /* ================= badges da nav, side-foot e conexão (alimentados pelo /estado) ================= */
  var health = null;
  async function checaSaude() { var h = await A.saude(); health = h.ok ? h : null; pintaStatus(); }
  function pintaStatus() {
    var e = A.estado, cfg = (e && e.config) || {}, on = String(cfg.auto_trade) === '1';
    var led = $('sf-led'), txt = $('sf-txt'), sub = $('sf-sub');
    var conn = $('conn'), cl = conn.querySelector('.led'), ct = conn.querySelector('span:last-child');
    if (A.online === false) { cl.className = 'led bad'; ct.textContent = 'backend offline'; }
    else if (A.online) {
      var vivo = health ? health.vivo : true;
      cl.className = 'led' + (vivo ? '' : ' bad');
      ct.textContent = (vivo ? 'ao vivo' : 'ciclo parado') + (health && health.j.ciclo_ha_s != null ? ' · ciclo há ' + Math.round(health.j.ciclo_ha_s) + ' s' : '');
    }
    if (!e) return;
    led.className = 'led' + (on ? '' : ' off');
    txt.textContent = 'Apollo ' + (on ? 'ligado' : 'desligado') + ' · ' + (cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado');
    sub.textContent = (health ? 'v' + health.j.versao + (health.j.commit ? ' · ' + String(health.j.commit).slice(0, 7) : '') + ' · ' : '') + (A.CONTA === 'B' ? 'Conta B' : 'Paper A');
    var nb = (e.pendentes || []).length, no = (e.ordens || []).length;
    $('nb-sinais').hidden = !nb; $('nb-sinais').textContent = nb;
    $('nb-ordens').hidden = !no; $('nb-ordens').textContent = no;
  }
  A.on('estado', pintaStatus);
  A.on('offline', function (m) { $('offline-txt').textContent = 'backend offline (' + m + ') · reconectando a cada 3 s. Os números abaixo são do último retrato.'; pintaStatus(); });
  A.on('online', pintaStatus);
  var saudeT = 0;
  function saudeLoop() { clearInterval(saudeT); if (!document.hidden) { checaSaude(); saudeT = setInterval(checaSaude, 30000); } }
  document.addEventListener('visibilitychange', saudeLoop);

  /* ================= widget global do Apollo ================= */
  var widgetRota = function () {};
  (function () {
    var apw = $('apw'), cvs = $('apw-canvas'), pop = $('apw-pop'), msgs = $('apw-msgs');
    var stEls = [$('apw-state'), $('apw-pop-state')], btnChat = $('apw-chat'), btnCall = $('apw-call');
    var h = null, falando = false, escondido = false, aberto = false;
    if (window.ApolloMesh) { try { h = window.ApolloMesh.create(cvs, { mode: 'mini', density: 22 }); } catch (e) { console.error('ApolloMesh', e); } }
    A.mesh = function (fn, a) { if (h && typeof h[fn] === 'function') { try { return h[fn](a); } catch (e) {} } };
    function estadoTxt() {
      var e = A.estado; if (!e) return { t: '—', on: false };
      var on = String((e.config || {}).auto_trade) === '1';
      if (falando) return { t: 'falando', on: true };
      return { t: on ? 'ligado · vigiando' : 'desligado', on: on };
    }
    function pinta() { var s = estadoTxt(); stEls.forEach(function (el) { el.textContent = s.t; el.classList.toggle('on', s.on); }); }
    A.on('estado', pinta);
    function sync() { if (escondido || document.hidden) A.mesh('pause'); else A.mesh('resume'); }
    document.addEventListener('visibilitychange', sync);
    function abre() { aberto = true; pop.hidden = false; btnChat.setAttribute('aria-expanded', 'true'); msgs.scrollTop = msgs.scrollHeight; }
    function fecha() { if (!aberto) return; aberto = false; pop.hidden = true; btnChat.setAttribute('aria-expanded', 'false'); }
    widgetRota = function (route) { escondido = route === 'apollo'; apw.hidden = escondido; if (escondido) fecha(); else A.mesh('resize'); sync(); };
    btnChat.addEventListener('click', function (e) { e.stopPropagation(); aberto ? fecha() : abre(); });
    $('apw-open').addEventListener('click', function (e) { e.stopPropagation(); aberto ? fecha() : abre(); });
    $('apw-close').addEventListener('click', function () { fecha(); btnChat.focus(); });
    $('apw-voice').addEventListener('click', function () { A.toast('Voz: em breve (fase F5)'); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && aberto) { fecha(); btnChat.focus(); } });
    document.addEventListener('click', function (e) { if (aberto && !apw.contains(e.target)) fecha(); });
    pop.addEventListener('click', function (e) { e.stopPropagation(); if (e.target.closest('a[href^="#"]')) fecha(); });

    function agora() { var d = new Date(); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
    function addMsg(cls, html) {
      var m = document.createElement('div'); m.className = 'apw-m ' + cls; m.innerHTML = html + '<time>' + agora() + '</time>';
      msgs.appendChild(m); while (msgs.children.length > 6) msgs.removeChild(msgs.firstChild);
      msgs.scrollTop = msgs.scrollHeight; return m;
    }
    /* eventos reais do /estado: a esfera pulsa e o evento entra no histórico do mini chat */
    A.on('evento', function (ev) {
      var t = '';
      if (ev.tipo === 'posicao_aberta') t = 'Posição aberta: <b>' + A.esc(F.par(ev.p.ativo)) + '</b> ' + ev.p.direcao + ' ' + ev.p.alavancagem + 'x · ' + F.brl(ev.p.valor_reais);
      else if (ev.tipo === 'posicao_fechada') t = 'Posição fechada: <b>' + A.esc(F.par(ev.p.ativo)) + '</b> ' + ev.p.direcao + ' (último P&L marcado ' + F.money(ev.p.pnl) + ')';
      else if (ev.tipo === 'sinal_novo') t = 'Sinal novo: <b>' + A.esc(F.par(ev.s.ativo)) + '</b> ' + ev.s.direcao + ' · convicção ' + Math.round(ev.s.conviccao);
      else if (ev.tipo === 'ordem_nova') t = 'Ordem post-only descansando: <b>' + A.esc(F.par(ev.o.ativo)) + '</b> ' + ev.o.direcao + ' @ ' + F.px(ev.o.preco_limite);
      else if (ev.tipo === 'trava') t = '<b class="neg">Trava diária disparou</b>: perda do dia ' + F.money(ev.r.pnl_dia) + '. Sem trades novos até a virada.';
      if (!t) return;
      addMsg('ev', t); A.mesh('pulse');
    });

    /* "Chamar Apollo": resumo por template do /estado. Sem LLM e sem número inventado: tudo sai do
       último retrato, e a hora do retrato vai junto. */
    A.resumo = function () {
      var e = A.estado; if (!e) return 'Ainda não tenho o estado do backend. Assim que a conexão voltar eu resumo.';
      var cfg = e.config || {}, rg = e.risco || {}, on = String(cfg.auto_trade) === '1';
      var pos = e.posicoes || [], aberto = pos.reduce(function (a, p) { return a + (p.pnl || 0); }, 0);
      var base = e.equity_total - (rg.pnl_dia || 0);
      var s = 'Equity <span class="mono">' + F.brl(e.equity_total) + '</span>; hoje <span class="mono ' + F.cls(rg.pnl_dia) + '">' + F.money(rg.pnl_dia) + '</span>' + (base > 0 ? ' (' + F.pct(rg.pnl_dia / base * 100) + ')' : '') + '. ';
      s += pos.length ? pos.length + (pos.length === 1 ? ' posição aberta, ' : ' posições abertas, ') + '<span class="mono ' + F.cls(aberto) + '">' + F.money(aberto) + '</span> em aberto. ' : 'Nenhuma posição aberta. ';
      if ((e.ordens || []).length) s += e.ordens.length + ' ordem(ns) post-only descansando. ';
      s += rg.trava_dia ? '<b class="neg">Trava diária disparada</b>: sem trades novos hoje. ' : 'Trava livre: consumi <span class="mono">' + F.brl(Math.max(0, -(rg.pnl_dia || 0))) + '</span> de <span class="mono">' + F.brl(rg.limite_rs) + '</span>. ';
      s += 'Estou ' + (on ? 'ligado' : '<b>desligado</b>') + ', execução ' + (cfg.exec_modo === 'post_only' ? 'post-only' : 'a mercado') + '. ';
      var a = e.auto || {};
      if (on && a.ts) s += 'Último ciclo do auto-trade ' + A.hhmm(a.ts) + ': ' + ((a.abertos || []).length ? (a.abertos.length + ' aberto(s)') : (a.motivo ? A.esc(a.motivo) : 'nada a fazer')) + '. ';
      var np = (e.pendentes || []).length; if (np) s += np + (np === 1 ? ' sinal na fila.' : ' sinais na fila.');
      return s;
    };
    btnCall.addEventListener('click', function () {
      if (falando) return; falando = true; btnCall.disabled = true; pinta();
      var txt = A.resumo(), m = addMsg('ai', '<span class="cur"></span>'), span = m.querySelector('.cur');
      var fim = function () { span.classList.remove('apw-cur'); span.innerHTML = txt; m.insertAdjacentHTML('beforeend', '<br><a class="apw-chip" href="#operar">abrir Operar</a><a class="apw-chip" href="#apollo">abrir Apollo</a>'); m.appendChild(m.querySelector('time')); falando = false; btnCall.disabled = false; pinta(); msgs.scrollTop = msgs.scrollHeight; };
      if (A.RM || !h) { fim(); return; }
      /* digita o texto puro e troca pelo HTML formatado no fim: a esfera fala enquanto ele aparece */
      var puro = txt.replace(/<[^>]+>/g, ''), i = 0, n = puro.length, passo = Math.max(8, Math.min(30, 2600 / n));
      A.mesh('speak', n * passo + 300); span.classList.add('apw-cur');
      (function tick() { i += 2; span.textContent = puro.slice(0, i); msgs.scrollTop = msgs.scrollHeight; if (i < n) setTimeout(tick, passo * 2); else setTimeout(fim, 200); })();
    });
  })();

  /* ================= gate: eventos de formulário ================= */
  $('gate-form').addEventListener('submit', A._gateEntrar);
  $('gate-eye').addEventListener('click', function () { var i = $('gate-pass'), oc = i.type === 'password'; i.type = oc ? 'text' : 'password'; this.textContent = oc ? 'ocultar' : 'ver'; this.setAttribute('aria-label', oc ? 'Ocultar senha' : 'Mostrar senha'); i.focus(); });
  ['keydown', 'keyup'].forEach(function (ev) { $('gate-pass').addEventListener(ev, function (e) { $('gate-caps').classList.toggle('on', !!(e.getModifierState && e.getModifierState('CapsLock'))); }); });

  /* ================= boot ================= */
  if (hasGsap() && !A.RM) {
    gsap.from('.side .nav-item', { x: -10, opacity: 0, duration: .5, stagger: .04, ease: 'power2.out', clearProps: 'transform,opacity' });
    gsap.to('.s1', { xPercent: -6, yPercent: 4, duration: 18, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    gsap.to('.s2', { xPercent: 5, yPercent: -3, duration: 22, yoyo: true, repeat: -1, ease: 'sine.inOut' });
  }
  /* sem gate preventivo: com credencial guardada entra direto; o 401 abre o gate se precisar */
  go(rota());
  A.carregar(); A.iniciar(); saudeLoop();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(function () {});
})();
