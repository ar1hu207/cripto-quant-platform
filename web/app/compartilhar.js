/* Apollux · card de resultado do mês para marketing [SHARE-1].

   Um PNG gerado no próprio navegador (canvas), sem lib e sem servidor: a % do mês, o win rate, o
   número de operações e o payoff da conta aberta, com a logo. NUNCA valor em R$: o card sai da casa
   para a rede social, e a banca é assunto do dono.

   Os números são os MESMOS do Painel, pela mesma conta, para o card não contradizer a tela:
   - % do mês = P&L FECHADO no mês ÷ (banca de agora − P&L fechado desde o dia 1) — o chip "no mês" do
     celular e o KPI do desktop. Para um mês passado, a base é a banca no dia 1 daquele mês, que é a de
     agora menos tudo o que fechou desde então.
   - win rate = trades com pnl_reais > 0 sobre os MEDIDOS (pnl_reais não nulo), a regra do db.metricas
     ([P2-36]): empate é perda, ausência não entra. Aqui só do mês, não da vida da conta.
   - payoff = ganho médio ÷ |perda média| do mês: razão, não dinheiro.
   Mês só aparece para escolha se o /trades?limite=500 o cobre inteiro desde o dia 1: mês cortado no
   limite daria uma % inventada, e card de marketing errado é pior que card nenhum.

   O rodapé diz que a conta é simulada. Não é enfeite: é paper trading com preço real, e publicar a %
   sem dizer isso vende como real um resultado que não foi (CLAUDE.md: não maquiar o resultado).

   Salvar: no celular, navigator.share com o arquivo abre a folha do sistema, onde "Salvar imagem" vai
   direto para a galeria (Fotos no iPhone). O arquivo é gerado ANTES do toque, porque o Safari só aceita
   share() no mesmo gesto, sem await no meio. Sem share de arquivo (desktop), baixa o PNG.
   A prévia é data: (a CSP do vercel.json libera img-src data:, não blob:). */
(function () {
  'use strict';
  var A = window.APX; if (!A) return;
  var F = A.fmt, esc = A.esc;
  var LIM = 500;
  var MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  var MES3 = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  /* Cores fixas da marca (paleta Osso), não as da paleta escolhida no app: o card é peça da marca. */
  var C = { bg: '#0B0B0C', panel: '#121214', line: '#2A2A2F', txt: '#EDEDEF', txt2: '#9A9AA3', mute: '#8A8A92',
    accent: '#E8E4D9', pos: '#3FD98C', posRgb: '63,217,140', neg: '#FF5A5F', negRgb: '255,90,95' };
  var FD = "'Syne','DM Sans',system-ui,sans-serif", FU = "'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif",
    FM = "'Fira Code','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace";
  var ICONE = '<svg class="ic" width="19" height="19" viewBox="0 0 24 24" aria-hidden="true" style="stroke:currentColor;fill:none;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round"><path d="M12 15V3M8 7l4-4 4 4"/><path d="M5 11v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8"/></svg>';

  /* ---------------- dados ---------------- */
  function mesDe(s) { return String(s || '').slice(0, 7); }
  function rotuloMes(mk) { var p = mk.split('-'); return MESES[+p[1] - 1] + ' ' + p[0]; }
  function curtoMes(mk) { var p = mk.split('-'); return MES3[+p[1] - 1] + '/' + p[0].slice(2); }
  function diasNoMes(mk) { var p = mk.split('-'); return new Date(+p[0], +p[1], 0).getDate(); }

  /* trades medidos e ordenados; meses cobertos inteiros pelo limite de 500 */
  function preparar(lista) {
    var tr = (lista || []).filter(function (t) { return t && t.fechado_em; })
      .sort(function (a, b) { return a.fechado_em < b.fechado_em ? -1 : 1; });
    var mkHoje = mesDe(A.hoje()), meses = [mkHoje], cortado = tr.length >= LIM;
    tr.forEach(function (t) { var m = mesDe(t.fechado_em); if (meses.indexOf(m) < 0) meses.push(m); });
    meses.sort().reverse();
    /* com o limite cheio, o mês do trade mais antigo pode ter começado antes dele: fica de fora */
    if (cortado) meses = meses.filter(function (m) { return m > mesDe(tr[0].fechado_em); });
    return { tr: tr, meses: meses.slice(0, 12), mkHoje: mkHoje };
  }

  function calcular(D, mk, banca) {
    var ini = mk + '-01', desde = 0, doMes = [];
    D.tr.forEach(function (t) {
      if (t.fechado_em.slice(0, 10) >= ini) desde += t.pnl_reais || 0;
      if (mesDe(t.fechado_em) === mk) doMes.push(t);
    });
    var base = banca - desde, pnl = 0, med = [], g = [], p = [];
    doMes.forEach(function (t) { pnl += t.pnl_reais || 0; if (t.pnl_reais != null) { med.push(t); (t.pnl_reais > 0 ? g : p).push(t.pnl_reais); } });
    var soma = function (a) { return a.reduce(function (x, y) { return x + y; }, 0); };
    var gm = g.length ? soma(g) / g.length : 0, pm = p.length ? Math.abs(soma(p) / p.length) : 0;
    /* curva: % acumulada no fim de cada dia, sobre a base do dia 1 (dia 0 = 0%) */
    var atual = mk === D.mkHoje, ultimo = atual ? +A.hoje().slice(8, 10) : diasNoMes(mk), porDia = [], acc = 0, pts = [0];
    for (var d = 1; d <= ultimo; d++) porDia[d] = 0;
    doMes.forEach(function (t) { var d = +t.fechado_em.slice(8, 10); if (porDia[d] != null) porDia[d] += t.pnl_reais || 0; });
    for (d = 1; d <= ultimo; d++) { acc += porDia[d]; pts.push(base > 0 ? acc / base * 100 : 0); }
    return {
      mk: mk, atual: atual, ultimo: ultimo, n: doMes.length, nMed: med.length,
      pct: base > 0 ? pnl / base * 100 : null,
      wr: med.length ? g.length / med.length * 100 : null,
      payoff: g.length && p.length && pm > 0 ? gm / pm : null,
      curva: pts
    };
  }

  /* ---------------- desenho ---------------- */
  var logo = null;
  function carregaLogo() {
    if (logo) return logo;
    logo = new Promise(function (res) { var i = new Image(); i.onload = function () { res(i); }; i.onerror = function () { res(null); }; i.src = 'icons/marca-hd.png'; });
    return logo;
  }
  /* O stylesheet do Google Fonts entra por preload→onload: antes dele não existe @font-face, e
     fonts.load resolve vazio na hora — o card saía em fonte de sistema. Tenta até a Syne existir,
     com teto de 3 s (sem rede, sai na fonte de sistema mesmo). */
  var FONTES = ['800 200px Syne', '700 66px Syne', '500 29px "DM Sans"', '400 24px "DM Sans"', '500 26px "Fira Code"', '600 24px "Fira Code"'];
  function fontes() {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    var fim = Date.now() + 3000;
    return new Promise(function (res) {
      (function tenta() {
        Promise.all(FONTES.map(function (f) { return document.fonts.load(f).catch(function () {}); })).then(function () {
          var ok = FONTES.every(function (f) { try { return document.fonts.check(f); } catch (e) { return true; } });
          if (ok || Date.now() > fim) res(); else setTimeout(tenta, 150);
        });
      })();
    });
  }

  function txt(ctx, s, x, y, font, cor, al, esp) {
    ctx.font = font; ctx.fillStyle = cor; ctx.textAlign = al || 'left';
    if ('letterSpacing' in ctx) ctx.letterSpacing = (esp || 0) + 'px';
    ctx.fillText(s, x, y);
    if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
  }
  function cabe(ctx, s, peso, fam, max, tam) {   /* maior corpo (até tam) em que s cabe em max */
    for (; tam > 40; tam -= 4) { ctx.font = peso + ' ' + tam + 'px ' + fam; if (ctx.measureText(s).width <= max) break; }
    return tam;
  }
  function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function desenhar(R, formato, img) {
    var W = 1080, H = formato === 'story' ? 1920 : 1350, story = H > 1500;
    var cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    var ctx = cv.getContext('2d'), PAD = 84;
    var up = R.pct == null || R.pct >= 0, cor = up ? C.pos : C.neg, corRgb = up ? C.posRgb : C.negRgb;

    /* fundo: preto da marca + brilho da cor do resultado no alto, como o ponto da órbita da logo */
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
    var g = ctx.createRadialGradient(W * 0.86, H * 0.08, 0, W * 0.86, H * 0.08, W * 0.9);
    g.addColorStop(0, 'rgba(' + corRgb + ',.20)'); g.addColorStop(.45, 'rgba(' + corRgb + ',.05)'); g.addColorStop(1, 'rgba(' + corRgb + ',0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    var g2 = ctx.createRadialGradient(W * 0.1, H, 0, W * 0.1, H, W * 0.8);
    g2.addColorStop(0, 'rgba(232,228,217,.06)'); g2.addColorStop(1, 'rgba(232,228,217,0)');
    ctx.fillStyle = g2; ctx.fillRect(0, 0, W, H);

    /* Layout em duas pontas: o topo desce do cabeçalho, o rodapé sobe da borda, e a curva fica com o
       que sobra no meio. Stories deixa ~250 px livres em cima e embaixo (barras do Instagram). */
    var topo = story ? 240 : 72, fundo = H - (story ? 250 : 72);

    /* topo: logo + wordmark à esquerda, conta à direita */
    var y = topo, lh = 92, lw = img ? Math.round(lh * img.width / img.height) : 0;
    if (img) ctx.drawImage(img, PAD - 6, y, lw, lh);
    txt(ctx, 'Apollux', PAD + (lw ? lw + 8 : 0), y + lh / 2 + 19, '800 54px ' + FD, C.txt, 'left', -0.5);
    ctx.font = '600 24px ' + FM; if ('letterSpacing' in ctx) ctx.letterSpacing = '3px';
    var conta = String(A.NOME_CONTA || '').toUpperCase(), cw = ctx.measureText(conta).width + 44;
    if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
    rr(ctx, W - PAD - cw, y + lh / 2 - 26, cw, 52, 26); ctx.fillStyle = 'rgba(237,237,239,.05)'; ctx.fill();
    ctx.strokeStyle = 'rgba(237,237,239,.18)'; ctx.lineWidth = 2; ctx.stroke();
    txt(ctx, conta, W - PAD - cw / 2 + 1.5, y + lh / 2 + 9, '600 24px ' + FM, C.txt2, 'center', 3);

    /* resultado: o número grande. A vírgula da Syne desce ~0,2 do corpo: a linha de baixo respeita isso */
    y += lh + (story ? 130 : 90);
    txt(ctx, ('Rentabilidade · ' + rotuloMes(R.mk)).toUpperCase(), PAD, y, '500 27px ' + FM, C.txt2, 'left', 4);
    var hero = R.pct == null ? '—' : F.pct(R.pct, 2), th = cabe(ctx, hero, 800, FD, W - 2 * PAD, story ? 220 : 196);
    y += 24 + Math.round(th * 0.74);
    ctx.save(); ctx.shadowColor = 'rgba(' + corRgb + ',.45)'; ctx.shadowBlur = 48;
    txt(ctx, hero, PAD - 6, y, '800 ' + th + 'px ' + FD, cor, 'left', -4); ctx.restore();
    y += Math.round(th * 0.2) + 44;
    var sub = R.atual ? 'no mês, até ' + ('0' + R.ultimo).slice(-2) + '/' + R.mk.slice(5, 7) + ' · resultado fechado' : 'mês fechado · resultado das operações encerradas';
    txt(ctx, sub, PAD, y, '500 29px ' + FU, C.mute);
    var cTop = y + (story ? 64 : 48);

    /* rodapé, de baixo para cima: aviso → linha → três números → eixo da curva */
    var yL2 = fundo, yL1 = yL2 - 34, ySep = yL1 - 46, yStats = ySep - 34 - 150, yAx = yStats - 44, cBot = yAx - 34;
    ctx.fillStyle = 'rgba(237,237,239,.12)'; ctx.fillRect(PAD, ySep, W - 2 * PAD, 2);
    txt(ctx, 'Conta simulada (paper trading) com preço real da Binance.', PAD, yL1, '400 24px ' + FU, C.mute);
    txt(ctx, 'Resultado passado não garante resultado futuro.', PAD, yL2, '400 24px ' + FU, C.mute);
    /* data de emissão, e não "operado pelo Apollo": parte do resultado vem de fechamento manual */
    var hj = A.hoje();
    txt(ctx, 'emitido em ' + hj.slice(8, 10) + '/' + hj.slice(5, 7) + '/' + hj.slice(0, 4), W - PAD, yL2, '500 22px ' + FM, C.mute, 'right');

    /* três números: como opera, sem dinheiro */
    ctx.fillStyle = 'rgba(237,237,239,.12)'; ctx.fillRect(PAD, yStats, W - 2 * PAD, 2);
    var col = (W - 2 * PAD) / 3, stats = [
      ['Win rate', R.wr == null ? '—' : F.f0(R.wr) + '%'],
      ['Operações', F.f0(R.n)],
      ['Payoff', R.payoff == null ? '—' : F.f2(R.payoff) + '×']
    ];
    stats.forEach(function (s, k) {
      var x = PAD + col * k + (k ? 34 : 0);
      if (k) { ctx.fillStyle = 'rgba(237,237,239,.12)'; ctx.fillRect(PAD + col * k, yStats + 30, 2, 110); }
      txt(ctx, s[0].toUpperCase(), x, yStats + 62, '500 23px ' + FM, C.txt2, 'left', 3);
      txt(ctx, s[1], x, yStats + 136, '700 66px ' + FD, C.txt, 'left', -1);
    });

    /* curva do mês em pontos: a área entre o zero e a curva vira partículas da cor do resultado */
    var cy0 = cTop, ch = Math.max(160, cBot - cTop), cx0 = PAD, cw2 = W - 2 * PAD;
    var pts = R.curva, n = pts.length - 1, total = R.atual ? diasNoMes(R.mk) : n;
    var lo = Math.min(0, Math.min.apply(null, pts)), hi = Math.max(0, Math.max.apply(null, pts));
    if (hi - lo < 1e-9) { hi = 1; lo = -1; }
    var mg = (hi - lo) * 0.14; lo -= mg; hi += mg;
    var X = function (i) { return cx0 + i / Math.max(1, total) * cw2; }, Y = function (v) { return cy0 + (hi - v) / (hi - lo) * ch; };
    var yZ = Y(0), xEnd = X(n);
    var emY = function (x) { var f = (x - cx0) / cw2 * total; if (f >= n) return Y(pts[n]); var i = Math.floor(f), t = f - i; return Y(pts[i] + (pts[i + 1] - pts[i]) * t); };
    var passo = 18;
    for (var gx = cx0; gx <= cx0 + cw2 + 0.5; gx += passo) {
      var yc = gx <= xEnd ? emY(gx) : null;
      for (var gy = cy0; gy <= cy0 + ch + 0.5; gy += passo) {
        var dentro = yc != null && ((gy >= yc && gy <= yZ) || (gy <= yc && gy >= yZ));
        if (dentro) {
          var prox = 1 - Math.min(1, Math.abs(gy - yc) / Math.max(40, Math.abs(yZ - yc)));
          ctx.fillStyle = 'rgba(' + corRgb + ',' + (0.16 + 0.6 * prox).toFixed(3) + ')';
          ctx.beginPath(); ctx.arc(gx, gy, 2.6 + 1.4 * prox, 0, 6.2832); ctx.fill();
        } else {
          ctx.fillStyle = 'rgba(237,237,239,.07)'; ctx.beginPath(); ctx.arc(gx, gy, 2, 0, 6.2832); ctx.fill();
        }
      }
    }
    ctx.setLineDash([6, 10]); ctx.strokeStyle = 'rgba(237,237,239,.22)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(cx0, yZ); ctx.lineTo(cx0 + cw2, yZ); ctx.stroke(); ctx.setLineDash([]);
    txt(ctx, '0%', cx0 + cw2, yZ - 12, '500 22px ' + FM, C.mute, 'right');
    ctx.save(); ctx.shadowColor = 'rgba(' + corRgb + ',.7)'; ctx.shadowBlur = 22;
    ctx.strokeStyle = cor; ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.beginPath(); for (var i = 0; i <= n; i++) { if (i) ctx.lineTo(X(i), Y(pts[i])); else ctx.moveTo(X(i), Y(pts[i])); } ctx.stroke();
    /* o ponto de agora, como o ponto na órbita da logo */
    ctx.shadowBlur = 36; ctx.fillStyle = cor; ctx.beginPath(); ctx.arc(xEnd, Y(pts[n]), 13, 0, 6.2832); ctx.fill();
    ctx.shadowBlur = 0; ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(xEnd, Y(pts[n]), 6, 0, 6.2832); ctx.fill(); ctx.restore();
    var mm = R.mk.slice(5, 7);
    txt(ctx, '01/' + mm, cx0, yAx, '500 22px ' + FM, C.mute, 'left');
    txt(ctx, ('0' + diasNoMes(R.mk)).slice(-2) + '/' + mm, cx0 + cw2, yAx, '500 22px ' + FM, C.mute, 'right');
    return cv;
  }

  /* ---------------- modal ---------------- */
  var CSS = '.shr-ov{position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,.72);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);display:grid;place-items:center;padding:16px}' +
    '.shr-box{width:min(440px,100%);max-height:calc(100dvh - 32px);overflow:auto;background:var(--panel);border:1px solid var(--line2);border-radius:18px;padding:16px;display:grid;gap:12px;color:var(--txt);font-family:var(--f-ui)}' +
    '.shr-hd{display:flex;align-items:center;gap:10px}.shr-hd h3{font-family:var(--f-display);font-weight:800;font-size:19px;margin:0;flex:1}' +
    '.shr-x{width:40px;height:40px;border-radius:12px;border:1px solid var(--line2);background:var(--panel2);color:var(--txt);display:grid;place-items:center;cursor:pointer}' +
    '.shr-prev{display:grid;place-items:center;background:#000;border-radius:12px;border:1px solid var(--line);min-height:200px;overflow:hidden}' +
    '.shr-prev img{display:block;width:auto;max-width:100%;max-height:min(52vh,560px)}' +
    '.shr-prev .shr-msg{font-family:var(--f-mono);font-size:12px;color:var(--mute);padding:24px;text-align:center}' +
    '.shr-lbl{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin-bottom:6px}' +
    '.shr-ops{display:flex;gap:6px;flex-wrap:wrap}' +
    '.shr-op{font-family:var(--f-mono);font-size:12px;padding:7px 11px;border-radius:9px;border:1px solid var(--line2);background:transparent;color:var(--txt2);cursor:pointer;min-height:36px}' +
    '.shr-op[aria-pressed="true"]{background:var(--accent);color:var(--accent-ink);border-color:transparent;font-weight:600}' +
    '.shr-act{display:grid;grid-template-columns:1fr 1fr;gap:8px}' +
    '.shr-b{font-family:var(--f-ui);font-weight:600;font-size:14px;min-height:46px;padding:10px 14px;border-radius:12px;border:1px solid var(--line2);background:rgba(var(--txt-rgb),.06);color:var(--txt);display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer}' +
    '.shr-b.pri{background:var(--accent);color:var(--accent-ink);border-color:transparent}.shr-b:disabled{opacity:.45;cursor:default}.shr-b .ic{width:18px;height:18px}' +
    '.shr-nota{font-size:12px;line-height:1.45;color:var(--mute);margin:0}' +
    '.shr-btn{cursor:pointer}.shr-btn .ic{width:19px;height:19px}' +
    '@media (max-width:560px){.shr-ov{place-items:end center;padding:0}.shr-box{width:100%;border-radius:18px 18px 0 0;border-bottom:0;padding-bottom:calc(16px + env(safe-area-inset-bottom,0px));max-height:94dvh}}';
  var ov = null, foco = null, D = null, banca = 0, S = { mk: null, formato: 'feed', arquivo: null, gen: 0 };
  var celular = !!(window.matchMedia && matchMedia('(pointer:coarse)').matches);

  function nomeArquivo() { return 'apollux-' + rotuloMes(S.mk).replace(' ', '-').replace('ç', 'c') + (S.formato === 'story' ? '-stories' : '') + '.png'; }
  function podeShare(f) { try { return !!(f && navigator.canShare && navigator.canShare({ files: [f] })); } catch (e) { return false; } }

  function fechar() {
    if (!ov) return; ov.remove(); ov = null; document.removeEventListener('keydown', tecla);
    if (foco && foco.focus) try { foco.focus(); } catch (e) {}
  }
  function tecla(e) {
    if (e.key === 'Escape') { e.preventDefault(); fechar(); return; }
    if (e.key === 'Tab' && ov) {   /* foco preso no diálogo */
      var f = ov.querySelectorAll('button:not([disabled])'); if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  }
  function q(s) { return ov && ov.querySelector(s); }

  function pintaOpcoes() {
    q('#shr-meses').innerHTML = D.meses.map(function (m) { return '<button type="button" class="shr-op" data-mk="' + m + '" aria-pressed="' + (m === S.mk) + '">' + curtoMes(m) + '</button>'; }).join('');
    q('#shr-fmt').innerHTML = [['feed', 'Feed 4:5'], ['story', 'Stories 9:16']].map(function (o) { return '<button type="button" class="shr-op" data-fmt="' + o[0] + '" aria-pressed="' + (o[0] === S.formato) + '">' + o[1] + '</button>'; }).join('');
  }

  async function gerar() {
    var meu = ++S.gen; S.arquivo = null;
    q('#shr-sv').disabled = true; q('#shr-dl').disabled = true;
    var R = calcular(D, S.mk, banca);
    var res = await Promise.all([carregaLogo(), fontes()]);
    if (meu !== S.gen || !ov) return;
    var cv = desenhar(R, S.formato, res[0]);
    var url = cv.toDataURL('image/png');
    q('#shr-prev').innerHTML = '<img alt="Prévia: ' + esc(rotuloMes(S.mk)) + ', ' + esc(R.pct == null ? 'sem base' : F.pct(R.pct, 2)) + ', win rate ' + esc(R.wr == null ? '—' : F.f0(R.wr) + '%') + ', ' + R.n + ' operações" src="' + url + '">';
    q('#shr-info').textContent = R.n ? '' : 'Nenhuma operação fechada neste mês ainda.';
    cv.toBlob(function (b) {
      if (meu !== S.gen || !ov || !b) return;
      try { S.arquivo = new File([b], nomeArquivo(), { type: 'image/png' }); } catch (e) { S.arquivo = b; S.arquivo.name = nomeArquivo(); }
      q('#shr-dl').disabled = false;
      q('#shr-sv').disabled = !podeShare(S.arquivo);
      q('#shr-sv').hidden = !podeShare(S.arquivo);
      q('.shr-act').style.gridTemplateColumns = podeShare(S.arquivo) ? '1fr 1fr' : '1fr';
    }, 'image/png');
  }

  function baixar() {
    var f = S.arquivo; if (!f) return;
    var u = URL.createObjectURL(f), a = document.createElement('a');
    a.href = u; a.download = nomeArquivo(); a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(u); }, 4000);
    A.toast('PNG baixado: ' + nomeArquivo());
  }
  function enviar() {
    var f = S.arquivo; if (!podeShare(f)) { baixar(); return; }
    /* só o arquivo, sem texto: com texto junto, o iPhone tira o "Salvar imagem" da folha */
    navigator.share({ files: [f] }).catch(function (e) { if (e && e.name !== 'AbortError') baixar(); });
  }

  async function abrir(ev) {
    if (ov) return;
    var e = A.estado;
    if (!e) { A.toast('Aguarde o primeiro retrato do backend.'); return; }
    foco = (ev && ev.currentTarget) || document.activeElement;
    if (!document.getElementById('shr-css')) { var st = document.createElement('style'); st.id = 'shr-css'; st.textContent = CSS; document.head.appendChild(st); }
    ov = document.createElement('div'); ov.className = 'shr-ov';
    ov.innerHTML = '<div class="shr-box" role="dialog" aria-modal="true" aria-labelledby="shr-t">' +
      '<div class="shr-hd"><h3 id="shr-t">Resultado do mês</h3><button type="button" class="shr-x" data-shr="x" aria-label="Fechar"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true" style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>' +
      '<div class="shr-prev" id="shr-prev"><div class="shr-msg">lendo as operações…</div></div>' +
      '<div><div class="shr-lbl">Mês</div><div class="shr-ops" id="shr-meses"></div></div>' +
      '<div><div class="shr-lbl">Formato</div><div class="shr-ops" id="shr-fmt"></div></div>' +
      '<div class="shr-act"><button type="button" class="shr-b' + (celular ? ' pri' : '') + '" id="shr-sv" disabled>' + ICONE + (celular ? 'Salvar na galeria' : 'Compartilhar') + '</button>' +
      '<button type="button" class="shr-b' + (celular ? '' : ' pri') + '" id="shr-dl" disabled><svg class="ic" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" style="stroke:currentColor;fill:none;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round"><path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>Baixar PNG</button></div>' +
      '<p class="shr-nota" id="shr-info"></p>' +
      '<p class="shr-nota">Só percentuais: nenhum valor em R$ sai no card. ' + (celular ? 'Em "Salvar na galeria", toque em <b>Salvar imagem</b> na folha do sistema.' : '') + '</p></div>';
    document.body.appendChild(ov);
    document.addEventListener('keydown', tecla);
    ov.addEventListener('click', function (ev2) {
      if (ev2.target === ov || ev2.target.closest('[data-shr="x"]')) { fechar(); return; }
      var m = ev2.target.closest('[data-mk]'); if (m && m.dataset.mk !== S.mk) { S.mk = m.dataset.mk; pintaOpcoes(); gerar(); return; }
      var f = ev2.target.closest('[data-fmt]'); if (f && f.dataset.fmt !== S.formato) { S.formato = f.dataset.fmt; pintaOpcoes(); gerar(); return; }
      if (ev2.target.closest('#shr-sv')) enviar();
      else if (ev2.target.closest('#shr-dl')) baixar();
    });
    q('[data-shr="x"]').focus();
    try {
      var lista = await A.api('/trades?limite=' + LIM);
      if (!ov) return;
      D = preparar(lista); banca = ((A.estado || e).banca || {}).atual || 0;
      /* abre no mês corrente; se ele ainda não tem operação (dia 1), no último que tem */
      var temHoje = D.tr.some(function (t) { return mesDe(t.fechado_em) === D.mkHoje; });
      S.mk = temHoje || D.meses.length < 2 ? D.mkHoje : D.meses[1];
      pintaOpcoes(); gerar();
    } catch (err) {
      if (ov) q('#shr-prev').innerHTML = '<div class="shr-msg">não deu para ler as operações: ' + esc(A.erroTxt ? A.erroTxt(err) : String(err)) + '</div>';
    }
  }

  document.addEventListener('click', function (ev) { var b = ev.target.closest && ev.target.closest('[data-share]'); if (b) { ev.preventDefault(); abrir({ currentTarget: b }); } });

  window.APXShare = {
    abrir: abrir,
    /* o botão do cabeçalho; cls = classe de botão-ícone de cada casca (.ib no celular, .btn no desktop) */
    botao: function (cls) { return '<button type="button" class="' + (cls || '') + ' shr-btn" data-share aria-label="Compartilhar resultado do mês" title="Compartilhar resultado do mês">' + ICONE + '</button>'; },
    _calcular: calcular, _preparar: preparar, _desenhar: desenhar
  };
})();
