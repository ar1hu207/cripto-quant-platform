/* Celular abre o app do celular (m.html), que é outra tela sobre o MESMO backend, a mesma credencial e as
   mesmas regras (app/api.js e app/comum.js). Carregado no topo do <head> do index.html, SEM defer: roda
   antes de qualquer pintura para não piscar o desktop. Escolha explícita vence a largura: "Versão completa"
   no app grava apx.ui=desktop, e "App do celular" no menu da conta grava apx.ui=mobile. O hash vai junto
   (#operar abre o Operar de lá).

   Era um <script> embutido no index.html. Virou arquivo porque a CSP não aceita mais script embutido
   (`script-src 'self'`, sem 'unsafe-inline'): é o que impede HTML injetado de executar e ler a credencial
   do localStorage. Não volte com ele para dentro do HTML: o navegador o bloquearia em silêncio e o celular
   passaria a abrir o desktop. */
(function () {
  var pref = null; try { pref = localStorage.getItem('apx.ui'); } catch (e) {}
  var cel = window.matchMedia && (matchMedia('(max-width: 760px)').matches || matchMedia('(max-height: 500px) and (pointer: coarse)').matches);
  if (pref === 'mobile' || (pref !== 'desktop' && cel)) location.replace('m.html' + location.search + location.hash);
})();
