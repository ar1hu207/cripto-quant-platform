// O app do painel classico (classico.html), carregado no fim do <body>, sem defer. Era um <script>
// embutido la. Virou arquivo porque a CSP do classico passou a ser a do resto do painel
// (`script-src 'self'`, sem 'unsafe-inline'): script embutido e handler em atributo (onclick=,
// oninput=) nao executam mais, e e isso que impede HTML injetado de rodar e ler a credencial do
// localStorage. O escH() continua valendo para todo campo do backend: a CSP e a segunda camada,
// nao a unica. Nao volte com nada disto para dentro do HTML, nem com onclick= num template daqui:
// o navegador bloqueia em silencio e o botao so para de responder. Clique novo: ver "cliques".

// brl() e num() NAO limpam nada sozinhos: "<img>".toLocaleString() devolve a propria string, e
// coluna REAL do SQLite aceita texto. O escH() mora aqui, na fonte; em numero de verdade ele nao
// muda um caractere. pct() nao precisa: .toFixed() em string estoura em vez de imprimir.
const brl=v=>'R$ '+escH((v??0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}));
const pct=v=>(v>=0?'+':'')+(v??0).toFixed(2)+'%';
const num=v=>escH((v??0).toLocaleString('pt-BR',{maximumFractionDigits:(v!=null&&Math.abs(v)<10)?5:2}));
let chart, _sig=null, _est=null, _saidas={}, _saidasVistas={}, _precos={}, _busy=false, _modalTrigger=null;

// ---- vendor sob demanda -----------------------------------------------------
// As duas libs de gráfico saíram do <head>. Elas continuam sendo servidas por NÓS, de
// web/vendor/ — a regra "nada de CDN de terceiro" é sobre a ORIGEM do script, não sobre o
// momento em que ele entra, e a origem não mudou. O que mudou é que agora entram quando
// alguém vai desenhar um gráfico, em vez de antes de existir markup.
// Memoizado por arquivo: chamar duas vezes devolve a MESMA promessa e injeta um <script> só.
const _libs={};
function carregarLib(arquivo,global){
  if(window[global]) return Promise.resolve(true);
  if(_libs[arquivo]) return _libs[arquivo];
  return _libs[arquivo]=new Promise(res=>{
    const s=document.createElement('script'); s.src='vendor/'+arquivo;
    s.onload=()=>res(!!window[global]);
    // Falha ao baixar a lib não pode derrubar o painel: o gráfico fica de fora e o resto do
    // terminal (tiles, tabelas, status bar, risco) segue de pé. Quem chama testa o retorno.
    s.onerror=()=>{ _libs[arquivo]=null; res(false); };
    document.head.appendChild(s);
  });
}
const libChart=()=>carregarLib('chart.umd.min.js','Chart');
const libTV=()=>carregarLib('lightweight-charts.standalone.production.js','LightweightCharts');
let _tvWarm=false;   // aquecimento ocioso da lib de velas já disparado? (ver fim do carregar())

function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('on');
  setTimeout(()=>t.classList.remove('on'),2600);}

// ---- ponte com o backend ---------------------------------------------------
// API vazio = mesma origem (o próprio backend serve este arquivo). Front separado
// (Vercel): config.js define window.API_BASE = 'https://seu-backend' e as credenciais
// do Basic Auth passam a ir no header explicitamente (o navegador não as anexa sozinho
// em requisição cross-origin).
// [AB-1] Conta A (produção) ou B (teste A/B). A B é outra instância do bot, com banca própria,
// que o backend expõe em /testeB/...: trocar de conta é só trocar o prefixo de TODAS as rotas.
// Fica no localStorage por ser preferência deste navegador; sem storage, cai na A.
// [AB-2] A C é a terceira instância, em /testeC/...: a conta A sem TP2 e TP3.
// [AB-3] A D é a quinta, em /testeD/...: filtro d1 + saída da C + tamanho da B.
const CONTA=(()=>{try{const c=localStorage.getItem('cbConta');return c==='B'||c==='C'||c==='D'?c:'A';}catch{return 'A';}})();
const API=(window.API_BASE||'').replace(/\/+$/,'')+(CONTA==='A'?'':'/teste'+CONTA);
function trocaConta(c){ if(c===CONTA) return; try{localStorage.setItem('cbConta',c);}catch{} location.reload(); }
let _cred=localStorage.getItem('cbAuth')||'';

// ---------- gate de login ----------
// Substitui os dois prompt() do navegador. O ganho não é só estético: prompt() não sabe a
// diferença entre senha errada, IP bloqueado pelo throttle, backend sem DASH_PASS e backend
// fora do ar — devolve as quatro como "não entrou". Aqui cada uma tem a sua mensagem, e o
// /health (única rota que dispensa credencial) diz ao vivo se o serviço está de pé ANTES de
// a pessoa digitar. Foi exatamente essa confusão que custou uma madrugada de investigação.
const $g=id=>document.getElementById(id);
let _gateSessao=null, _gateTimer=null, _gateHealth=null;

function gateMsg(html,tipo){ const m=$g('gate-msg'); m.innerHTML=html; m.className='gate-msg on '+(tipo||'err'); }
function gateLimpa(){ $g('gate-msg').className='gate-msg'; }
function gateOcupado(on,rotulo,girando){
  $g('gate-btn').disabled=on;
  $g('gate-btn').classList.toggle('loading',!!(on&&girando));
  $g('gate-btn-txt').textContent=rotulo||'Entrar no terminal';
  $g('gate-user').disabled=on; $g('gate-pass').disabled=on;
}
function gateSacode(){ const c=$g('gate-form');
  c.classList.remove('shake'); void c.offsetWidth; c.classList.add('shake');
  c.addEventListener('animationend',()=>c.classList.remove('shake'),{once:true}); }

// /health não passa pela autenticação (é o que o monitoramento consome), então serve de
// prova de vida do backend mesmo com o painel trancado.
async function gateSaude(){ const s=$g('gate-status'), t=$g('gate-status-txt');
  try{
    const j=await (await fetch(API+'/health',{cache:'no-store'})).json();
    // versao E commit, os dois. A versao diz o que o sistema E; o commit diz qual codigo esta
    // RODANDO -- e os dois nao andam juntos, porque a main avanca e o deploy e ato deliberado
    // (CLAUDE.md 5). Mostrar so a versao foi o que deixou o painel anunciar v0.3 por meses.
    // Commit ausente e declarado como tal: 'sem git' nunca vira string parecida com um sha.
    const sha=j.commit?(' · '+String(j.commit).slice(0,7)):' · sem git';
    s.className='gate-status up'; t.textContent='backend online · v'+j.versao+sha;
  }catch{ s.className='gate-status down'; t.textContent='backend sem resposta'; } }

// 429 = throttle do backend (15 senhas erradas bloqueiam o IP). Trava o botão e conta o
// tempo em vez de deixar a pessoa martelar e renovar o próprio bloqueio.
function gateEspera(seg){
  clearInterval(_gateTimer);
  const tick=()=>{ if(seg<=0){ clearInterval(_gateTimer); gateOcupado(false); gateLimpa(); $g('gate-pass').focus(); return; }
    gateMsg('Tentativas demais. O backend libera de novo em <b>'+seg+'s</b>.','warn'); seg--; };
  gateOcupado(true,'Aguarde',false); tick(); _gateTimer=setInterval(tick,1000);
}

async function gateEntrar(ev){
  ev.preventDefault();
  const u=$g('gate-user').value.trim(), p=$g('gate-pass').value;
  if(!p){ gateMsg('Digite a senha.','info'); $g('gate-pass').focus(); return; }
  const cand='Basic '+btoa(u+':'+p);
  gateLimpa(); gateOcupado(true,'Verificando…',true);
  let r;
  // /status é a rota autenticada mais barata que existe: valida a credencial sem arrastar
  // a curva de equity inteira só para descobrir se a senha presta.
  try{ r=await fetch(API+'/status',{headers:{Authorization:cand}}); }
  catch{ gateOcupado(false); gateSaude();
    gateMsg('Sem resposta do backend. Ou o serviço está fora do ar, ou a origem deste painel não está liberada no <b>CORS_ORIGINS</b> da VM.','err'); return; }

  if(r.ok){ _cred=cand; localStorage.setItem('cbAuth',cand);
    gateOcupado(true,'Entrando…',false); gateFecha(true);
    cargaInicial(); iniciarPolling(); return; }

  gateOcupado(false);
  if(r.status===401){ gateSacode(); gateMsg('Usuário ou senha incorretos.','err');
    const c=$g('gate-pass'); c.focus(); c.select(); }
  else if(r.status===429){ const txt=await r.text().catch(()=>'');
    // Retry-After não atravessa o CORS sem expose_headers, mas o backend repete o tempo no corpo.
    const m=txt.match(/(\d+)\s*s/); gateEspera(m?+m[1]:120); }
  else if(r.status===503){ gateMsg('O backend está no ar, mas sem <b>DASH_PASS</b> definido — e sem senha ele recusa qualquer acesso externo. Defina a senha no <b>.env</b> da VM e reinicie o serviço.','warn'); }
  else{ gateMsg('Resposta inesperada do backend (HTTP '+r.status+').','err'); }
}

// Single-flight: o poll dispara ~5 requisições por ciclo e todas levam 401 juntas. Quem
// chegar com o gate já aberto espera o MESMO login em vez de empilhar telas.
function gateAbre(){
  if(_gateSessao) return _gateSessao.promessa;
  let resolver; const promessa=new Promise(res=>{resolver=res;});
  _gateSessao={promessa,resolver};
  $g('gate').classList.add('on'); document.body.style.overflow='hidden';
  $g('gate-foot').innerHTML='autenticando em<br>'+(API||location.origin);
  gateLimpa(); gateOcupado(false); $g('gate-pass').value='';
  ($g('gate-user').value.trim()?$g('gate-pass'):$g('gate-user')).focus();
  gateSaude(); clearInterval(_gateHealth); _gateHealth=setInterval(gateSaude,15000);
  return promessa;
}
function gateFecha(ok){
  clearInterval(_gateHealth); clearInterval(_gateTimer);
  $g('gate').classList.remove('on'); document.body.style.overflow='';
  $g('gate-pass').value='';
  if(_gateSessao){ const r=_gateSessao.resolver; _gateSessao=null; r(!!ok); }
}

async function sairLogin(){
  localStorage.removeItem('cbAuth'); _cred=''; pararPolling();
  // Backend sem senha (dev/monolito local) não tem sessão pra encerrar: mostrar o gate ali
  // seria pedir uma credencial que ninguém vai conferir.
  try{ if((await fetch(API+'/status')).ok){ cargaInicial(); iniciarPolling();
        toast('Este backend não pede senha — não há sessão para encerrar'); return; } }catch{}
  gateAbre();
}

async function apiFetch(path,opts={}){
  const mk=()=>({...opts,headers:{...(opts.headers||{}),...(_cred?{Authorization:_cred}:{})}});
  let r=await fetch(API+path,mk());

  // Bloqueado pelo throttle: parar de bater, senão o poll renova o bloqueio pra sempre.
  if(r.status===429){ pararPolling(); toast(await r.clone().text()); return r; }

  // 401: NUNCA insistir com a mesma credencial. O poll dispara ~5 requisições a cada 3s e
  // 15 senhas erradas bloqueiam o IP por 2 min — um typo repetido viraria lockout. Então:
  // para o polling, descarta a credencial e abre o gate. Quem religa o painel é o próprio
  // gate quando a credencial nova passa, uma vez só, e não cada requisição que esperou.
  if(r.status===401){
    pararPolling();
    localStorage.removeItem('cbAuth'); _cred='';
    if(await gateAbre()) r=await fetch(API+path,mk());
  }
  return r;
}

async function api(path,body){const o=body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{};
  const r=await apiFetch(path,o); if(!r.ok) throw new Error(await r.text()); return r.json();}

function statusEntrada(s, pa){
  // Decide se ainda vale entrar comparando o quanto o preço andou a favor vs o R (stop)
  if(!pa) return {txt:'aguardando preço ao vivo…', cls:'st-wait'};
  const d = s.direcao==='LONG'?1:-1;
  const favor = (pa - s.preco)/s.preco*100 * d;                          // % a favor do sinal
  const stopDist = Math.abs(s.preco - s.stop_sugerido)/s.preco*100 || 1; // R inicial em %
  const ageMin = (Date.now() - Date.parse((s.ts||'').replace(' ','T')))/60000;
  const tfMin = {'5m':5,'15m':15,'30m':30,'1h':60,'4h':240,'1d':1440}[s.tf]||15;
  const candles = ageMin/tfMin;
  if(favor <= -stopDist)     return {txt:'✗ invalidado — já teria batido o stop', cls:'st-no'};
  if(favor >= stopDist*0.8)  return {txt:'⏭ já correu — movimento já aconteceu (chasing)', cls:'st-late'};
  if(candles >= 4)           return {txt:'⌛ expirou — sinal antigo, reavalie', cls:'st-late'};
  if(favor <= -stopDist*0.4) return {txt:'⚠ janela apertada — preço andou contra', cls:'st-tight'};
  return {txt:'✓ ainda dá pra entrar', cls:'st-ok'};
}

// Sparkline do card hero. Desenha a curva de equity que o /estado JA traz (e.equity_hist), sem
// lib e sem requisicao extra. SVG em vez de canvas porque escala junto com o CSS, sem precisar
// medir o elemento nem reagir a resize. Verde/vermelho aqui e legitimo: e direcao de dinheiro.
// Chart.js e Lightweight-Charts recebem STRING de cor: nao entendem var(). Em vez de repetir
// hex e deixar o grafico dessincronizar do resto, o tema dos graficos LE os tokens do :root.
// Assim o DESIGN.md continua sendo a fonte unica e trocar um token troca a vela junto.
const TEMA=(()=>{ const cs=getComputedStyle(document.documentElement);
  const t=n=>cs.getPropertyValue('--'+n).trim();
  return {pos:t('pos'),neg:t('neg'),warn:t('warn'),accent:t('accent'),accentTxt:t('accent-txt'),
          txt:t('txt'),txt2:t('txt2'),txt3:t('txt3'),line:t('line')}; })();
// Variacoes de alpha DECLARADAS dos tokens, para as libs de grafico, que so aceitam string de
// cor. Derivadas do PROPRIO token em vez de hex repetido: assim trocar --accent ou --txt2 no
// :root troca a area da curva e as bandas de Bollinger junto, que e o ponto de ter token.
const rgbDe=hex=>{const h=(hex||'').replace('#','').trim();
  const n=parseInt(h.length===3?h.split('').map(c=>c+c).join(''):h,16);
  return isFinite(n)?[(n>>16)&255,(n>>8)&255,n&255].join(','):'56,97,251';};
const ACCENT_RGB=rgbDe(TEMA.accent);
const BOLL=`rgba(${rgbDe(TEMA.txt2)},.5)`, BOLL_MID=`rgba(${rgbDe(TEMA.txt2)},.25)`;

// Sparkline generico: recebe a SERIE e o ALVO. Antes mirava o #spark do hero, que era o unico
// que existia; com cinco tiles o mesmo desenho serve equity e banca e o alvo tem que vir de fora.
// Azul, nao verde/vermelho: e a MESMA serie da Curva de capital, e pintar a mesma serie de duas
// cores em dois lugares da tela seria defeito. A direcao ja esta dita, em verde/vermelho, na
// linha de P&L logo acima.
// Devolve o SVG como STRING: a linha da tabela e montada por template, e um sparkline que so
// sabe escrever em innerHTML nao serve de fechamento de linha. O sparkline() abaixo passou a ser
// so o escritor.
function sparkSVG(valores, opts){
  const o=opts||{};
  const v=(valores||[]).filter(n=>typeof n==='number'&&isFinite(n));
  if(v.length<2) return '';
  const W=100,H=32,min=Math.min(...v),max=Math.max(...v),amp=(max-min)||1;
  const d=v.map((n,i)=>`${i?'L':'M'}${(i/(v.length-1)*W).toFixed(2)} ${(H-(n-min)/amp*H).toFixed(2)}`).join('');
  const gid='spark-g-'+(o.id||'x');             // id unico: dois <defs> com o mesmo id colidem
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" focusable="false" aria-hidden="true">`+
    (o.area===false?'':
      `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">`+
      `<stop offset="0" stop-color="rgba(${ACCENT_RGB},.28)"/>`+
      `<stop offset="1" stop-color="rgba(${ACCENT_RGB},0)"/>`+
      `</linearGradient></defs>`+
      `<path d="${d}L${W} ${H}L0 ${H}Z" fill="url(#${gid})"/>`)+
    // non-scaling-stroke: sem isso o preserveAspectRatio="none" estica a linha junto com a caixa
    `<path d="${d}" fill="none" stroke="var(--accent-txt)" stroke-width="1.5"`+
    ` vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
// Azul, nao verde/vermelho: e a MESMA serie da Curva de capital, e pintar a mesma serie de duas
// cores em dois lugares da tela seria defeito. A direcao ja esta dita, em verde/vermelho, na
// coluna de delta ao lado.
function sparkline(valores, alvo, opts){
  const el=typeof alvo==='string'?document.getElementById(alvo):alvo; if(!el) return;
  el.innerHTML=sparkSVG(valores,{...(opts||{}),id:el.id||'x'});
}

// ---- fila de sinais: tabela com linha expansivel ----
// Quais linhas estao abertas mora AQUI, num Set, e nao no HTML: o carregar() reescreve
// #pendentes inteiro a cada 3s, entao qualquer estado guardado na marcacao fecharia sozinho
// no proximo poll. O render le o Set, e por isso a linha continua aberta atravessando polls.
const _sigAbertos=new Set();
// Serie observada de preco por ativo, alimentada pelo /precos (poll de 8s). O /estado nao traz
// historico de preco do sinal, entao o sparkline da linha desenha o que o painel VIU desde que
// abriu -- dado honesto, sem requisicao nova. Fica vazio ate ter dois pontos.
const _serie={}, SERIE_MAX=60;
function anotaSerie(precos){
  Object.entries(precos||{}).forEach(([a,p])=>{
    if(typeof p!=='number'||!isFinite(p))return;
    const v=_serie[a]||(_serie[a]=[]);
    if(v[v.length-1]!==p)v.push(p);
    if(v.length>SERIE_MAX)v.splice(0,v.length-SERIE_MAX);
  });
}
// Evolucao do P&L por posicao, para o sparkline que fecha a linha. O /estado manda o P&L
// atual a cada poll, nao a serie; entao a serie e o que o painel observou, comecando em zero -
// que e o P&L no momento da entrada. Dado honesto, sem requisicao nova.
const _pnlHist={}, PNL_MAX=60;
function anotaPnl(posicoes){
  const vivos=new Set();
  (posicoes||[]).forEach(p=>{
    vivos.add(String(p.id));
    const v=_pnlHist[p.id]||(_pnlHist[p.id]=[0]);
    const pl=p.pnl||0;
    if(v[v.length-1]!==pl)v.push(pl);
    if(v.length>PNL_MAX)v.splice(1,v.length-PNL_MAX);
  });
  // posicao fechada nao acumula serie para sempre
  Object.keys(_pnlHist).forEach(k=>{if(!vivos.has(k))delete _pnlHist[k];});
}
function toggleSinal(ev,id){
  // clique num botao da linha e acao, nao expansao
  if(ev&&ev.target&&ev.target.closest&&ev.target.closest('button'))return;
  if(_sigAbertos.has(id))_sigAbertos.delete(id); else _sigAbertos.add(id);
  if(_est)carregarPendentes(_est);
}
function carregarPendentes(e){
  const pe2=document.getElementById('pendentes'); if(!pe2)return;
  if(!e.pendentes||!e.pendentes.length){
    pe2.innerHTML='<div class="empty">Nenhum sinal no momento — engine observando 👀</div>'; return;
  }
  pe2.innerHTML='<table class="tbl-sinais"><thead><tr>'+
    '<th class="col-2">#</th><th>Ativo</th><th>Lado</th><th class="col-2">Conv.</th>'+
    '<th class="num col-2">Entrada</th><th class="num col-3">Agora</th><th class="num col-4">Δ</th>'+
    '<th>Status</th><th class="col-3">Tendência</th><th class="flex"></th></tr></thead><tbody>'+
    e.pendentes.map((s,i)=>linhaSinal(s,i)).join('')+'</tbody></table>';
}
function linhaSinal(s,i){
  const cls=s.direcao==='LONG'?'long':'short', pa=_precos[s.ativo];
  const dlt=pa?(pa-s.preco)/s.preco*100:null;
  const fav=dlt!=null&&((s.direcao==='LONG'&&dlt>0)||(s.direcao==='SHORT'&&dlt<0));
  const st=statusEntrada(s,pa), aberto=_sigAbertos.has(s.id);
  // statusEntrada() e logica e nao se toca: o texto curto e so recorte para caber na celula,
  // e o inteiro fica no title e na sub-linha.
  const stCurto=st.txt.split(' — ')[0];
  // escH() porque o destino e o atributo data-sinal='...': JSON.stringify() nao escapa aspas simples,
  // e um apostrofo num campo do sinal fechava o atributo. O navegador desfaz as entidades ao ler o
  // atributo, entao o JSON.parse() do clique entrega ao abrirModal() o mesmo objeto de sempre.
  const json=escH(JSON.stringify(s));
  // a serie da linha comeca no preco do PROPRIO sinal e segue pelo que o painel observou:
  // e a leitura util aqui ("de onde saiu, pra onde foi"), e ja tem dois pontos no primeiro
  // /precos em vez de esperar dois polls para aparecer
  const spark=sparkSVG([s.preco].concat(_serie[s.ativo]||[]),{area:false,id:'sig'+s.id});
  const linha=`<tr class="sig-row${aberto?' on':''}${st.cls==='st-no'?' sig-dim':''}" data-sid="${s.id}"
      tabindex="0" aria-expanded="${aberto}" data-acao="toggleSinal">
    <td class="mono mut col-2">${i+1}</td>
    <td class="sig-ativo"><span class="sig-exp" aria-hidden="true">▶</span> ${escH(s.ativo.replace('/USDT',''))} <span class="tf-badge">${escH(s.tf||'')}</span></td>
    <td><span class="tag ${cls}">${escH(s.direcao)}</span></td>
    <td class="col-2"><span class="conv">${escH(s.conviccao)}<span class="convbar"><i style="width:${escH(s.conviccao)}%"></i></span></span></td>
    <td class="mono num col-2">${num(s.preco)}</td>
    <td class="mono num col-3">${pa?num(pa):'—'}</td>
    <td class="mono num col-4 ${dlt==null?'mut':(fav?'pos':'neg')}" title="${dlt==null?'sem preço ao vivo':(fav?'a favor do sinal':'contra o sinal')}">${dlt==null?'—':(dlt>=0?'+':'')+dlt.toFixed(2)+'% '+(fav?'✓':'✗')}</td>
    <td><span class="st ${st.cls}" title="${st.txt}">${stCurto}</span></td>
    <td class="col-3">${spark?`<span class="row-spark">${spark}</span>`:'<span class="row-spark vazio">—</span>'}</td>
    <td class="acts-cell flex"><button class="btn-op" data-foco="op-${s.id}" data-acao="abrirModal" data-sinal='${json}'>⚡ Operar</button><button class="btn-skip" data-acao="pular" data-id="${s.id}">Pular</button></td>
  </tr>`;
  if(!aberto)return linha;
  const chips=(s.motivos||'').split(', ').filter(Boolean).map(m=>`<span class="why-chip">${escH(m)}</span>`).join('')
    ||'<span class="why-chip">sinal fraco</span>';
  return linha+`<tr class="sig-det" data-sid="${s.id}"><td colspan="10">
    <div class="det-why"><span class="why-lbl">Por quê</span>${chips}</div>
    <div class="cmp"><span class="tipo-badge tipo-${escH(s.tipo||'tendencia')}">${s.tipo==='reversao'?'↩ reversão':'📈 tendência'}</span>
      <span class="mut">🕐 ${escH((s.ts||'').slice(11,16))}</span>
      <span class="mut">sinal <b>${num(s.preco)}</b></span>
      ${pa?`<span class="mut">→ agora <b>${num(pa)}</b></span><span class="${fav?'pos':'neg'}" style="font-weight:600">${dlt>=0?'+':''}${dlt.toFixed(2)}% ${fav?'✓ a favor':'✗ contra'}</span>`:'<span class="mut">→ agora …</span>'}
      <span class="mut">· stop sugerido <b class="neg">${num(s.stop_sugerido)}</b></span></div>
    <div class="entry-status ${st.cls}">${st.txt}</div>
    <div class="det-acts"><button class="btn-analise" data-acao="analisarSinal" data-sinal='${json}'>🔍 Analisar no gráfico</button></div>
  </td></tr>`;
}

// Tiles de Posicoes, Risco do dia e Exposicao. Os tres fecham com barra em vez de sparkline
// porque sao ocupacao de um teto, nao serie no tempo. Cada barra vem com o numero escrito ao
// lado: cor nunca e o unico sinal.
function tiles(e){
  const txt=(id,v,cls)=>{const el=document.getElementById(id); if(!el)return;
    el.textContent=v; if(cls!=null)el.className=cls;};
  const barra=(id,pct)=>{const el=document.getElementById(id);
    if(el)el.style.width=Math.min(Math.max(pct||0,0),100).toFixed(1)+'%';};

  const cfg=e.config||{}, rg=e.risco||{};

  // posicoes: contagem, P&L nao realizado e ocupacao das vagas
  const naoReal=(e.posicoes||[]).reduce((a,p)=>a+(p.pnl||0),0);
  const vagas=+(cfg.auto_max_posicoes||5)||5, usadas=(e.posicoes||[]).length;
  txt('pos-pnl',`${naoReal>=0?'▲':'▼'} ${brl(Math.abs(naoReal))} não realizado`,
      'delta mono '+(naoReal>=0?'pos':'neg'));
  barra('pos-bar',usadas/vagas*100);
  txt('pos-sub',`${usadas} de ${vagas} vagas ocupadas`);

  // risco do dia: perda do dia contra o limite diario
  if(rg.limite_rs!=null){
    const perdaPct=rg.limite_rs?Math.min(Math.max(-rg.pnl_dia,0)/rg.limite_rs*100,100):0;
    txt('risco-dia',brl(rg.pnl_dia),'val mono '+(rg.pnl_dia>=0?'pos':'neg'));
    barra('risco-bar',perdaPct);
    txt('risco-sub',rg.trava_dia
      ? `travado — limite ${brl(-rg.limite_rs)} atingido, sem novos trades hoje`
      : `${perdaPct.toFixed(0)}% do limite de ${brl(-rg.limite_rs)} (${rg.limite_pct}%)`);
  }

  // exposicao aberta: risco-ate-o-stop somado contra o teto
  if(rg.risco_aberto_max_rs){
    const expoPct=Math.min(rg.risco_aberto_rs/rg.risco_aberto_max_rs*100,100);
    txt('expo',brl(rg.risco_aberto_rs),'val mono'+(rg.teto_aberto?' neg':''));
    barra('expo-bar',expoPct);
    txt('expo-sub',rg.teto_aberto
      ? `teto de ${brl(rg.risco_aberto_max_rs)} atingido — feche uma posição antes de abrir outra`
      : `${expoPct.toFixed(0)}% do teto de ${brl(rg.risco_aberto_max_rs)} (${rg.risco_aberto_pct}%)`);
  } else {
    txt('expo','sem teto','val mono');
    txt('expo-sub','nenhum teto de exposição configurado');
  }
}

// Curva de capital. Saiu de dentro do carregar() porque o Chart.js agora entra sob demanda:
// o ciclo dispara e segue, e a curva aparece quando a lib chega — uma vez só por sessão.
// Duas chamadas concorrentes não criam dois Chart: libChart() devolve a mesma promessa e os
// .then entram na fila na ordem em que foram registrados, então o segundo já vê `chart` setado.
function desenharEquity(h){
  libChart().then(ok=>{
    if(!ok) return;                       // lib não veio: o resto do painel continua inteiro
    if(!chart){const ctx=document.getElementById('chart').getContext('2d');const g=ctx.createLinearGradient(0,0,0,230);
      // area da curva de capital: rgba(56,97,251,.28), o valor que o DESIGN.md fixa
      g.addColorStop(0,`rgba(${ACCENT_RGB},.28)`);g.addColorStop(1,`rgba(${ACCENT_RGB},0)`);
      chart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:TEMA.accentTxt,borderWidth:2,fill:true,backgroundColor:g,tension:.3,pointRadius:0}]},
        options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false},
          tooltip:{callbacks:{label:c=>brl(c.parsed.y)}}},scales:{x:{display:false},y:{position:'right',grid:{color:TEMA.line},ticks:{color:TEMA.txt3,callback:v=>brl(v)}}}}});}
    chart.data.labels=h.map(x=>x.ts); chart.data.datasets[0].data=h.map(x=>x.equity_total); chart.update('none');
  });
}

async function carregar(){
  let e; try{ e=await api('/estado'); }catch{
    document.getElementById('cfg').textContent='⚠️ backend offline — reconectando…';
    if(!_est){ ['pendentes','posicoes','trades','metricas','dca'].forEach(id=>{const el=document.getElementById(id); if(el)el.innerHTML='<div class="empty off">⚠️ Sem conexão com o backend. Reconectando…</div>';}); }
    return;
  }
  _est=e;
  const total=e.equity_total, b0=e.banca.inicial, lucro=total-b0;
  document.getElementById('equity').textContent=brl(total);
  const pe=document.getElementById('pnl'); pe.textContent=`${lucro>=0?'▲':'▼'} ${brl(Math.abs(lucro))} (${pct(lucro/b0*100)})`;
  pe.className='delta mono '+(lucro>=0?'pos':'neg');
  document.getElementById('banca').textContent=brl(e.banca.atual);
  document.getElementById('npos').textContent=e.posicoes.length;
  document.getElementById('npend').textContent=e.pendentes.length;
  tiles(e);
  const sbh=document.getElementById('sb-hora');
  if(sbh)sbh.textContent=new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  if(e.config) document.getElementById('cfg').textContent=`${e.config.ativos.split(',').length} ativos · ${e.config.timeframe} · paper trading · preço real`;

  // chart
  const h=e.equity_hist||[];
  desenharEquity(h);          // sem await: a lib entra sob demanda e não segura o resto do ciclo
  sparkline(h.map(x=>x.equity_total),'spark');
  sparkline(h.map(x=>x.banca),'spark-banca',{area:false});   // discreto: so a linha

  // guarda de risco: alimenta a status bar. A leitura detalhada (barra, limite, percentual)
  // vive nos tiles de Risco do dia e Exposicao aberta; aqui fica so o que precisa estar
  // sempre visivel, e o banner sobrou para os DOIS estados que travam operacao.
  const rg=e.risco, rgEl=document.getElementById('risco-guard');
  if(rg&&rgEl){
    let rgh=`<span class="rg-item"><span class="mut">banca</span><b class="mono">${brl(e.banca.atual)}</b></span>`;
    rgh+=`<span class="rg-item"><span class="mut">risco dia</span><b class="mono ${rg.pnl_dia>=0?'pos':'neg'}">${brl(rg.pnl_dia)}</b><span class="mut">de ${brl(-rg.limite_rs)}</span></span>`;
    if(rg.risco_aberto_max_rs){
      const usadoAb=Math.min(Math.max(rg.risco_aberto_rs/rg.risco_aberto_max_rs*100,0),100);
      rgh+=`<span class="rg-item"><span class="mut">exposição</span><b class="mono${rg.teto_aberto?' neg':''}">${usadoAb.toFixed(0)}%</b><span class="mut">do teto</span></span>`;
    }
    if(rg.trava_dia) rgh+=`<span class="rg-banner">🛑 trava diária — sem novos trades hoje</span>`;
    if(rg.teto_aberto) rgh+=`<span class="rg-banner">🛑 teto de exposição — feche uma posição antes de abrir outra</span>`;
    rgEl.innerHTML=rgh;
  }

  // pendentes: uma linha por sinal, sub-linha sob demanda
  carregarPendentes(e);

  // posicoes: a linha fecha com a evolucao do P&L da propria posicao
  anotaPnl(e.posicoes);
  // [EX-1] Ordens post-only pendentes. Elas JA reservam exposicao nos tetos do
  // `simulador`, entao esconde-las seria esconder risco ja comprometido -- por isso o bloco
  // fica ACIMA das posicoes, e nao numa aba propria. Some sozinho quando nao ha nenhuma.
  const pOrd=document.getElementById('painel-ordens'), od=document.getElementById('ordens'), ords=e.ordens||[];
  pOrd.hidden = !ords.length;
  if(ords.length){
    od.innerHTML='<table><thead><tr><th>Ativo</th><th>Lado</th><th class="num">Limite</th>'+
    '<th class="num col-2">Preço ref.</th><th class="num col-2">Distância</th><th class="col-2">Tam.</th>'+
    '<th class="num col-3">Expira</th></tr></thead><tbody>'+
    ords.map(o=>{
      const dist=o.preco_ref?Math.abs(o.preco_limite/o.preco_ref-1)*100:0;
      // minutos ate expirar, do relogio do NAVEGADOR contra o carimbo do backend. Os dois sao
      // hora de Sao Paulo sem fuso (CLAUDE.md §1), entao a subtracao fecha.
      const falta=o.expira_em?Math.max(0,Math.round((new Date(o.expira_em.replace(' ','T'))-new Date())/60000)):null;
      return `<tr><td style="font-weight:600">${escH(o.ativo.replace('/USDT',''))}</td>
      <td><span class="tag ${o.direcao==='LONG'?'long':'short'}">${escH(o.direcao)}</span></td>
      <td class="mono num" style="font-weight:600">${num(o.preco_limite)}</td>
      <td class="mono mut num col-2">${num(o.preco_ref)}</td>
      <td class="mono mut num col-2">${dist.toFixed(2)}%</td>
      <td class="mono mut col-2">R$${escH(o.valor_reais)}·${escH(o.alavancagem)}x</td>
      <td class="mono mut num col-3">${falta===null?'—':falta+' min'}</td></tr>`}).join('')+'</tbody></table>';
  }

  const po=document.getElementById('posicoes');
  if(e.posicoes.length){
    po.innerHTML='<table><thead><tr><th>Ativo</th><th>Lado</th><th class="num col-2">Entrada</th>'+
    '<th class="num">Atual</th><th class="col-2">Tam.</th><th class="num">P&L (ROE)</th>'+
    '<th class="num col-3">Liq.</th><th class="col-3">Evolução</th><th class="flex"></th></tr></thead><tbody>'+
    e.posicoes.map(p=>{const pl=p.pnl||0, roe=p.valor_reais?pl/p.valor_reais*100:0, d=p.direcao==='LONG'?1:-1, liq=p.entrada*(1-d*0.9/p.alavancagem), sd=_saidas[p.id];
      const spark=sparkSVG(_pnlHist[p.id],{area:false,id:'pos'+p.id});
      return `<tr><td style="font-weight:600">${escH(p.ativo.replace('/USDT',''))}</td>
      <td><span class="tag ${p.direcao==='LONG'?'long':'short'}">${escH(p.direcao)}</span></td>
      <td class="mono mut num col-2">${num(p.entrada)}</td>
      <td class="mono num">${num(p.preco_atual)}</td>
      <td class="mono mut col-2">R$${escH(p.valor_reais)}·${escH(p.alavancagem)}x</td>
      <td class="mono num ${pl>=0?'pos':'neg'}" style="font-weight:600">${brl(pl)} <span class="met-nota ${pl>=0?'pos':'neg'}">${pct(roe)}</span></td>
      <td class="mono neg num col-3">${num(liq)}</td>
      <td class="col-3">${spark?`<span class="row-spark">${spark}</span>`:'<span class="row-spark vazio">—</span>'}</td>
      <td class="acts-cell flex"><button class="btn-close" data-acao="fechar" data-id="${p.id}">Fechar</button></td></tr>${(sd&&sd.acao)?`<tr class="saida saida-${escH(sd.nivel)}"><td colspan="9">${escH(sd.acao)}${(sd.nivel==='forte'||sd.nivel==='lucro')?` <button class="btn-vender" data-acao="fechar" data-id="${p.id}">Vender agora</button>`:''}</td></tr>`:''}`}).join('')+'</tbody></table>';
  } else po.innerHTML='<div class="empty">Nenhuma posição aberta</div>';

  // trades
  const tr=document.getElementById('trades'), ts=e.trades||[];
  if(ts.length){
    tr.innerHTML='<table><thead><tr><th>Hora</th><th>Ativo</th><th>Lado</th><th class="num col-2">Entrada→Saída</th>'+
    '<th class="col-2">Tam.</th><th class="col-3 flex wrap">Motivo</th><th class="num">Resultado (ROE)</th></tr></thead><tbody>'+
    ts.map(t=>`<tr><td class="mono mut">${escH((t.fechado_em||'').slice(11,16))}</td><td style="font-weight:600">${escH(t.ativo.replace('/USDT',''))}</td>
      <td><span class="tag ${t.direcao==='LONG'?'long':'short'}">${escH(t.direcao)}</span></td>
      <td class="mono mut num col-2">${num(t.entrada)}→${num(t.saida)}</td>
      <td class="mono mut col-2">R$${escH(t.valor_reais)}·${escH(t.alavancagem)}x</td><td class="mut col-3 flex wrap">${escH(t.motivo_saida)}</td>
      <td class="mono num ${t.pnl_reais>=0?'pos':'neg'}" style="font-weight:600">${brl(t.pnl_reais)} <span class="met-nota ${t.pnl_reais>=0?'pos':'neg'}">${pct(t.valor_reais?t.pnl_reais/t.valor_reais*100:0)}</span></td></tr>`).join('')+'</tbody></table>';
  } else tr.innerHTML='<div class="empty">Nenhum trade ainda</div>';

  // metricas
  const m=e.metricas||{};
  const sqn=m.sqn||0, sqnCor=sqn>=2?'pos':(sqn>=1.6?'':'neg'),
    sqnLbl=sqn<=0?'sem dados':(sqn>7?'suspeito (overfit?)':sqn>=3?'excelente':sqn>=2?'bom':sqn>=1.6?'médio':'fraco');
  // Tabela de duas colunas, que e o que o CMC faz com dado tabular. A grade de .mstat dava a
  // 14 numeros de importancia muito diferente exatamente o mesmo peso visual.
  const linhaMet=(rot,val,nota,cls)=>`<tr><td>${rot}</td><td class="mono${cls?' '+cls:''}">${val}${nota?`<span class="met-nota">${nota}</span>`:''}</td></tr>`;
  let mh='<table class="tbl-met"><thead><tr><th>Métrica</th><th class="num">Valor</th></tr></thead><tbody>'+
    linhaMet('Trades',escH(m.n_trades||0))+
    linhaMet('Win rate',(m.win_rate||0).toFixed(1)+'%')+
    linhaMet('Profit factor',(m.profit_factor||0).toFixed(2))+
    linhaMet('P&L total',brl(m.pnl_total),'',m.pnl_total>=0?'pos':'neg')+
    linhaMet('Taxa paga',brl(m.taxa_total),'','neg')+
    linhaMet('SQN',sqn.toFixed(2),sqnLbl,sqnCor)+
    linhaMet('SQN-R (R-múltiplos)',(m.sqn_r||0).toFixed(2))+
    linhaMet('Sortino',(m.sortino||0).toFixed(2),'',(m.sortino||0)>=0?'pos':'neg')+
    linhaMet('Sharpe (diário)',(m.sharpe||0).toFixed(2),'',(m.sharpe||0)>=0?'pos':'neg')+
    linhaMet('Calmar',(m.calmar||0).toFixed(2))+
    linhaMet('Max drawdown',brl(m.max_drawdown),`${(m.max_drawdown_pct||0).toFixed(1)}%`,'neg')+
    linhaMet('Max DD (mark-to-market)',(m.max_dd_mtm_pct||0).toFixed(1)+'%','','neg')+
    linhaMet('Expectativa/trade',brl(m.expectancia),'',m.expectancia>=0?'pos':'neg')+
    linhaMet('Expectativa-R',(m.expectancia_r||0).toFixed(2)+'R','',(m.expectancia_r||0)>=0?'pos':'neg')+
    '</tbody></table>';
  if(m.por_conviccao&&m.por_conviccao.length){
    mh+=`<h2 style="margin-top:24px">🎯 Win rate por convicção — a tunagem</h2>
    <table><thead><tr><th>Faixa</th><th class="num">Trades</th><th class="num">Win rate</th><th class="num">P&L</th></tr></thead><tbody>`+
    m.por_conviccao.map(c=>`<tr><td class="mono">${escH(c.faixa)}</td><td class="mono num mut">${escH(c.n)}</td>
      <td class="mono num ${c.win_rate>=50?'pos':'neg'}" style="font-weight:600">${escH(c.win_rate)}%</td>
      <td class="mono num ${c.pnl>=0?'pos':'neg'}">${brl(c.pnl)}</td></tr>`).join('')+'</tbody></table>';
  } else mh+='<div class="empty">Confirme alguns trades pra ver o win rate por convicção.</div>';
  document.getElementById('metricas').innerHTML=mh;

  // DCA / acumulação
  const dcaEl=document.getElementById('dca'), planos=e.dca||[];
  if(dcaEl){
    if(planos.length){
      dcaEl.innerHTML='<table><thead><tr><th>Ativo</th><th class="num col-2">Investido</th>'+
        '<th class="num col-2">Preço médio</th><th class="num">Valor atual</th><th class="num">P&L</th>'+
        '<th class="col-3">Aportes</th><th class="flex"></th></tr></thead><tbody>'+
        planos.map(p=>`<tr><td style="font-weight:600">${escH(p.ativo.replace('/USDT',''))}</td>
          <td class="mono mut num col-2">${brl(p.total_investido)}</td>
          <td class="mono mut num col-2">${num(p.preco_medio)}</td>
          <td class="mono num">${brl(p.valor_atual)}</td>
          <td class="mono num ${p.pnl>=0?'pos':'neg'}" style="font-weight:600">${brl(p.pnl)} <span class="met-nota ${p.pnl>=0?'pos':'neg'}">${pct(p.pnl_pct)}</span></td>
          <td class="mono mut col-3">${escH(p.n_aportes)}× · R$${escH(p.valor_aporte)}/${escH(p.freq_dias)}d</td>
          <td class="acts-cell flex"><button class="btn-sug" data-acao="aportarDca" data-id="${p.id}">aportar</button> <button class="btn-skip" data-acao="removerDca" data-id="${p.id}" aria-label="remover plano DCA" title="remover">×</button></td></tr>`).join('')+'</tbody></table>';
    } else dcaEl.innerHTML='<div class="empty">Nenhum plano. Crie um abaixo pra acumular cripto de forma disciplinada (sem adivinhar timing).</div>';
    const dsel=document.getElementById('dca-ativo');
    if(dsel&&!dsel.options.length&&e.config){e.config.ativos.split(',').forEach(a=>{const o=document.createElement('option');o.value=a.trim();o.textContent=a.trim().replace('/USDT','');dsel.appendChild(o);});}
  }

  renderAuto(e);
  atualizarGrafico(e);

  // Aquecimento ocioso da lib de velas: só AQUI, depois que o painel já tem dado, porque é
  // daqui pra frente que a aba Gráfico passa a ser alcançável. Fazê-lo no boot devolveria os
  // 52 KB ao caminho crítico justamente enquanto a página espera a resposta que abre o gate.
  if(!_tvWarm){ _tvWarm=true;
    if(window.requestIdleCallback) requestIdleCallback(()=>libTV(),{timeout:5000});
    else setTimeout(libTV,3000); }
}

// ---- medidor de sentimento ----
async function carregarSentimento(){
  try{
    const s=await apiFetch('/sentimento').then(r=>r.json());
    const fg=s.fear_greed, br=s.breadth; let h='';
    if(fg){
      // faixa: a cor do numero e a mesma escala da barra. Todas saem de token, e todas passam
      // 4.5:1 sobre --surface (o --neg corrigido inclusive).
      const cor=fg.valor<25?'var(--neg)':fg.valor<45?'var(--warn)':fg.valor<55?'var(--txt2)':'var(--pos)';
      h+=`<div class="fg">
        <div><div class="lbl">Fear &amp; Greed</div>
          <div class="fg-num mono" style="color:${cor}">${+fg.valor||0}<span class="fg-lbl">${escH(fg.label)}</span></div></div>
        <div class="fg-escala">
          <div class="fg-barra" role="img" aria-label="Fear and Greed em ${+fg.valor||0} de 100: ${escH(fg.label)}">
            <span class="fg-agulha" style="left:${+fg.valor||0}%"></span></div>
          <div class="fg-pontas"><span>Medo extremo</span><span>Ganância extrema</span></div>
        </div></div>`;
    }
    if(br) h+=`<div class="fg-breadth">📊 <b>${escH(br.pct_subindo)}%</b> das ${escH(br.n)} moedas subindo hoje · variação média <span class="${br.variacao_media>=0?'pos':'neg'}">${pct(br.variacao_media)}</span></div>`;
    document.getElementById('sentimento').innerHTML=h||'sentimento indisponível';
  }catch(e){}
}

// ---- monitor de funding (radar do carry) ----
async function carregarFunding(){
  try{
    const arr=await apiFetch('/funding').then(r=>r.json());
    const el=document.getElementById('funding'); if(!el)return;
    if(!arr||!arr.length){el.innerHTML='<div class="mut">indisponível</div>';return;}
    const gordos=arr.filter(x=>x.gordo);
    const banner=gordos.length
      ? `<div class="fund-alert on">🔥 ${gordos.length} moeda(s) com funding GORDO — possível janela de CARRY! (${escH(gordos.map(x=>x.ativo.replace('/USDT','')).join(', '))})</div>`
      : `<div class="fund-alert">😴 Mercado calmo — funding fraco, sem prêmio de carry agora. Gatilho: funding anualizado ≥ 15%/ano.</div>`;
    // barra comparativa dentro da propria lista: a escala e o maior |anual| que veio agora
    const max=Math.max(1,...arr.map(x=>Math.abs(x.anual)));
    const linhas=arr.map(x=>{const w=Math.min(Math.abs(x.anual)/max*100,100);
      return `<tr><td class="fund-a">${x.gordo?'🔥 ':''}${escH(x.ativo.replace('/USDT',''))}</td>
        <td class="flex"><span class="fund-bar"><i class="${x.anual>=0?'b-pos':'b-neg'}" style="width:${w}%"></i></span></td>
        <td class="mono num ${x.anual>=0?'pos':'neg'}" style="font-weight:600">${x.anual>=0?'+':''}${escH(x.anual)}%</td>
        <td class="mono num mut">${escH(x.funding_pct)}%</td></tr>`;
    }).join('');
    // Sem sparkline aqui, e de proposito: o /funding devolve so o instante, nao serie. Inventar
    // uma curva a partir de um ponto seria desenho, nao dado.
    el.innerHTML=banner+'<table><thead><tr><th>Ativo</th><th class="flex">Carry (relativo)</th>'+
      '<th class="num">%/ano</th><th class="num">%/8h</th></tr></thead><tbody>'+linhas+'</tbody></table>';
  }catch(e){}
}

// ---- gráfico estilo TradingView (Lightweight Charts) + abas ----
let _tv=null,_candles=null,_plines=[],_zlines=[],_tvAtivo=null,_tvLast=0,_bookLast=0,_aba='painel',_tvTf=null;
let _indSeries={},_indOn=false,_analiseSig=null;
const TF_SEG={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400,'1d':86400};
function tfAtual(){return _tvTf||(_est&&_est.config&&_est.config.timeframe)||'15m';}
function marcarTfBtn(){document.querySelectorAll('#tv-tfs button').forEach(b=>{const sel=b.dataset.tf===_tvTf;b.classList.toggle('on',sel);b.setAttribute('aria-pressed',sel);});}
function mudarTf(tf){_tvTf=tf; marcarTfBtn(); if(_tvAtivo)recarregarGrafico(_tvAtivo);}
function toggleExpand(){
  const g=document.getElementById('view-grafico'); g.classList.toggle('expandido');
  const b=document.querySelector('.tv-expand'); if(b)b.textContent=g.classList.contains('expandido')?'⛶ Recolher':'⛶ Expandir';
  setTimeout(()=>{if(_tv)_tv.timeScale().fitContent();},80);
}
// Abas de conteudo. Guardadas fora do HTML (_sub) porque o carregar() reescreve o miolo
// dos blocos a cada 3s; o estado de qual aba esta aberta nao pode morar no que e reescrito.
let _sub='sinais';
function subaba(v){
  _sub=v;
  document.querySelectorAll('.subview').forEach(sec=>{sec.hidden=sec.dataset.sub!==v;});
  document.querySelectorAll('.subtab').forEach(b=>{const sel=b.dataset.sub===v;
    b.classList.toggle('on',sel);b.setAttribute('aria-selected',sel);b.tabIndex=sel?0:-1;});
  // o Chart.js mediu o container enquanto ele estava escondido (largura 0); ao aparecer
  // precisa remedir, senao a curva de capital nasce com 0px de largura
  if(v==='metricas'&&chart)chart.resize();
}
function aba(v){
  _aba=v;
  document.getElementById('view-painel').classList.toggle('hidden',v!=='painel');
  document.getElementById('view-grafico').classList.toggle('hidden',v!=='grafico');
  document.querySelectorAll('.tab').forEach(b=>{const sel=b.dataset.v===v;b.classList.toggle('on',sel);b.setAttribute('aria-pressed',sel);});
  // a marca vive na sidebar; o titulo da topbar diz onde voce esta, entao segue a vista
  const vt=document.getElementById('view-titulo'); if(vt)vt.textContent=v==='painel'?'Painel':'Gráfico';
  // A lib de velas entra sob demanda. Ela nunca desenhou nada na aba Painel, então esperar
  // o clique aqui é onde ela realmente faz falta. Devolve promessa porque quem chama pode
  // precisar do _tv já montado — ver analisarSinal().
  if(v!=='grafico') return Promise.resolve();
  return libTV().then(ok=>{
    if(!ok) return;
    if(!_tv)initTV();
    if(_est)prepararSelector(_est);
    if(!_tvTf)_tvTf=tfAtual(); marcarTfBtn();
    const el=document.getElementById('tvchart'); _tv.applyOptions({width:el.clientWidth,height:el.clientHeight});
    if(_tvAtivo)recarregarGrafico(_tvAtivo);
    if(_est)sidebar(_est);
  });
}
function initTV(){
  const el=document.getElementById('tvchart');
  _tv=LightweightCharts.createChart(el,{width:el.clientWidth||700,height:el.clientHeight||600,
    layout:{background:{color:'transparent'},textColor:TEMA.txt3},
    grid:{vertLines:{color:TEMA.line},horzLines:{color:TEMA.line}},
    timeScale:{timeVisible:true,borderColor:TEMA.line},rightPriceScale:{borderColor:TEMA.line}});
  // vela continua verde/vermelha: e direcao de preco, o uso legitimo do par (decisao travada 4.4)
  _candles=_tv.addCandlestickSeries({upColor:TEMA.pos,downColor:TEMA.neg,borderVisible:false,wickUpColor:TEMA.pos,wickDownColor:TEMA.neg});
  // mantém o gráfico SEMPRE do tamanho do container (resize, troca de aba, expandir)
  const ajusta=()=>{if(_tv&&el.clientWidth)_tv.applyOptions({width:el.clientWidth,height:el.clientHeight});};
  if(window.ResizeObserver){new ResizeObserver(ajusta).observe(el);}
  window.addEventListener('resize',ajusta);
}
function prepararSelector(e){
  const sel=document.getElementById('tv-ativo');
  if(sel&&!sel.options.length&&e.config){
    e.config.ativos.split(',').forEach(a=>{const o=document.createElement('option');o.value=a.trim();o.textContent=a.trim();sel.appendChild(o);});
    _tvAtivo=(e.posicoes[0]&&e.posicoes[0].ativo)||sel.options[0].value; sel.value=_tvAtivo;
    sel.onchange=()=>{_tvAtivo=sel.value;fecharAnalise();recarregarGrafico(_tvAtivo);};
  }
}
async function carregarCandles(ativo,tf){
  try{
    _plines.forEach(l=>{try{_candles.removePriceLine(l)}catch(_){}});_plines=[];  // limpa linhas do ativo anterior
    _zlines.forEach(l=>{try{_candles.removePriceLine(l)}catch(_){}});_zlines=[];   // limpa zonas de liquidez
    try{_candles.setMarkers([])}catch(_){}                                        // limpa setas anteriores
    const r=await apiFetch(`/candles?ativo=${encodeURIComponent(ativo)}&tf=${tf}&limite=200`);
    _candles.setData(await r.json());
    _candles.priceScale().applyOptions({autoScale:true});                         // reescala pro preço do novo ativo
    _tv.timeScale().fitContent();
    _tvLast=Date.now();
  }catch(e){}
}
function recarregarGrafico(ativo){
  carregarCandles(ativo,tfAtual()).then(()=>{
    if(_est)marcar(_est,ativo,tfAtual());
    carregarSmartMoney(ativo); carregarBook(ativo);
    carregarIndicadores(ativo,tfAtual()).then(a=>{
      const el=document.getElementById('g-analise');
      if(a&&_analiseSig)renderAnalise(_analiseSig,a);
      else if(el)el.innerHTML='';
    });
    if(_tv)_tv.timeScale().fitContent();
  });
}
async function analisarSinal(s){
  _analiseSig=s; _indOn=true; _tvTf=s.tf;
  await aba('grafico');                             // garante chart + selector (a lib entra sob demanda)
  _tvAtivo=s.ativo;                                 // foca no ativo do sinal
  const sel=document.getElementById('tv-ativo'); if(sel)sel.value=s.ativo;
  marcarTfBtn();
  const b=document.querySelector('.tv-ind'); if(b)b.classList.add('on');
  if(_tv)recarregarGrafico(s.ativo);
}
function garanteIndSeries(){
  if(_indSeries.ema20)return;
  // EMA20 azul (era teal, cor que saiu da paleta), EMA50 gold, Bollinger cinza-azulado.
  // Mapa de cor do DESIGN.md > Graficos: EMA20 azul (--accent-txt), EMA50 gold (--warn),
  // Bollinger cinza translucido. O roxo do tema antigo ja tinha saido, mas o cinza que ficou no
  // lugar era inventado: nao correspondia a token nenhum. Agora e o --txt2 (#A1A7BB) a 50%, que
  // e variacao de alpha DECLARADA de um token que existe.
  _indSeries.ema20=_tv.addLineSeries({color:TEMA.accentTxt,lineWidth:2,priceLineVisible:false,lastValueVisible:false});
  _indSeries.ema50=_tv.addLineSeries({color:TEMA.warn,lineWidth:2,priceLineVisible:false,lastValueVisible:false});
  _indSeries.bbU=_tv.addLineSeries({color:BOLL,lineWidth:1,priceLineVisible:false,lastValueVisible:false});
  _indSeries.bbL=_tv.addLineSeries({color:BOLL,lineWidth:1,priceLineVisible:false,lastValueVisible:false});
  _indSeries.bbM=_tv.addLineSeries({color:BOLL_MID,lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false});
}
function limparInd(){Object.values(_indSeries).forEach(s=>{try{s.setData([])}catch(_){}});}
async function carregarIndicadores(ativo,tf){
  if(!_indOn&&!_analiseSig){limparInd();return null;}
  try{
    const a=await apiFetch(`/analise?ativo=${encodeURIComponent(ativo)}&tf=${tf}`).then(r=>r.json());
    if(_indOn){garanteIndSeries();
      _indSeries.ema20.setData(a.ema20);_indSeries.ema50.setData(a.ema50);
      _indSeries.bbU.setData(a.bb_up);_indSeries.bbL.setData(a.bb_lo);_indSeries.bbM.setData(a.bb_mid);
    } else limparInd();
    return a;
  }catch(e){return null;}
}
function toggleIndicadores(){
  _indOn=!_indOn;
  const b=document.querySelector('.tv-ind'); if(b)b.classList.toggle('on',_indOn);
  if(_tvAtivo)recarregarGrafico(_tvAtivo);
}
function renderAnalise(s,a){
  const el=document.getElementById('g-analise'); if(!el)return;
  const snap=a.snapshot, pa=_precos[s.ativo]||snap.preco, st=statusEntrada(s,pa);
  el.innerHTML=`<div class="analise-box">
    <div class="gs-titulo" style="display:flex;justify-content:space-between;align-items:center">🔍 Análise do sinal <span style="cursor:pointer;font-size:13px" data-acao="fecharAnalise">✕</span></div>
    <div style="font-size:14px;font-weight:700;margin-bottom:7px">${escH(s.ativo)} <span class="tag ${s.direcao==='LONG'?'long':'short'}">${escH(s.direcao)}</span> <span class="tipo-badge tipo-${escH(s.tipo)}">${s.tipo==='reversao'?'↩ reversão':'📈 tendência'}</span> <span class="tf-badge">${escH(s.tf)}</span></div>
    <div style="font-size:12px;line-height:1.6;color:var(--txt3)">${escH(a.leitura)}</div>
    <div class="grid-ind">
      <span class="mut">RSI</span><b>${escH(snap.rsi)}</b>
      <span class="mut">ADX</span><b>${escH(snap.adx)}</b>
      <span class="mut">EMA20</span><b style="color:var(--accent-txt)">${num(snap.ema20)}</b>
      <span class="mut">EMA50</span><b style="color:var(--warn)">${num(snap.ema50)}</b>
      <span class="mut">Bollinger</span><b style="color:var(--txt2)">${num(snap.bb_lo)}–${num(snap.bb_up)}</b><!-- mesma cor da banda no grafico -->
    </div>
    <div style="margin-top:9px;font-size:12px">entrada <b>${num(s.preco)}</b> · stop <b class="neg">${num(s.stop_sugerido)}</b></div>
    <div class="entry-status ${st.cls}" style="margin-top:8px">${st.txt}</div>
    <button class="btn-op" style="width:100%;margin-top:11px" data-acao="abrirModal" data-sinal='${escH(JSON.stringify(s))}'>⚡ Operar este sinal</button>
  </div>`;
}
function fecharAnalise(){_analiseSig=null;const el=document.getElementById('g-analise');if(el)el.innerHTML='';}
async function carregarSmartMoney(ativo){
  try{
    const s=await apiFetch('/smartmoney?ativo='+encodeURIComponent(ativo)).then(r=>r.json());
    _zlines.forEach(l=>{try{_candles.removePriceLine(l)}catch(_){}});_zlines=[];
    (s.liquidez_acima||[]).forEach(p=>_zlines.push(_candles.createPriceLine({price:p,color:TEMA.warn,lineWidth:1,lineStyle:3,axisLabelVisible:true,title:'liq ↑'})));
    (s.liquidez_abaixo||[]).forEach(p=>_zlines.push(_candles.createPriceLine({price:p,color:TEMA.warn,lineWidth:1,lineStyle:3,axisLabelVisible:true,title:'liq ↓'})));
    const el=document.getElementById('g-smart');
    if(el)el.innerHTML=`<div style="font-size:13px">Funding: <b class="${(s.funding_pct||0)>=0?'pos':'neg'}">${escH(s.funding_pct??'—')}%</b></div>
      <div class="mut" style="font-size:11px;margin:5px 0 9px">${escH(s.leitura_funding||'')}</div>
      <div class="mut" style="font-size:11px">🟡 liquidez acima: ${(s.liquidez_acima||[]).map(num).join(' · ')||'—'}</div>
      <div class="mut" style="font-size:11px;margin-top:3px">🟡 liquidez abaixo: ${(s.liquidez_abaixo||[]).map(num).join(' · ')||'—'}</div>`;
  }catch(e){}
}
async function carregarBook(ativo){
  try{
    const b=await apiFetch('/book?ativo='+encodeURIComponent(ativo)).then(r=>r.json());
    const el=document.getElementById('g-book'); if(!el||!b)return;
    const corLado=b.lado_grande==='COMPRA'?'pos':(b.lado_grande==='VENDA'?'neg':'mut');
    el.innerHTML=`
      <div style="font-size:11px;color:var(--txt3);margin-bottom:3px">Pressão no book (±1%)</div>
      <div style="display:flex;height:8px;border-radius:4px;overflow:hidden;margin-bottom:6px">
        <div style="width:${escH(b.pressao_compra)}%;background:var(--pos)"></div><div style="flex:1;background:var(--neg)"></div></div>
      <div style="font-size:11.5px;display:flex;justify-content:space-between"><span class="pos">${escH(b.pressao_compra)}% compra</span><span class="neg">${(100-b.pressao_compra).toFixed(1)}% venda</span></div>
      <div style="font-size:12.5px;margin-top:10px">Fluxo taker: <b class="${b.fluxo_comprador>=50?'pos':'neg'}">${escH(b.fluxo_comprador)}% comprando</b></div>
      <div style="font-size:12.5px;margin-top:6px">💰 Dinheiro grande: <b class="${corLado}">${escH(b.lado_grande)}</b> <span class="mut" style="font-size:10.5px">(C R$${(b.grande_compra/1000).toFixed(0)}k · V R$${(b.grande_venda/1000).toFixed(0)}k)</span></div>
      <div class="mut" style="font-size:10.5px;margin-top:8px">🟢 parede ${num(b.parede_compra.preco)} · R$${(b.parede_compra.valor/1000).toFixed(0)}k</div>
      <div class="mut" style="font-size:10.5px">🔴 parede ${num(b.parede_venda.preco)} · R$${(b.parede_venda.valor/1000).toFixed(0)}k</div>`;
  }catch(e){}
}
function marcar(e,ativo,tf){
  if(!_candles)return;
  _plines.forEach(l=>{try{_candles.removePriceLine(l)}catch(_){}});_plines=[];
  (e.posicoes||[]).filter(p=>p.ativo===ativo).forEach(p=>{
    const cor=p.direcao==='LONG'?TEMA.pos:TEMA.neg;
    _plines.push(_candles.createPriceLine({price:p.entrada,color:cor,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:`${p.direcao} entrada`}));
    if(p.stop)_plines.push(_candles.createPriceLine({price:p.stop,color:TEMA.neg,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'stop'}));
  });
  const seg=TF_SEG[tf]||900, mk=[];
  const snap=dt=>Math.floor(new Date(String(dt).replace(' ','T')).getTime()/1000/seg)*seg;
  (e.trades||[]).filter(t=>t.ativo===ativo&&t.aberto_em).forEach(t=>mk.push({time:snap(t.aberto_em),position:t.direcao==='LONG'?'belowBar':'aboveBar',color:t.direcao==='LONG'?TEMA.pos:TEMA.neg,shape:t.direcao==='LONG'?'arrowUp':'arrowDown',text:t.direcao}));
  (e.posicoes||[]).filter(p=>p.ativo===ativo&&p.aberto_em).forEach(p=>mk.push({time:snap(p.aberto_em),position:p.direcao==='LONG'?'belowBar':'aboveBar',color:TEMA.warn,shape:p.direcao==='LONG'?'arrowUp':'arrowDown',text:p.direcao+' aberta'}));
  mk.sort((a,b)=>a.time-b.time);
  try{_candles.setMarkers(mk)}catch(_){}
}
function sidebar(e){
  const gp=document.getElementById('g-posicoes');
  if(gp)gp.innerHTML=(e.posicoes&&e.posicoes.length)?e.posicoes.map(p=>{const roe=p.valor_reais?p.pnl/p.valor_reais*100:0, sd=_saidas[p.id];
    return `<div style="font-size:13px;padding:7px 0;border-bottom:1px solid var(--line)">${escH(p.ativo)} <span class="tag ${p.direcao==='LONG'?'long':'short'}">${escH(p.direcao)}</span><br><span class="mut" style="font-size:11px">R$${escH(p.valor_reais)}·${escH(p.alavancagem)}x</span> <span class="mono ${p.pnl>=0?'pos':'neg'}">${brl(p.pnl)} <b>${pct(roe)}</b></span>${(sd&&sd.acao)?`<div class="saida-side saida-${escH(sd.nivel)}" style="font-size:10.5px;margin-top:4px;padding:3px 6px;border-radius:5px">${escH(sd.acao)}</div>`:''}</div>`}).join(''):'<div class="mut" style="font-size:12px">nenhuma</div>';
  const gt=document.getElementById('g-trades');
  if(gt)gt.innerHTML=(e.trades&&e.trades.length)?e.trades.slice(0,15).map(t=>`<div style="font-size:12.5px;padding:6px 0;border-bottom:1px solid var(--line)">${escH(t.ativo)} <span class="tag ${t.direcao==='LONG'?'long':'short'}">${escH(t.direcao)}</span> <span class="mono ${t.pnl_reais>=0?'pos':'neg'}">${brl(t.pnl_reais)}</span></div>`).join(''):'<div class="mut" style="font-size:12px">nenhum</div>';
}
function atualizarGrafico(e){
  if(_aba!=='grafico'||!_tv)return;
  if(_tvAtivo&&Date.now()-_tvLast>30000){recarregarGrafico(_tvAtivo);}
  else if(_tvAtivo)marcar(e,_tvAtivo,tfAtual());
  if(_tvAtivo&&Date.now()-_bookLast>6000){carregarBook(_tvAtivo);_bookLast=Date.now();}
  sidebar(e);
}

function abrirModal(s){_sig=s; _modalTrigger=document.activeElement;
  // o dialogo cresce de onde o clique saiu. Sem gatilho conhecido (teclado, chamada direta),
  // cai no centro, que e o comportamento antigo.
  try{ const m=document.querySelector('.modal');
    if(m&&_modalTrigger&&_modalTrigger.getBoundingClientRect){
      const r=_modalTrigger.getBoundingClientRect();
      m.style.transformOrigin=`${Math.round(r.left+r.width/2)}px ${Math.round(r.top+r.height/2)}px`;
    } else if(m){ m.style.transformOrigin='center'; }
  }catch(_){}
  document.getElementById('m-titulo').textContent=`${s.direcao} ${s.ativo}`;
  document.getElementById('m-sub').textContent=`convicção ${s.conviccao} · ${s.tipo||'tendência'} · ${s.tf||''} · entrada ~${s.preco}`;
  if(_est?.config){document.getElementById('m-lev').value=_est.config.alavancagem_padrao||10;
    document.getElementById('m-risco').value=(parseFloat(_est.config.risco_por_trade||0.03)*100);}
  usarSugestao(); document.getElementById('overlay').classList.add('on');
  setTimeout(()=>{const v=document.getElementById('m-valor'); if(v){v.focus();v.select();}},50);}   // foco no 1o campo
function fecharModal(){document.getElementById('overlay').classList.remove('on');_sig=null;
  // O poll reescreve #pendentes a cada 3s: enquanto o modal esta aberto, o botao guardado em
  // _modalTrigger vira no DETACHED, e focar um no fora do documento joga o foco no body. Por
  // isso o gatilho carrega data-foco, uma identidade que sobrevive ao rerender.
  let alvo=_modalTrigger;
  if(alvo&&!document.body.contains(alvo)&&alvo.dataset&&alvo.dataset.foco)
    alvo=document.querySelector('[data-foco="'+alvo.dataset.foco+'"]');
  if(alvo&&alvo.focus)alvo.focus();
  _modalTrigger=null;}
function calcSugestao(){
  const l=+document.getElementById('m-lev').value||1, risco=(+document.getElementById('m-risco').value||3)/100;
  const banca=_est&&_est.banca?_est.banca.atual:1000;
  const taxa=(_est&&_est.config?parseFloat(_est.config.taxa_por_lado):0.0005)||0.0005;
  const sd=_sig?Math.abs(_sig.preco-_sig.stop_sugerido)/_sig.preco:0.03;
  const sdEf=Math.min(sd,0.9/l);                                             // R efetivo = min(stop, liquidação)
  const valor=Math.max(1,Math.round(banca*risco/Math.max((sdEf+2*taxa)*l,0.0001)));  // inclui taxa -> arrisca risco% de verdade
  return {valor, sd, sdEf, taxa, banca, risco, l};
}
function usarSugestao(){document.getElementById('m-valor').value=calcSugestao().valor; previa();}
function previa(){
  const v=+document.getElementById('m-valor').value||0, l=+document.getElementById('m-lev').value||1;
  const sug=calcSugestao(), sd=sug.sd, taxa=sug.taxa;
  const liq=0.9/l, liqAntes=liq<sd, sdEf=Math.min(sd,liq);                    // R efetivo = min(stop, liquidação)
  const perdaBruta=v*l*(sdEf+2*taxa), perdaStop=Math.min(perdaBruta,v);       // inclui taxa, capada na margem
  const perdaPct=sug.banca?perdaStop/sug.banca*100:0;
  const wr=((_est&&_est.metricas&&_est.metricas.por_conviccao)||[]).find(c=>{const p=c.faixa.split('-').map(Number);return _sig&&_sig.conviccao>=p[0]&&_sig.conviccao<p[1];});
  document.getElementById('m-prev').innerHTML=
   `<div class="row"><span class="mut">Stop sugerido</span><span class="mono">${num(_sig?_sig.stop_sugerido:0)} (${(sd*100).toFixed(2)}%)</span></div>
    <div class="row"><span class="mut">R efetivo (min stop/liq)</span><span class="mono ${liqAntes?'warn':''}">${(sdEf*100).toFixed(2)}%${liqAntes?' ← liquida antes do stop ⚠️':''}</span></div>
    <div class="row"><span class="mut">Nocional</span><span class="mono">${brl(v*l)}</span></div>
    <div class="row"><span class="mut">Perda no pior caso (c/ taxa)</span><span class="mono neg">${brl(perdaStop)} (${perdaPct.toFixed(1)}% da banca)${perdaBruta>=v?' · margem inteira':''}</span></div>
    ${(_est&&_est.risco&&_est.risco.risco_aberto_max_rs)?(()=>{const nt=_est.risco.risco_aberto_rs+perdaStop,tt=_est.risco.risco_aberto_max_rs;return `<div class="row"><span class="mut">Exposição após este trade</span><span class="mono ${nt>tt?'neg':''}">${brl(nt)} / ${brl(tt)} ${nt>tt?'⛔ estoura o teto':''}</span></div>`;})():''}
    ${liqAntes?`<div class="aviso-liq">⚠️ Alavancagem alta pra esse stop — você LIQUIDA antes do stop agir (perde ~a margem). Baixe pra ≤ ${Math.floor(0.9/sd)}x pro stop valer.</div>`:''}
    <div class="row" style="margin-top:7px"><span class="mut">💡 Tamanho p/ arriscar ${(sug.risco*100).toFixed(1)}%</span><span><b class="mono">${brl(sug.valor)}</b> <button class="btn-sug" data-acao="usarSugestao">usar</button></span></div>
    ${wr?`<div class="mut" style="font-size:11px;margin-top:7px">📊 Win rate histórico nessa faixa: <b>${escH(wr.win_rate)}%</b> (${escH(wr.n)} trades) — referência, não garantia.</div>`:''}`;
}

async function confirmarTrade(){if(_busy||!_sig)return; _busy=true;        // trava: evita abrir 2 trades no duplo-clique
  const cbtn=document.getElementById('m-conf'); if(cbtn){cbtn.disabled=true;cbtn.textContent='Confirmando…';}
  const valor=+document.getElementById('m-valor').value, lev=+document.getElementById('m-lev').value;
  try{const r=await api('/confirmar',{sinal_id:_sig.id,valor_reais:valor,alavancagem:lev});
    if(r&&r.ok===false){toast(r.erro);return;}
    toast(`✅ ${_sig.direcao} ${_sig.ativo} aberto — R$${valor} @ ${lev}x`);fecharModal();carregar();}
  catch(e){toast('erro: '+e.message);}
  finally{_busy=false; if(cbtn){cbtn.disabled=false;cbtn.textContent='✅ Confirmar';}}}
// Texto que vem de fora (backend, e por ele de API de terceiro) nunca entra cru em innerHTML.
function escH(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function pular(id){
  try{const r=await api('/pular',{id}); if(r&&r.ok===false)toast(r.erro||'sinal não está mais na fila'); carregar();}
  catch(e){toast('erro: '+e.message);}}
// Fechar pedia UM clique, numa tabela que se redesenha a cada 3 s: uma posição nova empurra as
// linhas e o clique caía no Fechar de outra. Agora confirma dizendo QUAL posição, e a recusa
// do backend ({ok:false}) ou a posição já fechada (pnl null) param de virar "fechada, R$ 0,00".
async function fechar(id){
  const p=((_est&&_est.posicoes)||[]).find(x=>x.id===id);
  const qual=p?`${p.direcao} ${p.ativo} (P&L agora ${brl(p.pnl)})`:`a posição #${id}`;
  if(!confirm(`Fechar ${qual} a mercado?`))return;
  try{const r=await api('/fechar',{id});
    if(r&&r.ok===false)toast(r.erro||'não fechou');
    else toast(r.pnl==null?'A posição já estava fechada':`Posição fechada — P&L ${brl(r.pnl)}`);
    carregar();}
  catch(e){toast('erro ao fechar: '+e.message);}}
async function escanear(){toast('🔍 escaneando...');await api('/scan',{});carregar();}
// O reset apaga sinais, posições, trades e a curva, sem backup. Um OK num confirm() mandava a
// palavra-chave sozinho e anulava a guarda do backend; agora é a pessoa que digita.
async function resetar(){
  const w=prompt('Resetar APAGA sinais, posições, trades e a curva desta conta, sem volta.\nDigite RESET para confirmar:');
  if(w!=='RESET'){ if(w!=null)toast('reset cancelado: a palavra não confere'); return; }
  try{await api('/reset',{confirmar:'RESET'});toast('↻ simulação resetada');carregar();}
  catch(e){toast('reset recusado: '+e.message);}}
async function criarDca(){if(_busy)return;
  const ativo=document.getElementById('dca-ativo').value, valor=+document.getElementById('dca-valor').value, freq=+document.getElementById('dca-freq').value;
  if(!ativo||valor<=0||freq<=0){toast('preencha ativo/valor/frequência');return;}
  _busy=true;
  try{await api('/dca',{ativo,valor_aporte:valor,freq_dias:freq}); toast(`💰 Plano DCA criado: ${ativo} R$${valor}/${freq}d`); carregar();}
  finally{_busy=false;}
}
async function aportarDca(id){const r=await api('/dca/aportar',{id}); toast(r.ok?`💰 Aporte feito @ ${num(r.preco)}`:'erro no aporte'); carregar();}
async function removerDca(id){if(!confirm('Remover este plano DCA?'))return; await api('/dca/remover',{id}); toast('plano removido'); carregar();}
// O pânico DESLIGA o bot e CANCELA as ordens antes de fechar posição. Este botão voltava sem
// chamar o backend quando não havia posição aberta: com o bot ligado e ordens descansando, o
// dono apertava, lia "Nenhuma posição aberta" e o bot seguia abrindo. Agora chama sempre.
async function panico(){
  const n=(_est&&_est.posicoes)?_est.posicoes.length:0, no=(_est&&_est.ordens)?_est.ordens.length:0;
  if(!confirm(`🛑 PÂNICO: desliga o bot, cancela ${no} ordem(ns) pendente(s) e fecha ${n} posição(ões) a mercado. Confirmar?`))return;
  try{const r=await api('/panico',{});
    const falhou=(r.falhas||[]).length;
    toast(`🛑 bot desligado · ${r.fechadas} posição(ões) fechada(s) · ${r.ordens_canceladas||0} ordem(ns) cancelada(s) · P&L ${brl(r.pnl)}`);
    if(falhou)alert(`ATENÇÃO: ${falhou} posição(ões) NÃO fecharam (${r.falhas.map(f=>f.ativo).join(', ')}). O bot está desligado; aperte o pânico de novo ou feche à mão.`);
    carregar();}
  catch(e){alert('O PÂNICO FALHOU: '+e.message+'\nNada garante que o bot foi desligado. Tente de novo.');}}

async function carregarSaidas(){
  try{
    const arr=await apiFetch('/saidas').then(r=>r.json());
    _saidas={};
    (arr||[]).forEach(s=>{ _saidas[s.posicao_id]=s;
      if((s.nivel==='forte'||s.nivel==='lucro') && _saidasVistas[s.posicao_id]!==s.nivel){
        toast(`🔔 ${s.ativo}: ${s.acao}`); _saidasVistas[s.posicao_id]=s.nivel;
      }
    });
  }catch(e){}
}
async function carregarPrecos(){
  try{
    const ativos=[...new Set((_est?.pendentes||[]).map(s=>s.ativo))];
    if(!ativos.length){_precos={};return;}
    _precos=await apiFetch('/precos?ativos='+encodeURIComponent(ativos.join(','))).then(r=>r.json());
    anotaSerie(_precos);
    if(_est)carregarPendentes(_est);          // redesenha com o preco novo sem esperar o /estado
  }catch(e){}
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('overlay').classList.contains('on'))fecharModal();});
// Expandir pelo teclado. Delegado no document porque a lista e reescrita a cada 3s e um
// listener preso na linha morreria junto com ela.
document.addEventListener('keydown',e=>{
  const tr=e.target&&e.target.classList&&e.target.classList.contains('sig-row')?e.target:null;
  if(tr&&(e.key==='Enter'||e.key===' ')){ e.preventDefault(); toggleSinal(e,+tr.dataset.sid); }
});
// ---- cliques ----------------------------------------------------------------
// Era onclick= em cada botao. Sob `script-src 'self'` handler em atributo nao executa: o elemento
// agora so DIZ a acao, em data-acao, e quem a executa e uma destas duas tabelas. Nome que nao
// esta na tabela nao faz nada.
// Duas tabelas, de proposito. Os botoes escritos no classico.html recebem o listener NELES, uma
// vez, aqui no boot, antes de qualquer dado do backend entrar na tela. Um data-acao="panico" que
// aparecesse depois (HTML injetado por um campo que escapasse do escH) nao esta preso a nada, e
// a delegacao de baixo nao o atende: so conhece as acoes de linha.
const ACOES_FIXAS={
  trocaConta:el=>trocaConta(el.dataset.conta), aba:el=>aba(el.dataset.v),
  subaba:el=>subaba(el.dataset.sub), mudarTf:el=>mudarTf(el.dataset.tf),
  escanear:()=>escanear(), panico:()=>panico(), resetar:()=>resetar(), sairLogin:()=>sairLogin(),
  criarDca:()=>criarDca(), toggleAuto:()=>toggleAuto(), salvarAuto:()=>salvarAuto(),
  toggleIndicadores:()=>toggleIndicadores(), toggleExpand:()=>toggleExpand(),
  fecharModal:()=>fecharModal(), confirmarTrade:()=>confirmarTrade(),
};
// O que o render reescreve (linhas de sinal, posicao e DCA, a caixa de analise, a previa do
// modal): delegado no document, pelo mesmo motivo do keydown acima. O id vem de data-id/data-sid
// e o sinal de data-sinal, que entra no atributo ja escapado (ver linhaSinal).
const ACOES_LINHA={
  toggleSinal:(el,ev)=>toggleSinal(ev,+el.dataset.sid),
  abrirModal:el=>abrirModal(JSON.parse(el.dataset.sinal)),
  analisarSinal:el=>analisarSinal(JSON.parse(el.dataset.sinal)),
  pular:el=>pular(+el.dataset.id), fechar:el=>fechar(+el.dataset.id),
  aportarDca:el=>aportarDca(+el.dataset.id), removerDca:el=>removerDca(+el.dataset.id),
  fecharAnalise:()=>fecharAnalise(), usarSugestao:()=>usarSugestao(),
};
const acaoDe=(tabela,el)=>Object.prototype.hasOwnProperty.call(tabela,el.dataset.acao)?tabela[el.dataset.acao]:null;
document.querySelectorAll('[data-acao]').forEach(el=>{
  const f=acaoDe(ACOES_FIXAS,el); if(f)el.addEventListener('click',()=>f(el)); });
document.addEventListener('click',ev=>{
  const el=ev.target&&ev.target.closest&&ev.target.closest('[data-acao]');
  const f=el&&acaoDe(ACOES_LINHA,el); if(f)f(el,ev); });
// Os tres campos do modal recalculam a previa a cada tecla (era oninput= em cada um).
['m-valor','m-lev','m-risco'].forEach(id=>document.getElementById(id).addEventListener('input',()=>previa()));
// ---- auto-trader (experimento) ----
function renderAuto(e){
  const cfg=e.config||{}, a=e.auto||{};
  const on=String(cfg.auto_trade)==='1'||cfg.auto_trade===true;
  const panel=document.getElementById('auto-panel'); if(!panel)return;
  panel.classList.toggle('on',on);
  const btn=document.getElementById('auto-toggle');
  if(btn){btn.textContent=on?'🟢 Bot ATIVO — desativar':'Ativar bot 🤖';btn.classList.toggle('on',on);btn.setAttribute('aria-pressed',on);}
  const af=document.activeElement;                                   // não rouba foco se estiver editando
  const setIf=(id,v)=>{const el=document.getElementById(id); if(el&&el!==af&&v!=null&&v!=='')el.value=v;};
  setIf('a-conv',cfg.auto_conviccao_min);
  setIf('a-risco',cfg.risco_por_trade!=null?(parseFloat(cfg.risco_por_trade)*100):null);
  setIf('a-maxpos',cfg.auto_max_posicoes);
  const modoConv=String(cfg.auto_lev_modo||'conviccao')==='conviccao';
  const cb=document.getElementById('a-levmodo'); if(cb&&cb!==af)cb.checked=modoConv;
  const lbl=document.getElementById('a-lev-lbl'); if(lbl)lbl.childNodes[0].nodeValue=modoConv?'Alav. teto (x)':'Alavancagem (x)';
  setIf('a-lev',modoConv?cfg.auto_lev_max:cfg.alavancagem_padrao);
  const st=document.getElementById('auto-status');
  if(st){ if(!on){st.innerHTML='<span class="auto-badge"></span> desligado';}
    else{ const ab=(a.abertos||[]).length, fc=(a.fechados||[]).length;
      let txt='<span class="auto-badge on"></span> ativo — ';
      if(ab||fc) txt+=`última ação: ${ab} aberto(s), ${fc} fechado(s)`;
      else if(a.motivo) txt+=escH(a.motivo);
      else txt+='monitorando sinais frescos…';
      if(a.ts) txt+=` <span class="mut">(${escH(String(a.ts).slice(11,19))})</span>`;
      st.innerHTML=txt; } }
  const lg=document.getElementById('auto-log');
  if(lg){ const ls=[];
    (a.abertos||[]).forEach(o=>ls.push(`🟢 abriu ${escH(o.direcao)} ${escH(o.ativo)} ${escH(o.tf||'')} — R$${escH(o.valor)} @ ${escH(o.lev)}x (conv ${escH(o.conviccao)})`));
    (a.fechados||[]).forEach(f=>ls.push(`⚪ fechou ${escH(f.ativo)} — P&L R$${escH(f.pnl)} (${escH(f.motivo)})`));
    (a.rejeitados||[]).forEach(r=>ls.push(`<span class="mut">⏭️ pulou ${escH(r.ativo)}: ${escH(r.erro)}</span>`));
    lg.innerHTML=ls.length?ls.join('<br>'):''; }
}
async function toggleAuto(){
  if(_busy)return; _busy=true;
  const on=String(_est&&_est.config&&_est.config.auto_trade)==='1';
  const btn=document.getElementById('auto-toggle'); if(btn)btn.disabled=true;
  try{ await api('/auto',{auto_trade:on?'0':'1'}); toast(on?'Bot desativado':'🤖 Bot ATIVADO — paper trading'); carregar(); }
  catch(e){ toast('erro: '+e.message); }
  finally{ _busy=false; if(btn)btn.disabled=false; }
}
async function salvarAuto(){
  if(_busy)return; _busy=true;
  const modoConv=document.getElementById('a-levmodo').checked;
  const levVal=document.getElementById('a-lev').value;
  const body={ auto_conviccao_min:document.getElementById('a-conv').value,
    risco_por_trade:(parseFloat(document.getElementById('a-risco').value)/100),
    auto_max_posicoes:document.getElementById('a-maxpos').value };
  // Esta tela desenha DOIS modos de alavancagem e o catálogo tem três. Com `auto_lev_modo=risco`
  // (alavancagem pela conta do trade) o checkbox aparecia desmarcado e o Salvar gravava "fixo":
  // mexer na convicção mínima trocava o modo de alavancagem sem aviso. Modo que a tela não
  // conhece não é tocado, nem os dois campos que dependem dele. Sem o primeiro /estado não há
  // como saber o modo, então também não se envia.
  const modoAtual=String((_est&&_est.config&&_est.config.auto_lev_modo)||'');
  if(modoAtual==='conviccao'||modoAtual==='fixo'){
    body.auto_lev_modo=modoConv?'conviccao':'fixo';
    if(modoConv) body.auto_lev_max=levVal; else body.alavancagem_padrao=levVal;
  }
  try{ await api('/auto',body); toast('Config do bot salva'); carregar(); }
  catch(e){ toast('erro: '+e.message); }
  finally{ _busy=false; }
}
const _timers=[];
function iniciarPolling(){ if(_timers.length)return;
  _timers.push(setInterval(carregar,3000), setInterval(carregarSentimento,60000),
    setInterval(carregarFunding,60000), setInterval(carregarSaidas,8000), setInterval(carregarPrecos,8000)); }
function pararPolling(){ _timers.forEach(clearInterval); _timers.length=0; }
// carregarPrecos() precisa de _est.pendentes para saber que ativos pedir. Disparado em
// paralelo com o carregar(), o primeiro pedido saia vazio e as colunas Agora/Delta/Tendencia
// ficavam em "—" ate o poll de 8s. Encadear custa nada e enche a tabela de primeira.
function cargaInicial(){ carregar().then(carregarPrecos); carregarSentimento(); carregarFunding(); carregarSaidas(); }
// Sem gate preventivo: se o backend exigir senha, o tratamento de 401 no apiFetch abre a
// tela de login e para o polling. Com o backend aberto, ela nunca aparece. A credencial do
// localStorage é reaproveitada: descartá-la aqui obrigava a redigitar login a cada F5, e
// foi essa fricção que levou a desligar a senha no servidor. Credencial que não serve mais
// é limpa no tratamento de 401, que é onde se descobre isso.
$g('gate-form').addEventListener('submit',gateEntrar);
$g('gate-eye').addEventListener('click',()=>{ const i=$g('gate-pass'), oculto=i.type==='password';
  i.type=oculto?'text':'password'; const b=$g('gate-eye');
  b.textContent=oculto?'\u{1F648}':'\u{1F441}'; b.setAttribute('aria-label',oculto?'Ocultar senha':'Mostrar senha'); i.focus(); });
// Caps Lock explica metade dos "a senha está certa e não entra".
['keydown','keyup'].forEach(ev=>$g('gate-pass').addEventListener(ev,e=>{
  $g('gate-caps').classList.toggle('on', !!(e.getModifierState&&e.getModifierState('CapsLock'))); }));

// A status bar e fixa: sem folga embaixo ela cobriria a ultima linha da tabela. A folga e
// MEDIDA, nao chutada, porque a barra quebra de linha quando a tela aperta.
function folgaStatusBar(){ const sb=document.querySelector('.statusbar'); if(!sb)return;
  const h=sb.offsetHeight;
  document.body.style.paddingBottom=(h+8)+'px';
  document.documentElement.style.setProperty('--sb-h',h+'px'); }
// A PRIMEIRA medida vai em requestAnimationFrame; as outras (ResizeObserver) já chegam pelo
// caminho do próprio browser. Ler offsetHeight aqui, direto no boot, forçava o layout do
// documento inteiro no meio do script — 82 ms medidos em produção (forced-reflow-insight) —
// e as duas linhas que vêm logo abaixo, que disparam as requisições, só saíam depois disso.
// O layout tem que acontecer de qualquer jeito; o que muda é a ORDEM: agora a rede começa
// primeiro e a medida ocorre no quadro seguinte. O callback de rAF roda ANTES da pintura
// desse quadro, então a folga já está aplicada quando a tela aparece: nada salta.
requestAnimationFrame(folgaStatusBar);
if(window.ResizeObserver){ const sb=document.querySelector('.statusbar');
  if(sb)new ResizeObserver(folgaStatusBar).observe(sb); }
else window.addEventListener('resize',folgaStatusBar);

// App instalavel: o service worker guarda so a casca (ver web/sw.js). Ele so existe em https
// ou localhost; no http da VM o navegador recusa e o painel segue igual, sem app.
if('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(()=>{});

// [AB-1] marca a conta ativa: botão pressionado, faixa roxa na B e o título da aba do navegador,
// para não haver dúvida de qual banca está na tela antes de apertar Pânico ou Resetar.
document.querySelectorAll('.conta-sel button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.conta===CONTA)));
if(CONTA!=='A'){ document.body.classList.add('conta-teste'); document.title='[Teste '+CONTA+'] '+document.title; }

cargaInicial(); iniciarPolling();
// pausa o polling quando a aba fica oculta (economia de CPU/rede; sem rebuilds inúteis)
document.addEventListener('visibilitychange',()=>{ if(document.hidden){ pararPolling(); } else { cargaInicial(); iniciarPolling(); } });
