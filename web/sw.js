// Service worker do app instalado (PWA). Guarda SO a casca: o HTML, as libs de web/vendor e os
// icones. Nunca a API.
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
const CASCA = 'casca-v1';

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
      const c = r.clone(); caches.open(CASCA).then(k => k.put(req, c)); return r;
    }).catch(() => caches.match(req).then(r => r || caches.match('./'))));
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
