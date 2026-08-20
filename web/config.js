// Aponta o front pro backend.
//
// VAZIO = mesma origem: o próprio backend serve este arquivo (modo monolito, local
// ou VM). É o padrão e não quebra nada.
//
// Front separado no Vercel: troque pela URL **HTTPS** do backend na VM Azure, ex:
//   window.API_BASE = "https://meu-bot.brazilsouth.cloudapp.azure.com";
// Tem que ser https:// — página HTTPS não pode chamar http:// (mixed content).
window.API_BASE = "https://cripto-bot-24517.southafricanorth.cloudapp.azure.com";
