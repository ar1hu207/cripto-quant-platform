/* Apollux · cliente do backend (APX). Tudo que fala com a API passa por aqui: credencial, conta,
   poll do /estado, gate de login, estados de falha e os eventos que fazem a esfera do Apollo pulsar.

   Contratos herdados do painel clássico (web/classico.html), mantidos IGUAIS de propósito para quem já
   tem o app instalado não ser deslogado nem trocar de banca sem perceber:
   - credencial em localStorage 'cbAuth' ("Basic ..."), header Authorization em toda requisição;
   - conta em localStorage 'cbConta' ('A' | 'B'); a B é outra instância exposta em /testeB/... [AB-1],
     então trocar de conta é trocar o prefixo de TODAS as rotas;
   - 401 nunca insiste com a mesma credencial (15 senhas erradas bloqueiam o IP): para o poll, descarta,
     abre o gate uma vez só (single-flight) e religa quando a credencial nova passa;
   - 429 para o poll, senão ele renova o próprio bloqueio.
   Poll: /estado a cada 3 s, como o clássico. Pausa com a aba escondida (apertar pode; acelerar não). */
(function () {
  'use strict';
  var root = document.documentElement;
  var STATIC = /[?&#]static=1(&|$)/.test(location.search + location.hash);
  if (STATIC) root.classList.add('is-static');
  var RM = STATIC || !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

  /* ---- storage: leitura e escrita sempre em try/catch (aba privada, site data bloqueado) ---- */
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) {} }
  };

  var CONTA = store.get('cbConta') === 'B' ? 'B' : 'A';
  var BASE = String(window.API_BASE || '').replace(/\/+$/, '');
  var API = BASE + (CONTA === 'B' ? '/testeB' : '');
  var cred = store.get('cbAuth') || '';

  /* ---- formatação (pt-BR; números em mono tabular na tela) ---- */
  var f2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var f0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  var MENOS = '−';
  function n(v) { return typeof v === 'number' && isFinite(v) ? v : 0; }
  var fmt = {
    f2: function (v) { return f2.format(n(v)); },
    f0: function (v) { return f0.format(n(v)); },
    brl: function (v) { v = n(v); return (v < 0 ? MENOS : '') + 'R$ ' + f2.format(Math.abs(v)); },
    /* dinheiro com sinal explícito: P&L */
    money: function (v) { v = n(v); return (v > 0 ? '+' : v < 0 ? MENOS : '') + 'R$ ' + f2.format(Math.abs(v)); },
    pct: function (v, d) { v = n(v); var f = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d }); return (v > 0 ? '+' : v < 0 ? MENOS : '') + f.format(Math.abs(v)) + '%'; },
    /* preço: casas conforme a grandeza (0,1621 · 15,31 · 69.110) */
    px: function (v) {
      v = n(v); var a = Math.abs(v), d = a >= 1000 ? 1 : a >= 100 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 4 : 6;
      if (a >= 10000) d = 0;
      return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
    },
    par: function (a) { return String(a || '').replace('/USDT', 'USDT').replace(':USDT', ''); },
    base: function (a) { return String(a || '').split('/')[0]; },
    cls: function (v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }
  };

  /* Timestamps do backend são naive em hora de São Paulo (CLAUDE.md §1). Nunca toISOString(): o dia
     muda de lado depois das 21h. Agrupamento por dia usa o PREFIXO da string. */
  function ts(s) { if (!s) return null; var d = new Date(String(s).slice(0, 19).replace(' ', 'T')); return isNaN(d) ? null : d; }
  function dia(s) { return String(s || '').slice(0, 10); }
  function ddmm(s) { s = String(s || ''); return s.slice(8, 10) + '/' + s.slice(5, 7); }
  function hhmm(s) { return String(s || '').slice(11, 16); }
  function idade(s) {
    var d = ts(s); if (!d) return '—';
    var m = Math.max(0, Math.round((Date.now() - d) / 60000));
    if (m < 1) return 'agora'; if (m < 60) return m + ' min';
    var h = Math.floor(m / 60); if (h < 24) return h + 'h ' + ('0' + (m % 60)).slice(-2) + 'm';
    return Math.floor(h / 24) + 'd ' + (h % 24) + 'h';
  }
  function hoje() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ---- barramento de eventos (views assinam no init e saem no destroy) ---- */
  var subs = {};
  function on(ev, fn) { (subs[ev] = subs[ev] || []).push(fn); return function () { off(ev, fn); }; }
  function off(ev, fn) { var a = subs[ev]; if (!a) return; var i = a.indexOf(fn); if (i >= 0) a.splice(i, 1); }
  function emit(ev, d) { (subs[ev] || []).slice().forEach(function (fn) { try { fn(d); } catch (e) { console.error('APX ' + ev, e); } }); }

  /* ---- toast ---- */
  var tt = 0;
  function toast(msg, tipo) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = msg; t.className = 'toast is-on' + (tipo ? ' ' + tipo : '');
    clearTimeout(tt); tt = setTimeout(function () { t.className = 'toast'; }, 3200);
  }

  /* ---- gate de login (markup em index.html) ---- */
  var $ = function (id) { return document.getElementById(id); };
  var gateSessao = null, gateTimer = 0, gateHealth = 0;
  function gateMsg(html, tipo) { var m = $('gate-msg'); m.innerHTML = html; m.className = 'gate-msg on ' + (tipo || 'err'); }
  function gateLimpa() { $('gate-msg').className = 'gate-msg'; }
  function gateOcupado(on, rotulo) {
    $('gate-btn').disabled = on; $('gate-btn').textContent = rotulo || 'Entrar';
    $('gate-user').disabled = on; $('gate-pass').disabled = on;
  }
  async function saude() {
    try {
      var r = await fetch(API + '/health', { cache: 'no-store' });
      var j = await r.json();
      return { ok: true, vivo: r.ok, j: j };
    } catch (e) { return { ok: false }; }
  }
  /* /health não passa pela autenticação: prova de vida do backend com o painel trancado. Versão E
     commit, os dois (o commit diz qual código está RODANDO; deploy é ato deliberado, CLAUDE.md §5). */
  async function gateSaude() {
    var s = $('gate-status'), t = $('gate-status-txt'), h = await saude();
    if (h.ok) {
      var sha = h.j.commit ? ' · ' + String(h.j.commit).slice(0, 7) : ' · sem git';
      s.className = 'gate-status ' + (h.vivo ? 'up' : 'warn');
      t.textContent = (h.vivo ? 'backend online' : 'backend no ar, ciclo parado') + ' · v' + h.j.versao + sha;
    } else { s.className = 'gate-status down'; t.textContent = 'backend sem resposta'; }
  }
  function gateEspera(seg) {
    clearInterval(gateTimer);
    var tick = function () {
      if (seg <= 0) { clearInterval(gateTimer); gateOcupado(false); gateLimpa(); $('gate-pass').focus(); return; }
      gateMsg('Tentativas demais. O backend libera de novo em <b>' + seg + ' s</b>.', 'warn'); seg--;
    };
    gateOcupado(true, 'Aguarde'); tick(); gateTimer = setInterval(tick, 1000);
  }
  async function gateEntrar(ev) {
    ev.preventDefault();
    var u = $('gate-user').value.trim(), p = $('gate-pass').value;
    if (!p) { gateMsg('Digite a senha.', 'info'); $('gate-pass').focus(); return; }
    var cand = 'Basic ' + btoa(unescape(encodeURIComponent(u + ':' + p)));
    gateLimpa(); gateOcupado(true, 'Verificando…');
    var r;
    /* /status é a rota autenticada mais barata: valida a senha sem arrastar a curva de equity */
    try { r = await fetch(API + '/status', { headers: { Authorization: cand } }); }
    catch (e) {
      gateOcupado(false); gateSaude();
      gateMsg('Sem resposta do backend. Ou o serviço está fora do ar, ou a origem deste painel não está liberada no <b>CORS_ORIGINS</b> do servidor.', 'err');
      return;
    }
    if (r.ok) { cred = cand; store.set('cbAuth', cand); gateOcupado(true, 'Entrando…'); gateFecha(true); return; }
    gateOcupado(false);
    if (r.status === 401) {
      var f = $('gate-form'); f.classList.remove('shake'); void f.offsetWidth; f.classList.add('shake');
      gateMsg('Usuário ou senha incorretos.', 'err'); var c = $('gate-pass'); c.focus(); c.select();
    } else if (r.status === 429) {
      var txt = await r.text().catch(function () { return ''; }), m = txt.match(/(\d+)\s*s/); gateEspera(m ? +m[1] : 120);
    } else if (r.status === 503) {
      gateMsg('O backend está no ar, mas sem <b>DASH_PASS</b> definido, e sem senha ele recusa acesso externo. Defina a senha no <b>.env</b> do servidor e reinicie.', 'warn');
    } else gateMsg('Resposta inesperada do backend (HTTP ' + r.status + ').', 'err');
  }
  function gateAbre() {
    if (gateSessao) return gateSessao.p;
    var res; var p = new Promise(function (r) { res = r; });
    gateSessao = { p: p, res: res };
    root.classList.add('gate-on'); $('gate').hidden = false;
    $('gate-foot').textContent = 'autenticando em ' + (API || location.origin) + (CONTA === 'B' ? ' · conta B' : '');
    gateLimpa(); gateOcupado(false); $('gate-pass').value = '';
    ($('gate-user').value.trim() ? $('gate-pass') : $('gate-user')).focus();
    gateSaude(); clearInterval(gateHealth); gateHealth = setInterval(gateSaude, 15000);
    emit('gate', true);
    return p;
  }
  function gateFecha(ok) {
    clearInterval(gateHealth); clearInterval(gateTimer);
    root.classList.remove('gate-on'); $('gate').hidden = true; $('gate-pass').value = '';
    emit('gate', false);
    if (gateSessao) { var r = gateSessao.res; gateSessao = null; r(!!ok); }
    if (ok) { carregar(); iniciar(); }
  }

  /* ---- fetch autenticado ---- */
  async function apiFetch(path, opts) {
    opts = opts || {};
    var mk = function () { var h = Object.assign({}, opts.headers || {}); if (cred) h.Authorization = cred; return Object.assign({}, opts, { headers: h }); };
    var r = await fetch(API + path, mk());
    if (r.status === 429) { parar(); toast(await r.clone().text(), 'warn'); return r; }
    if (r.status === 401) {
      parar(); store.del('cbAuth'); cred = '';
      if (await gateAbre()) r = await fetch(API + path, mk());
    }
    return r;
  }
  /* GET (sem body) ou POST JSON. Erro HTTP vira exceção com o texto do backend. */
  async function api(path, body) {
    var o = body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {};
    var r = await apiFetch(path, o);
    if (!r.ok) { var t = await r.text().catch(function () { return ''; }); var e = new Error(t || ('HTTP ' + r.status)); e.status = r.status; throw e; }
    return r.json();
  }
  /* Mensagem legível de um erro de rota (o FastAPI devolve {"detail": ...}). */
  function erroTxt(e) {
    var m = (e && e.message) || String(e);
    try { var j = JSON.parse(m); var d = j.detail != null ? j.detail : j; if (typeof d === 'string') return d; if (d.recusados) return d.erro + ': ' + d.recusados.join('; '); return JSON.stringify(d); } catch (x) { return m; }
  }

  /* ---- poll do /estado ---- */
  var estado = null, timer = 0, online = null, emCurso = false;
  function setOnline(v, msg) {
    if (online === v) return; online = v;
    root.classList.toggle('is-offline', !v);
    emit(v ? 'online' : 'offline', msg);
  }
  /* Eventos reais para o Apollo: posição aberta/fechada, sinal novo, trava disparada, ordem nova.
     Só a partir do SEGUNDO estado: a primeira carga não é evento, é o retrato inicial. */
  function eventos(a, b) {
    if (!a) return;
    var ids = function (l) { var s = {}; (l || []).forEach(function (x) { s[x.id] = x; }); return s; };
    var pa = ids(a.posicoes), pb = ids(b.posicoes), sa = ids(a.pendentes), oa = ids(a.ordens);
    (b.posicoes || []).forEach(function (p) { if (!pa[p.id]) emit('evento', { tipo: 'posicao_aberta', p: p }); });
    (a.posicoes || []).forEach(function (p) { if (!pb[p.id]) emit('evento', { tipo: 'posicao_fechada', p: p }); });
    (b.pendentes || []).forEach(function (s) { if (!sa[s.id]) emit('evento', { tipo: 'sinal_novo', s: s }); });
    (b.ordens || []).forEach(function (o) { if (!oa[o.id]) emit('evento', { tipo: 'ordem_nova', o: o }); });
    var ta = a.risco && a.risco.trava_dia, tb = b.risco && b.risco.trava_dia;
    if (!ta && tb) emit('evento', { tipo: 'trava', r: b.risco });
  }
  async function carregar() {
    if (emCurso) return estado; emCurso = true;
    try {
      var r = await apiFetch('/estado');
      if (!r.ok) {
        if (r.status !== 401 && r.status !== 429) setOnline(false, 'HTTP ' + r.status);
        return estado;
      }
      var e = await r.json(), ant = estado;
      e._em = Date.now(); estado = e; setOnline(true);
      eventos(ant, e);
      emit('estado', e);
      return e;
    } catch (err) {
      setOnline(false, 'sem resposta');
      return estado;
    } finally { emCurso = false; }
  }
  function iniciar() { if (timer || document.hidden) return; timer = setInterval(carregar, 3000); }
  function parar() { clearInterval(timer); timer = 0; }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) parar(); else if (!gateSessao) { carregar(); iniciar(); }
  });

  async function sair() {
    store.del('cbAuth'); cred = ''; parar();
    /* backend sem senha (monolito local) não tem sessão para encerrar */
    try { if ((await fetch(API + '/status')).ok) { carregar(); iniciar(); toast('Este backend não pede senha: não há sessão para encerrar'); return; } } catch (e) {}
    gateAbre();
  }
  function trocaConta(c) { if (c === CONTA || (c !== 'A' && c !== 'B')) return; store.set('cbConta', c); location.reload(); }

  /* ---- libs vendoradas sob demanda (sempre de web/vendor, nunca de CDN) ---- */
  var libs = {};
  function lib(arquivo, global) {
    if (window[global]) return Promise.resolve(true);
    if (libs[arquivo]) return libs[arquivo];
    return (libs[arquivo] = new Promise(function (res) {
      var s = document.createElement('script'); s.src = 'vendor/' + arquivo;
      s.onload = function () { res(!!window[global]); };
      s.onerror = function () { libs[arquivo] = null; res(false); };
      document.head.appendChild(s);
    }));
  }

  /* Cores das paletas para quem só aceita string (canvas, lightweight-charts): lidas do :root na hora. */
  function cor(nome) { return getComputedStyle(root).getPropertyValue('--' + nome).trim(); }
  function rgba(nome, a) { return 'rgba(' + cor(nome + '-rgb') + ',' + a + ')'; }

  window.APX = {
    STATIC: STATIC, RM: RM, CONTA: CONTA, API: API, store: store, fmt: fmt, esc: esc,
    ts: ts, dia: dia, ddmm: ddmm, hhmm: hhmm, idade: idade, hoje: hoje,
    on: on, off: off, emit: emit, toast: toast,
    api: api, apiFetch: apiFetch, erroTxt: erroTxt, saude: saude,
    carregar: carregar, iniciar: iniciar, parar: parar, sair: sair, trocaConta: trocaConta,
    get estado() { return estado; }, get online() { return online; },
    lib: lib, cor: cor, rgba: rgba,
    _gateEntrar: gateEntrar, _gateAbre: gateAbre
  };
})();
