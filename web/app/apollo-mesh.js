/* ApolloMesh — a presença do Apollo: uma ESFERA DE PARTÍCULAS (pontos, sem linhas), silhueta densa, que se
   deforma quando ele fala. Arquivo compartilhado (casca: widget mini; aba #apollo: full).
   API (CONTRATO.md, seção "Apollo: presença global + aba"), inalterada:
     window.ApolloMesh.create(canvas, { mode: "mini" | "full", density: 22 }) → handle
     handle.setLevel(v) · speak(ms) · pulse() · setListening(bool) · setMode(m) · resize() · pause() · resume() · destroy()
   Tokens (--txt-rgb, --accent-rgb, --bg-rgb, --glow*) lidos a cada frame; DPR; pausa em document.hidden;
   em is-static / prefers-reduced-motion desenha UM frame e speak/pulse não animam.
   Produção (web/app, 12/11): copiado do mockup com duas mudanças, as duas regras de movimento do front:
   - fora da tela o laço PARA (IntersectionObserver), não só com a aba escondida: a esfera full mora
     no topo da #apollo e rolar até o journal deixava 3.200 pontos sendo desenhados para ninguém;
   - em tela estreita (≤ 640 px) a esfera nasce com menos da metade dos pontos: celular paga em bateria. */
(function () {
  'use strict';

  function tokens() {
    var cs = getComputedStyle(document.documentElement);
    var g = function (n, d) { var v = (cs.getPropertyValue(n) || '').trim(); return v || d; };
    return {
      accent: g('--accent-rgb', '77,163,255').split(',').map(Number),
      txt: g('--txt-rgb', '234,242,255').split(',').map(Number),
      bg: g('--bg-rgb', '3,6,12'),
      glow: parseFloat(g('--glow', '0.45')) || 0.45,
      glowLo: parseFloat(g('--glow-lo', '0.25')) || 0.25
    };
  }
  function isStatic() {
    return document.documentElement.classList.contains('is-static') ||
      (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function mix(a, b, t) { return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)]; }

  /* esfera de Fibonacci: pontos uniformes na superfície */
  function fib(n) {
    var pts = new Float32Array(n * 4), GA = Math.PI * (3 - Math.sqrt(5));
    for (var i = 0; i < n; i++) {
      var seed = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1; /* semente determinística por ponto */
      var seed2 = Math.abs(Math.sin(i * 78.233) * 43758.5453) % 1;
      /* jitter leve quebra a treliça da espiral: lê como partículas, não como malha */
      var y = clamp(1 - 2 * (i + 0.5) / n + (seed2 - 0.5) * (2.2 / n) * 3, -1, 1);
      var r = Math.sqrt(1 - y * y), phi = i * GA + (seed - 0.5) * 0.9;
      pts[i * 4] = r * Math.cos(phi); pts[i * 4 + 1] = y; pts[i * 4 + 2] = r * Math.sin(phi);
      pts[i * 4 + 3] = seed;
    }
    return pts;
  }

  function create(canvas, opts) {
    opts = opts || {};
    var ctx = canvas.getContext('2d');
    var st = {
      mode: opts.mode === 'mini' ? 'mini' : 'full',
      level: 0, listening: false, rings: [], shells: [], speakUntil: 0, speakSeed: 0,
      paused: false, hidden: false, offscreen: false, destroyed: false, raf: 0, last: 0, t: 0, lastRing: 0,
      mx: 0, my: 0, tx: 0, ty: 0, w: 1, h: 1, dpr: 1, pts: null, n: 0, ringPts: null
    };
    function build() {
      var small = !!(window.matchMedia && window.matchMedia('(max-width: 640px)').matches);
      st.n = st.mode === 'mini' ? (small ? 360 : 700) : (small ? 1400 : 3200);
      st.pts = fib(st.n);
      var m = st.mode === 'mini' ? 60 : 140, rp = new Float32Array(m * 2);
      for (var i = 0; i < m; i++) { rp[i * 2] = i / m * Math.PI * 2; rp[i * 2 + 1] = Math.sin(i * 7.31) * 0.5; }
      st.ringPts = rp;
    }
    build();

    /* ---- deformação radial (fração do raio) ---- */
    function deform(x, y, z, seed, t, fz) {
      /* fz = profundidade rotacionada (1 = frente, -1 = fundo), para os anéis que nascem na frente */
      var d = 0.012 * Math.sin(seed * 6.28 + t * 0.8); /* ruído de repouso, muito leve */
      var L = st.level;
      if (L > 0.002) {
        d += L * 0.2 * (Math.sin(3.1 * x + 2.1 * t) * Math.sin(2.4 * y - 1.7 * t) + 0.6 * Math.sin(5.3 * z + 3.1 * t + seed * 6.28) + 0.4 * Math.sin(7.7 * (x + y) - 4.3 * t));
      }
      var theta = Math.acos(clamp(fz, -1, 1)); /* ângulo a partir do ponto frontal */
      for (var k = 0; k < st.rings.length; k++) {
        var r = st.rings[k], age = t - r.t0, pos = age * 2.6; /* rad/s: percorre a esfera em ~1,2 s */
        var dd = (theta - pos) / 0.28;
        d += r.amp * 0.16 * Math.exp(-dd * dd) * Math.exp(-age * 1.6);
      }
      return d;
    }

    function draw(t) {
      var w = st.w, h = st.h, full = st.mode === 'full';
      ctx.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      var tk = tokens();
      var R = (full ? Math.min(w, h) * 0.39 : h * 0.4) * (1 + 0.02 * Math.sin(t * 0.5));
      var cx = w / 2, cy = h * 0.5;
      var ay = t * 0.22 + st.mx * 0.09, ax = Math.sin(t * 0.13) * 0.14 + st.my * 0.07;
      var cay = Math.cos(ay), say = Math.sin(ay), cax = Math.cos(ax), sax = Math.sin(ax);
      var camD = 3.2;
      var pts = st.pts, n = st.n, L = st.level;
      var baseA = st.listening ? 0.86 : 0.74;
      var bright = []; /* candidatos ao passe de brilho */
      var pass, i;
      for (pass = 0; pass < 2; pass++) {
        for (i = 0; i < n; i++) {
          var x = pts[i * 4], y = pts[i * 4 + 1], z = pts[i * 4 + 2], seed = pts[i * 4 + 3];
          /* rotação Y depois X */
          var x1 = x * cay + z * say, z1 = -x * say + z * cay;
          var y1 = y * cax - z1 * sax, z2 = y * sax + z1 * cax;
          var front = (z2 + 1) / 2; /* 1 = de frente para a câmera */
          if (pass === 0 ? z2 > 0 : z2 <= 0) continue; /* fundo primeiro, frente depois */
          var d = deform(x, y, z, seed, t, z2);
          var rr = R * (1 + d);
          var X = x1 * rr, Y = y1 * rr, Z = z2 * rr;
          var s = camD * R / (camD * R - Z);
          var px = cx + X * s, py = cy - Y * s;
          var rim = 1 - Math.abs(z2);                     /* 1 na silhueta */
          var crest = clamp(d * 5, 0, 1);
          var a = baseA * (0.12 + 0.88 * front * front) * (1 + 0.9 * rim * rim) + crest * 0.5;
          a = clamp(a, 0.04, 1);
          var size = (full ? 1.15 : 0.85) * (0.45 + 0.95 * front) * (1 + 0.6 * crest) * (1 + L * 0.35 * front) * s;
          var tint = clamp(crest * 1.4 + (front - 0.86) * 4, 0, 1) * 0.65;
          var c = tint > 0.02 ? mix(tk.txt, tk.accent, tint) : tk.txt;
          ctx.fillStyle = 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a.toFixed(3) + ')';
          if (size < 1.3) ctx.fillRect(px - size * 0.5, py - size * 0.5, size, size);
          else { ctx.beginPath(); ctx.arc(px, py, size * 0.55, 0, 6.2832); ctx.fill(); }
          if (a > 0.78 && front > 0.8 && bright.length < (full ? 140 : 40)) bright.push(px, py, size, tint);
        }
      }
      /* passe de brilho: só nos pontos mais brilhantes */
      for (i = 0; i < bright.length; i += 4) {
        var tc = mix(tk.txt, tk.accent, 0.5 + bright[i + 3] * 0.5);
        ctx.fillStyle = 'rgba(' + tc[0] + ',' + tc[1] + ',' + tc[2] + ',' + (tk.glowLo * 0.55).toFixed(3) + ')';
        ctx.beginPath(); ctx.arc(bright[i], bright[i + 1], bright[i + 2] * 2.6, 0, 6.2832); ctx.fill();
      }
      /* cascas do pulse: uma concha de pontos que se expande e some */
      for (var sh = 0; sh < st.shells.length; sh++) {
        var S = st.shells[sh], age2 = t - S.t0, k2 = 1 + age2 * 1.1, al = (1 - age2 / 1.1) * 0.75;
        if (al <= 0) continue;
        ctx.fillStyle = 'rgba(' + tk.accent[0] + ',' + tk.accent[1] + ',' + tk.accent[2] + ',' + al.toFixed(3) + ')';
        for (i = 0; i < n; i += full ? 8 : 5) {
          var xs = pts[i * 4], ys = pts[i * 4 + 1], zs = pts[i * 4 + 2];
          var xs1 = xs * cay + zs * say, zs1 = -xs * say + zs * cay, ys1 = ys * cax - zs1 * sax, zs2 = ys * sax + zs1 * cax;
          var rs = R * k2, ss = camD * R / (camD * R - zs2 * rs);
          ctx.fillRect(cx + xs1 * rs * ss - 0.7, cy - ys1 * rs * ss - 0.7, 1.4, 1.4);
        }
      }
      /* ouvindo: anel fino de partículas orbitando, inclinado */
      if (st.listening) {
        var rp = st.ringPts, m = rp.length / 2, tilt = 0.44, ct = Math.cos(tilt), stt = Math.sin(tilt), spin = t * 0.9;
        for (i = 0; i < m; i++) {
          var ang = rp[i * 2] + spin, wob = rp[i * 2 + 1] * 0.03;
          var rx = Math.cos(ang) * 1.38, rz0 = Math.sin(ang) * 1.38, ry = rz0 * stt + wob, rz = rz0 * ct;
          var rx1 = rx * cay + rz * say, rz1 = -rx * say + rz * cay, ry1 = ry * cax - rz1 * sax, rz2 = ry * sax + rz1 * cax;
          var sr = camD * R / (camD * R - rz2 * R), fa = (rz2 + 1) / 2;
          ctx.fillStyle = 'rgba(' + tk.accent[0] + ',' + tk.accent[1] + ',' + tk.accent[2] + ',' + (0.25 + 0.6 * fa).toFixed(3) + ')';
          var rs2 = (full ? 1.1 : 0.8) * (0.6 + 0.8 * fa);
          ctx.fillRect(cx + rx1 * R * sr - rs2 / 2, cy - ry1 * R * sr - rs2 / 2, rs2, rs2);
        }
      }
      /* vinheta sutil: funde ao fundo da casca */
      var grd = ctx.createRadialGradient(cx, cy, Math.min(w, h) * 0.3, cx, cy, Math.max(w, h) * 0.75);
      grd.addColorStop(0, 'rgba(' + tk.bg + ',0)'); grd.addColorStop(1, 'rgba(' + tk.bg + ',0.7)');
      ctx.fillStyle = grd; ctx.fillRect(0, 0, w, h);
    }

    /* ---- laço ---- */
    function step(ts) {
      if (st.destroyed) return;
      st.raf = 0;
      var dt = st.last ? Math.min(0.05, (ts - st.last) / 1000) : 0.016;
      st.last = ts; st.t += dt;
      var now = st.t;
      if (now < st.speakUntil) {
        var env = 0.3 + 0.7 * Math.abs(Math.sin(now * 9.1 + st.speakSeed) * Math.sin(now * 2.3 + st.speakSeed * 0.7));
        st.level = Math.max(st.level, env);
      }
      if (st.level > 0.25 && now - st.lastRing > 0.18) { st.rings.push({ t0: now, amp: st.level }); st.lastRing = now; }
      st.level = Math.max(0, st.level - dt / 0.3);
      st.rings = st.rings.filter(function (r) { return now - r.t0 < 1.6; });
      st.shells = st.shells.filter(function (s) { return now - s.t0 < 1.1; });
      st.mx += (st.tx - st.mx) * 0.06; st.my += (st.ty - st.my) * 0.06;
      draw(now);
      if (!st.paused && !st.hidden && !st.offscreen) st.raf = requestAnimationFrame(step);
    }
    function running() { return !st.paused && !st.hidden && !st.offscreen && !isStatic() && !st.destroyed; }
    function start() { if (running() && !st.raf) { st.last = 0; st.raf = requestAnimationFrame(step); } }
    function stop() { if (st.raf) cancelAnimationFrame(st.raf); st.raf = 0; }

    function resize() {
      var r = canvas.getBoundingClientRect();
      st.w = Math.max(1, Math.round(r.width || canvas.clientWidth || 300));
      st.h = Math.max(1, Math.round(r.height || canvas.clientHeight || 160));
      st.dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(st.w * st.dpr); canvas.height = Math.round(st.h * st.dpr);
      draw(st.t);
    }

    /* ---- eventos ---- */
    function onVis() { st.hidden = !!document.hidden; if (st.hidden) stop(); else start(); }
    function onMove(e) {
      if (st.mode !== 'full') return;
      var r = canvas.getBoundingClientRect();
      st.tx = clamp((e.clientX - (r.left + r.width / 2)) / Math.max(1, r.width), -0.5, 0.5);
      st.ty = clamp((e.clientY - (r.top + r.height / 2)) / Math.max(1, r.height), -0.5, 0.5);
    }
    function onLeave() { st.tx = 0; st.ty = 0; }
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
    var ro = null;
    if (window.ResizeObserver) { ro = new ResizeObserver(function () { resize(); }); ro.observe(canvas); }
    var io = null;
    if (window.IntersectionObserver) {
      io = new IntersectionObserver(function (es) {
        st.offscreen = !es[es.length - 1].isIntersecting;
        if (st.offscreen) stop(); else start();
      });
      io.observe(canvas);
    }

    resize();
    start();

    var handle = {
      setLevel: function (v) { st.level = Math.max(st.level, clamp(+v || 0, 0, 1)); if (isStatic()) draw(st.t); else start(); },
      speak: function (ms) { if (isStatic()) return; st.speakUntil = st.t + Math.max(0, (+ms || 0) / 1000); st.speakSeed = Math.random() * 10; start(); },
      pulse: function () { if (isStatic()) return; st.shells.push({ t0: st.t }); st.rings.push({ t0: st.t, amp: 0.8 }); start(); },
      setListening: function (b) { st.listening = !!b; if (isStatic()) draw(st.t); else start(); },
      setMode: function (m) { st.mode = m === 'mini' ? 'mini' : 'full'; build(); resize(); },
      resize: resize,
      pause: function () { st.paused = true; stop(); },
      resume: function () { st.paused = false; start(); },
      destroy: function () {
        st.destroyed = true; stop();
        document.removeEventListener('visibilitychange', onVis);
        window.removeEventListener('resize', resize);
        window.removeEventListener('mousemove', onMove);
        canvas.removeEventListener('mouseleave', onLeave);
        if (ro) ro.disconnect();
        if (io) io.disconnect();
        try { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); } catch (e) {}
      },
      _state: st
    };
    return handle;
  }

  window.ApolloMesh = { create: create, version: 2 };
})();
