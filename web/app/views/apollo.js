/* Apollux · view Apollo (#apollo): o agente. Esfera full (ApolloMesh), estado real, liga/pausa, pânico,
   configuração pelo catálogo e journal.

   Regras que esta tela obedece (CLAUDE.md §2 e o briefing do front):
   - config só pelo /catalogo + POST /config, com o valor ATUAL ao lado e um diálogo de diff antes de
     gravar; chave que mexe em risco ganha aviso de `toca-risco`. Perfil (/perfil) só com o diff completo
     do que muda na tela. Nada é gravado "de brinde" junto com outra ação;
   - a trava diária é indicador: o `POST /config` recusa `trava_dia_em` desde 12/11: limpar à mão é relaxar
     invariante, então ela NÃO entra no editor;
   - `telegram_token`/`telegram_chat_id` não são exibidos (só "configurado ou não"): segredo não vai para
     a tela;
   - chat e voz estão travados (F5). "Chamar Apollo" monta o resumo por template a partir do /estado,
     sem LLM, e a esfera fala enquanto ele aparece.
   Rotas, só com a view montada: /catalogo (uma vez), /status (30 s), /trades?limite=200 (60 s),
   /config/auditoria (ao abrir a aba e depois de gravar). */
(function () {
  'use strict';
  function p1(v) { v = +v || 0; return (Math.round(v * 10) / 10).toLocaleString('pt-BR', { maximumFractionDigits: 1 }); }
  var A = window.APX, F = A.fmt;
  /* grupos do editor; chave do catálogo fora daqui cai em "Outros" (catálogo novo não some da tela) */
  var GRUPOS = [
    ['Tamanho e alavancagem', ['risco_por_trade', 'alavancagem_padrao', 'auto_lev_modo', 'auto_lev_min', 'auto_lev_max', 'auto_lev_margem_frac', 'auto_max_posicoes', 'auto_max_valor_frac']],
    ['Guardas', ['limite_perda_dia', 'risco_aberto_max', 'exposicao_max']],
    ['Entrada', ['auto_conviccao_min', 'min_conviccao', 'adx_min', 'min_fatores', 'exigir_fluxo', 'reversao_ativa', 'adx_max_rev', 'tendencia_filtro', 'auto_freshness_min', 'auto_cooldown_min']],
    ['Execução', ['exec_modo', 'exec_ordem_ttl_s', 'taxa_maker', 'exec_maker_off', 'taxa_por_lado']],
    ['Saída', ['trailing_ativo', 'trailing_unidade', 'trailing_arma_r', 'trailing_dist_r', 'trailing_dist', 'tp_ativo', 'tp_n', 'tp_fracoes', 'tp_min_r', 'tp_max_r', 'tp_forca_min', 'tp_fallback_r', 'auto_fechar_saida', 'alvo_roe']],
    ['Mercado', ['timeframe', 'timeframes', 'ativos']]
  ];
  var FORA = { auto_trade: 1, trava_dia_em: 1, telegram_token: 1, telegram_chat_id: 1 };
  var RISCO = { risco_por_trade: 1, alavancagem_padrao: 1, auto_lev_modo: 1, auto_lev_min: 1, auto_lev_max: 1, auto_lev_margem_frac: 1, auto_max_posicoes: 1, auto_max_valor_frac: 1, limite_perda_dia: 1, risco_aberto_max: 1, exposicao_max: 1 };
  var NOMES = { risco_por_trade: 'Risco por trade', alavancagem_padrao: 'Alavancagem padrão', auto_lev_modo: 'Modo da alavancagem', auto_lev_min: 'Alavancagem mínima', auto_lev_max: 'Alavancagem máxima', auto_lev_margem_frac: 'Margem por trade (modo risco)', auto_max_posicoes: 'Máx. posições', auto_max_valor_frac: 'Máx. margem por trade', limite_perda_dia: 'Trava diária (perda máx.)', risco_aberto_max: 'Teto de risco aberto', exposicao_max: 'Teto de margem', auto_conviccao_min: 'Convicção mínima do auto', min_conviccao: 'Convicção mínima do sinal', adx_min: 'ADX mínimo', min_fatores: 'Fatores mínimos', exigir_fluxo: 'Exigir fluxo taker a favor', reversao_ativa: 'Sinais de reversão', adx_max_rev: 'ADX máx. na reversão', tendencia_filtro: 'Filtro de tendência diária', auto_freshness_min: 'Idade máx. do sinal (min)', auto_cooldown_min: 'Cooldown por par (min)', exec_modo: 'Modo de execução', exec_ordem_ttl_s: 'Validade da ordem (s)', taxa_maker: 'Taxa maker', exec_maker_off: 'Afastamento da ordem', taxa_por_lado: 'Taxa taker por lado', trailing_ativo: 'Trailing', trailing_unidade: 'Unidade do trailing', trailing_arma_r: 'Trailing arma em (R)', trailing_dist_r: 'Distância do trailing (R)', trailing_dist: 'Distância do trailing (% preço)', tp_ativo: 'TP por estrutura', tp_n: 'Nº de alvos', tp_fracoes: 'Frações dos alvos', tp_min_r: 'Alvo mínimo (R)', tp_max_r: 'Alvo máximo (R)', tp_forca_min: 'Força mínima do nível', tp_fallback_r: 'Alvo de reserva (R)', auto_fechar_saida: 'Fechar pelo gestor de saída', alvo_roe: 'Alvo de ROE', timeframe: 'Tempo gráfico principal', timeframes: 'Tempos gráficos varridos', ativos: 'Pares varridos' };
  /* frações exibidas como % (o banco guarda 0.03; a tela mostra 3) */
  var PCT = { risco_por_trade: 1, limite_perda_dia: 1, risco_aberto_max: 1, exposicao_max: 1, auto_lev_margem_frac: 1, auto_max_valor_frac: 1, taxa_maker: 1, taxa_por_lado: 1, exec_maker_off: 1, trailing_dist: 1 };

  var css = '<style>' +
  '.v-apollo{display:grid;gap:18px;min-width:0}' +
  '.v-apollo .hero{position:relative;min-height:360px;padding:0;overflow:hidden;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr) minmax(0,1fr);align-items:end}' +
  '.v-apollo .hero canvas{position:absolute;inset:0;width:100%;height:100%;display:block}' +
  '.v-apollo .hero-l{position:relative;z-index:2;padding:22px;display:grid;gap:10px;align-content:end}' +
  '.v-apollo .ap-name{font-family:var(--f-display);font-weight:800;font-size:34px;letter-spacing:-.02em;line-height:1;margin:0;text-shadow:0 0 18px rgba(var(--accent-rgb),var(--glow-lo))}' +
  '.v-apollo .ap-name small{display:block;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--txt2);margin-top:7px;font-weight:500}' +
  '.v-apollo .ap-state{justify-self:start;font-family:var(--f-mono);font-size:11.5px;letter-spacing:.14em;color:var(--accent);font-weight:600;padding:5px 10px;border:1px solid rgba(var(--accent-rgb),var(--glow));border-radius:999px;box-shadow:0 0 12px rgba(var(--accent-rgb),var(--glow-xlo));text-transform:uppercase}' +
  '.v-apollo .ap-state.is-off{color:var(--warn);border-color:rgba(var(--warn-rgb),.5);box-shadow:none}' +
  '.v-apollo .ap-state.is-trava{color:var(--neg);border-color:rgba(var(--neg-rgb),.5);box-shadow:none}' +
  '.v-apollo .voice{display:inline-flex;gap:8px;align-items:center;justify-self:start;border:1px solid var(--line2);border-radius:999px;padding:6px 12px;font-size:12px;color:var(--txt2)}' +
  '.v-apollo .hero-r{position:relative;z-index:2;grid-column:3;padding:22px;display:grid;gap:10px;align-content:end}' +
  '.v-apollo .cap{border:1px solid var(--line2);background:rgba(var(--bg-rgb),.72);border-radius:12px;padding:12px 14px;font-size:12.5px;line-height:1.55;color:var(--txt);max-height:220px;overflow:auto}' +
  '.v-apollo .cap .lbl{font-family:var(--f-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);display:block;margin-bottom:4px}' +
  '.v-apollo .cap .mono{font-family:var(--f-mono)}' +
  '.v-apollo .row-main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:start}' +
  '.v-apollo .tl{list-style:none;margin:0;padding:0;display:grid;gap:10px;max-height:420px;overflow:auto}' +
  '.v-apollo .tl li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:start;font-size:12.5px}' +
  '.v-apollo .tl time{font-family:var(--f-mono);font-size:11px;color:var(--mute);padding-top:2px}' +
  '.v-apollo .tl .b{border:1px solid var(--line);border-radius:10px;padding:8px 10px;background:var(--panel2)}' +
  '.v-apollo .chat-in{display:flex;gap:8px;align-items:center;border:1px solid var(--line2);border-radius:12px;padding:8px 10px;margin-top:12px;color:var(--mute);font-size:13px}' +
  '.v-apollo .chat-in input{flex:1;min-width:0;background:none;border:0;color:var(--mute);font:inherit}' +
  '.v-apollo .notes{font-family:var(--f-mono);font-size:11px;color:var(--mute);line-height:1.6;margin-top:10px}' +
  '.v-apollo .st-acts{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}' +
  '.v-apollo .cfg-g{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}' +
  '.v-apollo .cfg-g:first-of-type{border-top:0;margin-top:0;padding-top:0}' +
  '.v-apollo .cfg-gt{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin-bottom:8px}' +
  '.v-apollo .cfg-r{display:grid;grid-template-columns:minmax(0,1fr) 210px;gap:12px;align-items:center;padding:9px 0;border-bottom:1px solid rgba(var(--line-rgb),.5)}' +
  '.v-apollo .cfg-r:last-child{border-bottom:0}' +
  '.v-apollo .cfg-r.mudou{background:linear-gradient(90deg,rgba(var(--accent-rgb),.07),transparent)}' +
  '.v-apollo .cfg-k b{display:block;font-size:13px;font-weight:600}' +
  '.v-apollo .cfg-k{min-width:0}.v-apollo .cfg-k .ch{display:block;font-family:var(--f-mono);font-size:10.5px;color:var(--mute);overflow-wrap:anywhere}' +
  '.v-apollo .cfg-k details{margin-top:3px}' +
  '.v-apollo .cfg-k summary{font-size:11px;color:var(--txt2);cursor:pointer;list-style:none}' +
  '.v-apollo .cfg-k summary::-webkit-details-marker{display:none}' +
  '.v-apollo .cfg-k summary::before{content:"+ ";font-family:var(--f-mono)} .v-apollo .cfg-k details[open] summary::before{content:"− "}' +
  '.v-apollo .cfg-k details p{margin:4px 0 0;font-size:11.5px;color:var(--txt2);line-height:1.5;white-space:pre-wrap}' +
  '.v-apollo .cfg-v{display:grid;gap:3px;justify-items:end}' +
  '.v-apollo .cfg-v .inp,.v-apollo .cfg-v select{width:100%;text-align:right}' +
  '.v-apollo .cfg-v select{background:var(--panel2);color:var(--txt);border:1px solid var(--line2);border-radius:8px;padding:7px 8px;font-family:var(--f-mono);font-size:12.5px}' +
  '.v-apollo .cfg-v .cur{font-family:var(--f-mono);font-size:10.5px;color:var(--mute)}' +
  '.v-apollo .cfg-v .ro{font-family:var(--f-mono);font-size:12px;color:var(--txt2);text-align:right;word-break:break-all}' +
  '.v-apollo .tag-r{display:inline-block;font-family:var(--f-mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--warn);border:1px solid rgba(var(--warn-rgb),.45);border-radius:999px;padding:0 6px;margin-left:6px;vertical-align:1px}' +
  '.v-apollo .sw{position:relative;width:42px;height:24px;flex:none}' +
  '.v-apollo .sw input{position:absolute;inset:0;opacity:0;margin:0;cursor:pointer}' +
  '.v-apollo .sw i{position:absolute;inset:0;border-radius:999px;background:rgba(var(--txt-rgb),.12);transition:background .2s}' +
  '.v-apollo .sw i::after{content:"";position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:var(--txt2);transition:transform .2s,background .2s}' +
  '.v-apollo .sw input:checked+i{background:var(--accent)} .v-apollo .sw input:checked+i::after{transform:translateX(18px);background:var(--accent-ink)}' +
  '.v-apollo .sw input:focus-visible+i{outline:2px solid var(--accent);outline-offset:2px}' +
  '.v-apollo .cfg-save{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px;padding:12px 0 2px;border-top:1px solid var(--line)}' +
  '.v-apollo .cfg-save .mute{font-family:var(--f-mono);font-size:11.5px}' +
  '.v-apollo .ind-trava{display:flex;justify-content:space-between;gap:10px;align-items:center;border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel2);margin-bottom:12px;font-size:12.5px}' +
  '.v-apollo .ind-trava b{font-family:var(--f-mono);font-size:11px;letter-spacing:.12em}' +
  '.v-apollo .perfis{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;font-size:12.5px;color:var(--txt2)}' +
  '.v-apollo .flt{display:flex;gap:6px;flex-wrap:wrap}' +
  '.v-apollo .flt button{border:1px solid var(--line2);background:none;color:var(--txt2);border-radius:999px;padding:3px 10px;font-family:var(--f-mono);font-size:11px;cursor:pointer}' +
  '.v-apollo .flt button[aria-pressed="true"]{color:var(--accent);border-color:rgba(var(--accent-rgb),var(--glow))}' +
  '.v-apollo .jr{list-style:none;margin:10px 0 0;padding:0;display:grid;max-height:720px;overflow:auto}' +
  '.v-apollo .jr li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;padding:9px 0;border-bottom:1px solid rgba(var(--line-rgb),.6);font-size:12.5px;align-items:start}' +
  '.v-apollo .jr time{font-family:var(--f-mono);font-size:11px;color:var(--mute);white-space:nowrap}' +
  '.v-apollo .jr .d{font-family:var(--f-mono);font-size:11px;color:var(--txt2);margin-top:2px}' +
  '.v-apollo .jr .amt{font-family:var(--f-mono);font-weight:600;white-space:nowrap}' +
  '.v-apollo .aud{list-style:none;margin:0;padding:0;display:grid;gap:6px;font-family:var(--f-mono);font-size:11.5px}' +
  '.v-apollo .aud li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;padding:6px 0;border-bottom:1px solid rgba(var(--line-rgb),.5)}' +
  /* valor de config sem espaço (a lista `ativos`, 24 pares colados por vírgula) alargava a página para 1.664 px e o celular reduzia o zoom da tela inteira */
  '.v-apollo .aud li>*{min-width:0;overflow-wrap:anywhere}' +
  '.v-apollo .aud .o{color:var(--mute);font-size:10.5px}' +
  '@media (max-width:1100px){.v-apollo .row-main{grid-template-columns:1fr}.v-apollo .hero{grid-template-columns:1fr 1fr}.v-apollo .hero-r{grid-column:2}}' +
  '@media (max-width:700px){.v-apollo .hero{grid-template-columns:1fr;min-height:480px;align-content:end}.v-apollo .hero-r{grid-column:1;padding-top:0}.v-apollo .cfg-r{grid-template-columns:1fr}.v-apollo .cfg-v{justify-items:stretch}.v-apollo .cfg-v .cur,.v-apollo .cfg-v .ro{text-align:left}}' +
  '</style>';

  var html = css + '<div class="v-apollo">' +
    '<section class="card hero" aria-label="Apollo"><canvas id="ap-mesh" aria-hidden="true"></canvas>' +
      '<div class="hero-l"><h2 class="ap-name">Apollo<small>agente · opera, vigia e fala com você</small></h2><span class="ap-state" id="ap-state">—</span>' +
        '<span class="voice" title="Voz entra na fase F5"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>Voz <span class="soon">em breve</span></span>' +
        '<button type="button" class="btn primary" id="ap-chamar" style="justify-self:start">Chamar Apollo</button></div>' +
      '<div class="hero-r"><div class="cap" id="ap-cap" aria-live="polite"><span class="lbl">Apollo</span><span id="ap-cap-t">Chame o Apollo para um resumo do estado de agora, montado do /estado.</span></div></div>' +
    '</section>' +
    '<section class="row-main">' +
      '<article class="card"><div class="card-head"><h2 class="h2">Fale com o Apollo</h2><span class="soon">chat · F5</span></div>' +
        '<ul class="tl" id="ap-tl"><li><time>—</time><div class="b mute">Aqui entram os eventos reais desta sessão: posição aberta ou fechada, sinal novo, ordem descansando, trava. Enquanto o chat não chega, é o Apollo contando o que fez.</div></li></ul>' +
        '<label class="chat-in"><input disabled placeholder="Fale com o Apollo…" aria-label="Mensagem (em breve)"><span class="soon">em breve</span></label>' +
        '<div class="notes">· chat e voz entram na fase F5, junto com o push · o Apollo só executa o que a régua autorizou: conversa não cria regra nova</div></article>' +
      '<article class="card"><div class="card-head"><h2 class="h2">Status</h2><span class="state" id="ap-st-chip">—</span></div><dl class="kv" id="ap-st"></dl>' +
        '<div class="st-acts"><button type="button" class="btn" id="ap-auto">—</button><button type="button" class="btn danger" id="ap-panico">Pânico</button></div>' +
        '<div class="notes">Pausar desliga só a abertura nova: posições abertas seguem com stop e trailing. Pânico desliga e fecha tudo a mercado.</div></article>' +
    '</section>' +
    '<section class="row-main">' +
      '<article class="card"><div class="card-head"><h2 class="h2">Configuração</h2><span class="count mute" id="ap-cfg-t">pelo /catalogo</span></div>' +
        '<div class="ind-trava" id="ap-trava"></div><div class="perfis" id="ap-perfis"></div><div id="ap-cfg"><div class="skel"></div><div class="skel"></div><div class="skel" style="width:60%"></div></div>' +
        '<div class="cfg-save"><button type="button" class="btn primary" id="ap-salvar" disabled>Revisar e salvar</button><button type="button" class="btn ghost" id="ap-desfaz" disabled>Desfazer</button><span class="mute" id="ap-pend">nenhuma alteração pendente</span></div></article>' +
      '<div class="stack"><article class="card"><div class="card-head"><h2 class="h2">Journal</h2><span class="count" id="ap-jr-n">—</span></div>' +
        '<div class="flt" id="ap-flt"><button type="button" data-f="tudo" aria-pressed="true">Tudo</button><button type="button" data-f="ganho" aria-pressed="false">Ganhos</button><button type="button" data-f="perda" aria-pressed="false">Perdas</button><button type="button" data-f="stop" aria-pressed="false">Stop</button><button type="button" data-f="manual" aria-pressed="false">Manual</button></div>' +
        '<ul class="jr" id="ap-jr"><li><span class="skel" style="grid-column:1/-1"></span></li></ul></article>' +
        '<article class="card"><div class="card-head"><h2 class="h2">Auditoria da config</h2><span class="count mute" id="ap-aud-n">—</span></div><ul class="aud" id="ap-aud"></ul><div class="notes" id="ap-aud-nota"></div></article></div>' +
    '</section>' +
  '</div>';

  var S = null;
  function $(id) { return S && S.root.querySelector('#' + id); }
  function on(e) { return String(((e || {}).config || {}).auto_trade) === '1'; }
  function nome(k) { return NOMES[k] || k; }
  /* valor do banco → valor mostrado no campo, e de volta */
  function paraTela(k, v) { if (PCT[k] && v !== '' && v != null && isFinite(+v)) return String(+(+v * 100).toFixed(6)); return v == null ? '' : String(v); }
  function doCampo(k, v) { if (PCT[k] && v !== '' && isFinite(+v)) return String(+(+v / 100).toFixed(8)); return String(v); }
  function mostra(k, v, spec) {
    if (v == null || v === '') return '—';
    if (spec && spec.tipo === 'bool') return String(v) === '1' || String(v).toLowerCase() === 'true' ? 'ligado' : 'desligado';
    if (PCT[k] && isFinite(+v)) return F.f2(+v * 100) + '%';
    return String(v);
  }
  function iguais(a, b) { if (a === b) return true; var x = parseFloat(a), y = parseFloat(b); return isFinite(x) && isFinite(y) && String(+x) === String(+y) && /^[\d.eE+-]+$/.test(String(a)) && /^[\d.eE+-]+$/.test(String(b)); }

  /* ---------- hero ---------- */
  function hero(e) {
    var st = $('ap-state'), rg = e.risco || {};
    if (rg.trava_dia) { st.textContent = 'trava diária'; st.className = 'ap-state is-trava'; }
    else if (on(e)) { st.textContent = 'ligado · vigiando'; st.className = 'ap-state'; }
    else { st.textContent = 'desligado'; st.className = 'ap-state is-off'; }
    if (S.mesh) { try { S.mesh.setLevel(on(e) ? .6 : .25); } catch (x) {} }
  }
  function chamar() {
    if (S.falando) return;
    var txt = A.resumo(), alvo = $('ap-cap-t'), b = $('ap-chamar');
    S.falando = true; b.disabled = true;
    var fim = function () { if (!S) return; alvo.innerHTML = txt; S.falando = false; b.disabled = false; addTl('Resumo pedido: ' + txt); };
    if (A.RM || !S.mesh) { fim(); return; }
    var puro = txt.replace(/<[^>]+>/g, ''), i = 0, n = puro.length, passo = Math.max(8, Math.min(30, 2600 / n));
    try { S.mesh.speak(n * passo + 300); } catch (x) {}
    (function tick() { if (!S) return; i += 2; alvo.textContent = puro.slice(0, i); if (i < n) S.tt = setTimeout(tick, passo * 2); else S.tt = setTimeout(fim, 200); })();
  }
  function addTl(h) {
    var ul = $('ap-tl'); if (!ul) return;
    if (!S.tlAlgum) { ul.innerHTML = ''; S.tlAlgum = true; }
    var d = new Date(), li = document.createElement('li');
    li.innerHTML = '<time>' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) + '</time><div class="b">' + h + '</div>';
    ul.insertBefore(li, ul.firstChild); while (ul.children.length > 30) ul.removeChild(ul.lastChild);
  }
  function evento(ev) {
    var t = '';
    if (ev.tipo === 'posicao_aberta') t = 'Abri <b>' + A.esc(F.par(ev.p.ativo)) + '</b> ' + ev.p.direcao + ' ' + ev.p.alavancagem + 'x · margem ' + F.brl(ev.p.valor_reais) + ' · entrada ' + F.px(ev.p.entrada) + ' · stop ' + F.px(ev.p.stop);
    else if (ev.tipo === 'posicao_fechada') t = 'Fechou <b>' + A.esc(F.par(ev.p.ativo)) + '</b> ' + ev.p.direcao + ' · último P&amp;L marcado <span class="' + F.cls(ev.p.pnl) + '">' + F.money(ev.p.pnl) + '</span>';
    else if (ev.tipo === 'sinal_novo') t = 'Sinal novo: <b>' + A.esc(F.par(ev.s.ativo)) + '</b> ' + ev.s.direcao + ' · convicção ' + Math.round(ev.s.conviccao) + ' · ' + A.esc(ev.s.tf);
    else if (ev.tipo === 'ordem_nova') t = 'Ordem post-only descansando: <b>' + A.esc(F.par(ev.o.ativo)) + '</b> ' + ev.o.direcao + ' @ ' + F.px(ev.o.preco_limite);
    else if (ev.tipo === 'trava') t = '<b class="neg">Trava diária disparou</b> · perda do dia ' + F.money(ev.r.pnl_dia) + '. Sem trade novo até a virada.';
    if (!t) return;
    addTl(t); if (S.mesh) { try { S.mesh.pulse(); } catch (x) {} }
  }

  /* ---------- status ---------- */
  function status(e) {
    var cfg = e.config || {}, a = e.auto || {}, st = S.status, rg = e.risco || {};
    var chip = $('ap-st-chip'); chip.textContent = on(e) ? 'ligado' : 'desligado'; chip.className = 'state' + (on(e) ? '' : ' off');
    var ult = '—';
    if (a.ts) ult = A.hhmm(a.ts) + ' · ' + ((a.abertos || []).length ? a.abertos.length + ' aberto(s)' : (a.fechados || []).length ? a.fechados.length + ' fechado(s)' : (a.motivo || 'nada a fazer'));
    else if (a.motivo) ult = a.motivo;
    var rows = [['Modo', cfg.exec_modo === 'post_only' ? 'post-only' : 'mercado'], ['Conta', A.CONTA === 'B' ? 'Conta B' : 'Paper A'], ['Última ação do auto', ult],
      ['Ordens descansando', String((e.ordens || []).length)], ['Posições abertas', String((e.posicoes || []).length)], ['Trava diária', rg.trava_dia ? 'disparada' : 'livre']];
    if (st) {
      var ini = A.ts(st.iniciado), up = ini ? Math.max(0, (Date.now() - ini) / 3600000) : null;
      rows.splice(2, 0, ['Ciclos do worker', F.f0(st.ciclos) + (st.erros ? ' · ' + st.erros + ' erros' : '')], ['Último ciclo', st.ultimo_ciclo ? A.hhmm(st.ultimo_ciclo) + ' (há ' + A.idade(st.ultimo_ciclo) + ')' : '—'], ['No ar há', up == null ? '—' : up >= 24 ? Math.floor(up / 24) + ' d ' + Math.floor(up % 24) + ' h' : F.f0(up) + ' h'], ['Saúde', st.saudavel ? 'enxergando o mercado' : 'CEGO: scan ou marcação sem resposta']);
    }
    $('ap-st').innerHTML = rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + A.esc(r[1]) + '</dd>'; }).join('');
    var b = $('ap-auto'); b.textContent = on(e) ? 'Pausar' : 'Ligar'; b.className = 'btn ' + (on(e) ? 'ghost' : 'primary');
  }
  async function lerStatus() { try { var s = await A.api('/status'); if (!S) return; S.status = s; if (S.estado) status(S.estado); } catch (e) {} }
  async function toggleAuto() {
    var e = A.estado; if (!e) return; var cfg = e.config || {}, liga = !on(e);
    if (liga) {
      var ok = await A.dialogo({ titulo: 'Ligar o Apollo', ok: 'Ligar',
        corpo: '<p>Ele passa a abrir e fechar posições sozinho na <b>' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</b> com a config gravada agora' + (S.mudancas && Object.keys(S.mudancas).length ? ' (as alterações não salvas do editor <b>não</b> entram)' : '') + ':</p><div class="diff">' +
          ['risco_por_trade', 'auto_conviccao_min', 'auto_max_posicoes', 'auto_lev_modo', 'alavancagem_padrao', 'exec_modo'].map(function (k) { return '<div><span>' + nome(k) + '</span><b>' + A.esc(mostra(k, cfg[k], S.cat && S.cat.parametros[k])) + '</b></div>'; }).join('') + '</div>' });
      if (!ok) return;
    }
    try { await A.api('/auto', { auto_trade: liga ? '1' : '0' }); A.toast(liga ? 'Apollo ligado' : 'Apollo pausado: posições abertas seguem com stop'); addTl(liga ? 'Fui <b>ligado</b> por você.' : 'Fui <b>pausado</b> por você.'); A.carregar(); }
    catch (err) { A.toast('Erro: ' + A.erroTxt(err), 'neg'); }
  }

  /* ---------- editor de config ---------- */
  function campo(k, spec, v) {
    var id = 'cf-' + k, val = k in S.mudancas ? S.mudancas[k] : v;
    if (spec.tipo === 'bool') { var ck = String(val) === '1' || String(val).toLowerCase() === 'true'; return '<label class="sw"><input type="checkbox" id="' + id + '" data-k="' + k + '"' + (ck ? ' checked' : '') + ' aria-label="' + A.esc(nome(k)) + '"><i></i></label>'; }
    if (spec.tipo === 'enum') return '<select id="' + id + '" data-k="' + k + '" aria-label="' + A.esc(nome(k)) + '">' + spec.opcoes.map(function (o) { return '<option' + (String(o) === String(val) ? ' selected' : '') + '>' + A.esc(o) + '</option>'; }).join('') + '</select>';
    if (spec.tipo === 'float' || spec.tipo === 'int') {
      var mn = PCT[k] ? spec.min * 100 : spec.min, mx = PCT[k] ? spec.max * 100 : spec.max;
      return '<input class="inp" type="number" id="' + id + '" data-k="' + k + '" inputmode="decimal" step="any" min="' + mn + '" max="' + mx + '" value="' + A.esc(paraTela(k, val)) + '" aria-label="' + A.esc(nome(k)) + (PCT[k] ? ' em %' : '') + '">';
    }
    return '<input class="inp" type="text" id="' + id + '" data-k="' + k + '" value="' + A.esc(val == null ? '' : val) + '"' + (spec.max_chars ? ' maxlength="' + spec.max_chars + '"' : '') + ' aria-label="' + A.esc(nome(k)) + '">';
  }
  function editor() {
    var e = S.estado, cat = S.cat; if (!e || !cat) return;
    var cfg = e.config || {}, P = cat.parametros || {}, usados = {};
    var grupos = GRUPOS.map(function (g) { return [g[0], g[1].filter(function (k) { usados[k] = 1; return P[k] && !FORA[k]; })]; });
    var resto = Object.keys(P).filter(function (k) { return !usados[k] && !FORA[k]; }); if (resto.length) grupos.push(['Outros', resto]);
    $('ap-cfg').innerHTML = grupos.filter(function (g) { return g[1].length; }).map(function (g) {
      return '<div class="cfg-g"><div class="cfg-gt">' + g[0] + '</div>' + g[1].map(function (k) {
        var spec = P[k], v = cfg[k], ro = k === 'ativos';
        var faixa = spec.tipo === 'float' || spec.tipo === 'int' ? (PCT[k] ? F.f2(spec.min * 100) + '–' + F.f2(spec.max * 100) + '%' : spec.min + '–' + spec.max) : spec.tipo === 'enum' ? spec.opcoes.join(' · ') : spec.tipo;
        return '<div class="cfg-r' + (k in S.mudancas ? ' mudou' : '') + '" data-row="' + k + '"><div class="cfg-k"><b>' + A.esc(nome(k)) + (RISCO[k] ? '<span class="tag-r" title="mudar isto mexe em risco: decisão do dono">toca-risco</span>' : '') + '</b>' +
          '<span class="ch">' + k + ' · ' + A.esc(faixa) + ' · padrão ' + A.esc(mostra(k, spec.padrao, spec)) + '</span>' +
          (spec.racional ? '<details><summary>por que este valor</summary><p>' + A.esc(spec.racional) + '</p></details>' : '') + '</div>' +
          '<div class="cfg-v">' + (ro ? '<span class="ro">' + A.esc(String(v || '').split(',').map(F.par).join(' · ')) + '</span><span class="cur">só leitura nesta tela (' + String(v || '').split(',').filter(Boolean).length + ' pares)</span>' : campo(k, spec, v) + '<span class="cur">atual: ' + A.esc(mostra(k, v, spec)) + '</span>') + '</div></div>';
      }).join('') + '</div>';
    }).join('');
    var tg = cfg.telegram_token ? 'configurado' : 'não configurado';
    $('ap-cfg').insertAdjacentHTML('beforeend', '<div class="cfg-g"><div class="cfg-gt">Alertas</div><div class="cfg-r"><div class="cfg-k"><b>Telegram</b><span class="ch">telegram_token · telegram_chat_id · segredo: o valor não aparece na tela</span></div><div class="cfg-v"><span class="ro">' + tg + '</span></div></div></div>');
    pendentes();
  }
  function perfis() {
    var cat = S.cat; if (!cat) return;
    $('ap-perfis').innerHTML = 'Perfil de risco: <b class="mono">' + A.esc(cat.perfil_ativo || 'personalizado') + '</b>' + Object.keys(cat.perfis || {}).map(function (p) { return '<button type="button" class="btn ghost sm" data-perfil="' + A.esc(p) + '"' + (p === cat.perfil_ativo ? ' disabled' : '') + '>aplicar ' + A.esc(p) + '</button>'; }).join('');
  }
  function trava(e) {
    var rg = e.risco || {}, cfg = e.config || {};
    $('ap-trava').innerHTML = '<span>Trava diária <span class="mute">· ' + p1(rg.limite_pct) + '% do equity do início do dia · ' + (rg.trava_dia ? 'disparada em ' + A.esc(cfg.trava_dia_em || 'hoje') : 'livre') + '</span></span><b class="' + (rg.trava_dia ? 'neg' : '') + '">NÃO DESLIGA</b>';
  }
  function pendentes() {
    var n = Object.keys(S.mudancas).length;
    $('ap-salvar').disabled = !n; $('ap-desfaz').disabled = !n;
    var t = $('ap-cfg-t'); t.textContent = n ? n + ' pendente' + (n > 1 ? 's' : '') + ' · salvar no fim' : 'pelo /catalogo'; t.className = 'count' + (n ? ' warn' : ' mute');
    $('ap-pend').textContent = n ? n + (n === 1 ? ' alteração pendente' : ' alterações pendentes') + ' · nada foi gravado ainda' : 'nenhuma alteração pendente';
  }
  function aoMudar(el) {
    var k = el.dataset.k, cfg = (S.estado || {}).config || {}, spec = S.cat.parametros[k];
    var v = spec.tipo === 'bool' ? (el.checked ? '1' : '0') : spec.tipo === 'float' || spec.tipo === 'int' ? doCampo(k, el.value) : el.value;
    var atual = cfg[k];
    if (spec.tipo === 'bool') atual = String(atual) === '1' || String(atual).toLowerCase() === 'true' ? '1' : '0';
    if (iguais(String(v), String(atual))) delete S.mudancas[k]; else S.mudancas[k] = v;
    var row = S.root.querySelector('[data-row="' + k + '"]'); if (row) row.classList.toggle('mudou', k in S.mudancas);
    pendentes();
  }
  async function salvar() {
    var m = S.mudancas, ks = Object.keys(m); if (!ks.length) return;
    var cfg = (S.estado || {}).config || {}, P = S.cat.parametros, risco = ks.some(function (k) { return RISCO[k]; });
    var corpo = '<p>Grava ' + ks.length + (ks.length === 1 ? ' chave' : ' chaves') + ' na <b>' + (A.CONTA === 'B' ? 'Conta B' : 'Paper A') + '</b> pelo <span class="mono">POST /config</span>, validado pelo catálogo, e fica na auditoria.</p>' +
      '<div class="diff">' + ks.map(function (k) { return '<div><span>' + A.esc(nome(k)) + (RISCO[k] ? ' <span class="tag-r">toca-risco</span>' : '') + '</span><span>' + A.esc(mostra(k, cfg[k], P[k])) + ' → <b>' + A.esc(mostra(k, m[k], P[k])) + '</b></span></div>'; }).join('') + '</div>' +
      (risco ? '<div class="aviso">Pelo menos uma destas chaves mexe em risco. Apertar guarda pode; afrouxar é decisão do dono (CLAUDE.md §2).</div>' : '');
    if (!(await A.dialogo({ titulo: 'Revisar alterações', corpo: corpo, ok: 'Gravar', perigo: risco }))) return;
    try {
      await A.api('/config', m);
      A.toast('Config gravada: ' + ks.join(', '));
      addTl('Config alterada por você: ' + ks.map(function (k) { return A.esc(k); }).join(', ') + '.');
      S.mudancas = {}; await A.carregar(); lerCatalogo(); auditoria();
    } catch (err) { A.toast('Recusado: ' + A.erroTxt(err), 'neg'); }
  }
  async function aplicaPerfil(p) {
    var cat = S.cat, alvo = (cat.perfis || {})[p], cfg = (S.estado || {}).config || {}; if (!alvo) return;
    var ks = Object.keys(alvo), muda = ks.filter(function (k) { return !iguais(String(alvo[k]), String(cfg[k])); });
    var corpo = '<p>Aplica o perfil <b>' + A.esc(p) + '</b> inteiro pelo <span class="mono">POST /perfil</span>. É o mesmo validador do /config, e a troca fica na auditoria.</p><div class="diff">' +
      ks.map(function (k) { var d = muda.indexOf(k) >= 0; return '<div><span>' + A.esc(nome(k)) + '</span><span>' + A.esc(mostra(k, cfg[k], cat.parametros[k])) + ' → <b' + (d ? '' : ' class="mute"') + '>' + A.esc(mostra(k, alvo[k], cat.parametros[k])) + '</b>' + (d ? '' : ' (igual)') + '</span></div>'; }).join('') + '</div>' +
      '<div class="aviso">Troca de perfil é mudança de risco: decisão do dono.</div>' + (Object.keys(S.mudancas).length ? '<p class="mute">As alterações não salvas do editor serão descartadas.</p>' : '');
    if (!(await A.dialogo({ titulo: 'Aplicar perfil ' + p, corpo: corpo, ok: 'Aplicar perfil', perigo: true }))) return;
    try { var r = await A.api('/perfil', { perfil: p }); A.toast('Perfil ativo: ' + r.perfil_ativo); addTl('Perfil de risco trocado por você: ' + A.esc(r.perfil_anterior) + ' → <b>' + A.esc(r.perfil_ativo) + '</b>.'); S.mudancas = {}; await A.carregar(); lerCatalogo(); auditoria(); }
    catch (err) { A.toast('Recusado: ' + A.erroTxt(err), 'neg'); }
  }
  async function lerCatalogo() {
    try { var c = await A.api('/catalogo'); if (!S) return; S.cat = c; perfis(); editor(); }
    catch (err) { if (S) $('ap-cfg').innerHTML = '<div class="empty">Não consegui ler o /catalogo (' + A.esc(A.erroTxt(err)) + '). Sem catálogo esta tela não edita nada: é ele que diz o que pode.</div>'; }
  }

  /* ---------- journal e auditoria ---------- */
  async function lerTrades() { try { var t = await A.api('/trades?limite=200'); if (!S) return; S.trades = t || []; journal(); } catch (err) { if (S) $('ap-jr').innerHTML = '<li class="mute">Não consegui ler o /trades.</li>'; } }
  function journal() {
    var f = S.filtro, l = (S.trades || []).filter(function (t) {
      if (f === 'ganho') return t.pnl_reais > 0; if (f === 'perda') return t.pnl_reais < 0;
      if (f === 'stop') return /stop|trailing|liquid/i.test(t.motivo_saida || ''); if (f === 'manual') return /manual|panico|pânico/i.test(t.motivo_saida || '');
      return true;
    });
    var soma = l.reduce(function (a, t) { return a + (t.pnl_reais || 0); }, 0);
    $('ap-jr-n').innerHTML = l.length + ' de ' + (S.trades || []).length + (l.length ? ' · <span class="' + F.cls(soma) + '">' + F.money(soma) + '</span>' : '');
    $('ap-jr').innerHTML = l.length ? l.slice(0, 80).map(function (t) {
      var ret = t.ret_pct != null ? F.pct(t.ret_pct) : '';
      return '<li><time>' + A.ddmm(t.fechado_em) + ' ' + A.hhmm(t.fechado_em) + '</time><div><span class="mono strong">' + A.esc(F.par(t.ativo)) + '</span> <span class="chip ' + (t.direcao === 'LONG' ? 'long' : 'short') + '">' + A.esc(t.direcao) + '</span> <span class="chip neutro">' + A.esc(t.motivo_saida || '—') + '</span>' +
        '<div class="d">' + F.px(t.entrada) + ' → ' + F.px(t.saida) + ' · ' + A.esc(t.alavancagem) + 'x · margem ' + F.brl(t.valor_reais) + (t.conviccao != null ? ' · conv. ' + Math.round(t.conviccao) : '') + ' · taxa ' + F.brl(t.taxa) + '</div></div>' +
        '<span class="amt ' + F.cls(t.pnl_reais) + '">' + F.money(t.pnl_reais) + '<div class="d" style="text-align:right">' + ret + '</div></span></li>';
    }).join('') : '<li class="mute" style="display:block">Nenhum trade nesse filtro.</li>';
  }
  async function auditoria() {
    try {
      var a = await A.api('/config/auditoria?limite=40'); if (!S) return;
      $('ap-aud-n').textContent = a.total + ' mudanças';
      $('ap-aud').innerHTML = (a.linhas || []).length ? a.linhas.map(function (l) {
        var seg = /token|chat_id/.test(l.chave);
        return '<li><span class="o">' + A.esc(String(l.ts).slice(0, 16)) + '</span><span><b>' + A.esc(l.chave) + '</b> ' + (seg ? '(segredo, valor oculto)' : A.esc(l.valor_antigo == null ? '∅' : l.valor_antigo) + ' → ' + A.esc(l.valor_novo)) + ' <span class="o">· ' + A.esc(l.origem || '') + '</span></span></li>';
      }).join('') : '<li class="mute">Nenhuma mudança registrada.</li>';
      $('ap-aud-nota').textContent = a.nota || '';
    } catch (err) { if (S) $('ap-aud').innerHTML = '<li class="mute">Não consegui ler a auditoria.</li>'; }
  }

  function render(e) {
    if (!S) return; var primeira = !S.estado; S.estado = e;
    hero(e); status(e); trava(e);
    /* o editor NÃO é redesenhado a cada poll: apagaria o que você está digitando. Só quando a config
       gravada muda por fora (outra aba, o auto, o pânico). */
    var ass = JSON.stringify(e.config || {});
    if (primeira || ass !== S.cfgAss) { S.cfgAss = ass; if (S.cat) { editor(); if (!primeira && Object.keys(S.mudancas).length) A.toast('A config mudou no backend: os valores atuais foram atualizados', 'warn'); } }
  }

  window.PULSE_VIEWS = window.PULSE_VIEWS || {};
  window.PULSE_VIEWS.apollo = {
    id: 'apollo', titulo: 'Apollo', html: html,
    init: function (root) {
      S = { root: root, estado: null, cat: null, mudancas: {}, timers: [], offs: [], filtro: 'tudo', trades: null, status: null };
      if (window.ApolloMesh) { try { S.mesh = window.ApolloMesh.create($('ap-mesh'), { mode: 'full', density: 22 }); } catch (x) { console.error('ApolloMesh full', x); } }
      S.offs.push(A.on('estado', render), A.on('evento', evento));
      root.addEventListener('click', function (ev) {
        var t = ev.target.closest('button'); if (!t || !S) return;
        if (t.id === 'ap-chamar') chamar();
        else if (t.id === 'ap-auto') toggleAuto();
        else if (t.id === 'ap-panico') A.panico();
        else if (t.id === 'ap-salvar') salvar();
        else if (t.id === 'ap-desfaz') { S.mudancas = {}; editor(); }
        else if (t.dataset.perfil) aplicaPerfil(t.dataset.perfil);
        else if (t.dataset.f) { S.filtro = t.dataset.f; Array.prototype.forEach.call($('ap-flt').children, function (b) { b.setAttribute('aria-pressed', String(b === t)); }); journal(); }
      });
      var mudar = function (ev) { var el = ev.target; if (el && el.dataset && el.dataset.k && S && S.cat) aoMudar(el); };
      root.addEventListener('input', mudar); root.addEventListener('change', mudar);
      S.timers.push(setInterval(function () { if (!document.hidden) lerStatus(); }, 30000), setInterval(function () { if (!document.hidden) lerTrades(); }, 60000));
      lerCatalogo(); lerStatus(); lerTrades(); auditoria();
      if (A.estado) render(A.estado);
    },
    destroy: function () {
      if (!S) return;
      clearTimeout(S.tt); S.timers.forEach(clearInterval); S.offs.forEach(function (f) { f(); });
      if (S.mesh) { try { S.mesh.destroy(); } catch (x) {} }
      S = null;
    }
  };
})();
