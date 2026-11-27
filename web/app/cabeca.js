/* O que o <head> do index.html e do m.html fazia em <script> embutido e em atributo onload. Carregado logo
   depois do config.js, SEM defer (precisa do window.API_BASE e tem de rodar antes da primeira pintura).

   Virou arquivo porque a CSP não aceita mais script embutido nem handler em atributo (`script-src 'self'`,
   sem 'unsafe-inline'): é o que impede HTML injetado de executar e ler a credencial do localStorage.
   Não volte com nada disto para dentro do HTML: o navegador bloquearia em silêncio. */
(function () {
  /* Abre a conexão com o backend enquanto o resto do front ainda baixa. */
  if (window.API_BASE) {
    var pc = document.createElement('link');
    pc.rel = 'preconnect'; pc.href = window.API_BASE; pc.crossOrigin = '';
    document.head.appendChild(pc);
  }
  /* Fontes sem bloquear a primeira pintura (P2-37). O HTML traz a folha do Google Fonts como
     <link rel="preload" as="style">, que só baixa; aqui ela vira stylesheet de verdade. Entra como
     media=print (não segura a pintura) e passa a valer no load. O listener é posto ANTES de a folha entrar
     no documento: o `onload="this.rel='stylesheet'"` de antes era handler em atributo, e trocar por um
     listener no próprio preload perderia o evento quando a folha já estivesse no cache. */
  var pre = document.querySelector('link[rel="preload"][as="style"]');
  if (pre) {
    var folha = document.createElement('link');
    folha.rel = 'stylesheet'; folha.href = pre.href; folha.media = 'print';
    folha.addEventListener('load', function () { folha.media = 'all'; });
    document.head.appendChild(folha);
  }
})();
