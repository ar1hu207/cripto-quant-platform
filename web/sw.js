// Service worker do app instalado (PWA). Guarda SO a casca: o HTML, o codigo do front em web/app,
// as libs de web/vendor e os icones. Nunca a API.
//
// A API mora em outra origem (a VM) e responde com a credencial do painel no header: cachear
// isso seria guardar banca e posicao velhas num disco que o usuario nao sabe que existe, e
// mostra-las como se fossem de agora quando a rede cair. Por isso requisicao de outra origem
// nem passa por aqui -- o `return` sem respondWith devolve a decisao ao navegador.
//
// config.js tambem passa direto: o vercel.json manda no-store nele porque e o arquivo que
// aponta o front para o backend, e um cache aqui furaria exatamente essa garantia.
//
// O HTML vai rede-primeiro: merge na main publica no Vercel, e cache-primeiro prenderia o
// celular na versao de ontem ate a pessoa reinstalar. O cache so responde sem rede, para o
// app abrir e mostrar o proprio estado de "sem conexao" em vez da tela do sistema.
// casca-v2 = front Apollux: o activate apaga o cache v1, que guardava o painel antigo como index.
const CASCA = 'casca-v2';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CASCA).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request, u = new URL(req.url);
  if (req.method !== 'GET' || u.origin !== location.origin) return;
  if (u.pathname.endsWith('/config.js')) return;

  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(r => {
      // só guarda resposta boa: um 404/5xx do Vercel não pode substituir a casca que abre offline
      if (r.ok) { const c = r.clone(); caches.open(CASCA).then(k => k.put(req, c)); }
      return r;
    }).catch(() => caches.match(req).then(r => r || caches.match('./'))));
    return;
  }
  // web/app (casca.js, api.js, views): rede-primeiro, como o HTML, e pelo mesmo motivo. O HTML e
  // o JS da casca andam juntos (ids, contrato das views); se o HTML viesse novo da rede e o JS
  // velho do cache, a tela quebraria justamente no dia do deploy. O cache so responde sem rede.
  if (u.pathname.includes('/app/')) {
    e.respondWith(fetch(req).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(CASCA).then(k => k.put(req, c)); }
      return r;
    }).catch(() => caches.match(req).then(r => r || Response.error())));
    return;
  }
  // libs e icones: responde do cache e renova em segundo plano. Os nomes em web/vendor NAO
  // carregam versao (chart.umd.min.js), entao cache-primeiro puro prenderia o celular na lib
  // antiga para sempre depois de uma atualizacao; assim ela troca na abertura seguinte.
  if (u.pathname.includes('/vendor/') || u.pathname.includes('/icons/')) {
    const rede = fetch(req).then(resp => {
      if (resp.ok) { const c = resp.clone(); caches.open(CASCA).then(k => k.put(req, c)); }
      return resp;
    });
    e.respondWith(caches.match(req).then(r => r || rede));
    e.waitUntil(rede.catch(() => {}));
  }
});

// [PUSH-1] Notificacao nativa. O backend cifra para este aparelho e entrega pelo servico de push
// dele (Apple/Google); aqui ela vira notificacao do sistema. TODO push tem que mostrar uma
// notificacao: o iOS retira a permissao do app que recebe push e fica calado. Por isso nao ha
// caminho que saia daqui sem showNotification, nem com corpo ilegivel.
// `tag` agrupa: "pos-12" do aviso de abertura e trocado pelo de fechamento da mesma posicao.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { corpo: e.data ? e.data.text() : '' }; }
  const op = { body: d.corpo || '', icon: 'icons/icon-192.png', badge: 'icons/icon-192.png',
               lang: 'pt-BR', data: { url: d.url || '#painel' } };
  if (d.tag) { op.tag = d.tag; op.renotify = true; }
  e.waitUntil(self.registration.showNotification(d.titulo || 'Apollux', op));
});

// Toque na notificacao: com o app aberto, foca e manda para a tela do aviso (a pagina troca o
// hash, sem recarregar); fechado, abre pela raiz, e o index decide celular ou desktop.
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '#painel';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
    const c = cs.find(x => x.url.startsWith(self.registration.scope));
    if (c) { c.postMessage({ tipo: 'abrir', url: url }); return c.focus(); }
    return self.clients.openWindow(new URL('./' + url, self.registration.scope).href);
  }));
});
