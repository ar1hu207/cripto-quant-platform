// Paletas completas para a direção Pulse (Apollux). Fonte única: o mockup (d4-pulse.html) e o catálogo
// (paletas-pulse.html) leem daqui. Cada paleta retinta TODOS os tokens, não só o acento.
// Semântica fixa: pos = alta/lucro/LONG, neg = baixa/prejuízo/SHORT, warn = aviso. O acento nunca é usado em P&L.
// glow = alpha do brilho (0 a 1) permitido em item ativo, LED, linha de gráfico e foco; nunca em bloco.
window.APOLLUX_PALETAS = [
  {
    id: "neon", nome: "Neon", familia: "verde",
    historia: "A paleta original do Pulse: o mercado pulsa em verde fósforo sobre preto esverdeado. Energia máxima; exige disciplina no brilho.",
    melhorPara: "marca reconhecível de longe; quem gosta de ver o sinal",
    conflito: "o acento é da mesma família do verde de lucro: P&L usa pos sem brilho, o acento nunca aparece em número de P&L",
    t: { bg: "#030705", panel: "#0A1410", panel2: "#0F1C16", line: "#123D2A", line2: "#1C5A3E", text: "#E8FFF3", text2: "#8FB3A3", mute: "#6B8A78",
         accent: "#00FF88", on: "#03140A", pos: "#34D399", neg: "#FF4D6D", warn: "#FFD166", info: "#4DA3FF", glow: 0.5 }
  },
  {
    id: "eletrico", nome: "Elétrico", familia: "azul",
    historia: "O azul do print que você escolheu, agora com fundo, bordas e superfícies retintados para azul-preto em vez de verde-preto. Lê como instrumento de precisão.",
    melhorPara: "sessão longa; separa limpo o acento (azul) do dinheiro (verde/vermelho)",
    conflito: "nenhum: azul não disputa com lucro nem com prejuízo",
    t: { bg: "#03060C", panel: "#0A1220", panel2: "#0F1A2C", line: "#16304F", line2: "#1F4573", text: "#EAF2FF", text2: "#93A9C8", mute: "#7088A8",
         accent: "#4DA3FF", on: "#04101F", pos: "#34D399", neg: "#FF5C6A", warn: "#FFC24D", info: "#7DD3FC", glow: 0.45 }
  },
  {
    id: "solar", nome: "Solar", familia: "âmbar",
    historia: "Apollo é o deus do sol e da luz: âmbar quente sobre preto-café. É a paleta que conta a história do nome Apollux sem dizer uma palavra.",
    melhorPara: "identidade própria, longe do azul de todo mundo; combina com Apollo",
    conflito: "âmbar é a cor universal de aviso: aqui o aviso vira laranja-avermelhado e ganha ícone sempre",
    t: { bg: "#0A0704", panel: "#15100A", panel2: "#1C1610", line: "#3D2E14", line2: "#5A431C", text: "#FFF6E8", text2: "#C4B394", mute: "#9A8C72",
         accent: "#FFB020", on: "#1A1000", pos: "#3FD98C", neg: "#FF5A5F", warn: "#FF7A1A", info: "#7DD3FC", glow: 0.35 }
  },
  {
    id: "ouro", nome: "Ouro", familia: "dourado",
    historia: "O Solar com o volume abaixado: ouro fosco, menos saturado, brilho contido. Premium sem gritar.",
    melhorPara: "produto de assinatura; quem opera 8 horas e quer calma",
    conflito: "mesmo cuidado do Solar com o aviso; o acento em texto corrido cansa, use só em foco e ativo",
    t: { bg: "#0B0A08", panel: "#141210", panel2: "#1B1915", line: "#3A3220", line2: "#55492E", text: "#F5F1E8", text2: "#B8AE9A", mute: "#8F8772",
         accent: "#E2C275", on: "#1A1405", pos: "#3FD98C", neg: "#FF5A5F", warn: "#FF8A3D", info: "#7DD3FC", glow: 0.3 }
  },
  {
    id: "holo", nome: "Holo", familia: "ciano",
    historia: "O ciano holográfico do Command Deck dentro da estrutura do Pulse: HUD sem os colchetes.",
    melhorPara: "sensação Jarvis; densidade alta",
    conflito: "nenhum direto; ciano perto do verde-água em telas ruins, por isso pos é um verde mais amarelado",
    t: { bg: "#04080A", panel: "#0A1418", panel2: "#0F1C22", line: "#143A44", line2: "#1D5563", text: "#E6FBFF", text2: "#8FB8C4", mute: "#6E949F",
         accent: "#19E6FF", on: "#04181D", pos: "#2BE39A", neg: "#FF5C6A", warn: "#FFB020", info: "#7DD3FC", glow: 0.45 }
  },
  {
    id: "magenta", nome: "Magenta", familia: "rosa",
    historia: "A variante magenta do Pulse levada ao fundo: preto-ameixa, bordas roxas, acento rosa elétrico.",
    melhorPara: "marca forte e jovem; difícil de confundir com qualquer corretora",
    conflito: "magenta e vermelho de prejuízo são vizinhos: neg desloca para laranja-vermelho e ganha seta sempre",
    t: { bg: "#0A040A", panel: "#150A14", panel2: "#1E1020", line: "#3F1A3D", line2: "#5C2659", text: "#FFF0FA", text2: "#C49BBE", mute: "#977691",
         accent: "#FF3DA6", on: "#1C0414", pos: "#34D399", neg: "#FF6B4D", warn: "#FFD166", info: "#7DD3FC", glow: 0.45 }
  },
  {
    id: "violeta", nome: "Violeta", familia: "roxo",
    historia: "Roxo profundo com acento lilás: o céu noturno em vez do neon. Menos agressivo que o magenta, mais quente que o azul.",
    melhorPara: "quem quer cor sem perder a calma; funciona bem em celular",
    conflito: "nenhum direto",
    t: { bg: "#06050C", panel: "#0E0C1A", panel2: "#151226", line: "#2B2550", line2: "#3E3670", text: "#EFEBFF", text2: "#A79FCB", mute: "#817AA5",
         accent: "#8B6CFF", on: "#0F0820", pos: "#34D399", neg: "#FF5C6A", warn: "#FFC24D", info: "#7DD3FC", glow: 0.4 }
  },
  {
    id: "osso", nome: "Osso", familia: "mono",
    historia: "O Ledger dentro do Pulse: quase sem croma, branco quente como acento. A cor só aparece onde há dinheiro.",
    melhorPara: "densidade máxima e 8 horas sem cansar; envelhece melhor",
    conflito: "nenhum; o brilho cai para 0,2 porque branco brilhando lê como erro de tela",
    t: { bg: "#0B0B0C", panel: "#121214", panel2: "#18181B", line: "#2A2A2F", line2: "#3A3A41", text: "#EDEDEF", text2: "#9A9AA3", mute: "#8A8A92",
         accent: "#E8E4D9", on: "#121212", pos: "#3FD98C", neg: "#FF5A5F", warn: "#E3B341", info: "#9FB3C8", glow: 0.2 }
  },
  {
    id: "aco", nome: "Aço", familia: "azul-cinza",
    historia: "Cinza-azulado de baixa saturação: o acento é um aço claro, não uma luz. Instrumento de cockpit.",
    melhorPara: "sobriedade; quem acha o Osso frio demais e o Elétrico vivo demais",
    conflito: "nenhum",
    t: { bg: "#0A0C10", panel: "#111419", panel2: "#171B22", line: "#2A313D", line2: "#3B4553", text: "#E9EDF3", text2: "#9CA7B8", mute: "#7A8594",
         accent: "#9FB3C8", on: "#0E1218", pos: "#3FD98C", neg: "#FF5A5F", warn: "#E3B341", info: "#7DD3FC", glow: 0.25 }
  },
  {
    id: "lima", nome: "Lima", familia: "verde-amarelo",
    historia: "O lima do Volt sobre o preto-oliva: mais amarelo que o neon, menos elétrico, mais fintech.",
    melhorPara: "lê bem para quem não é trader; assinatura",
    conflito: "mesma família do verde de lucro: vale a regra do Neon (acento nunca em P&L)",
    t: { bg: "#0A0A06", panel: "#131408", panel2: "#1A1B0C", line: "#35381A", line2: "#4C5026", text: "#F7F8EC", text2: "#B8BB9A", mute: "#8F9272",
         accent: "#D4FF3F", on: "#141800", pos: "#3FD98C", neg: "#FB7185", warn: "#FF8A3D", info: "#7DD3FC", glow: 0.35 }
  },
  {
    id: "menta", nome: "Menta", familia: "verde-água",
    historia: "Verde-água frio sobre preto-petróleo: o neon depois de um banho. Mantém a família verde, perde a agressividade.",
    melhorPara: "quem gostou do Neon mas quer operar sem óculos escuros",
    conflito: "menta e verde de lucro são próximos: pos vira um verde mais amarelado e o acento sai de todo número",
    t: { bg: "#040908", panel: "#0A1513", panel2: "#0F1C1A", line: "#164038", line2: "#215C50", text: "#E9FFFA", text2: "#93BDB3", mute: "#71968C",
         accent: "#5CF0C8", on: "#03201A", pos: "#4ADE80", neg: "#FF5C6A", warn: "#FFD166", info: "#7DD3FC", glow: 0.4 }
  },
  {
    id: "coral", nome: "Coral", familia: "laranja",
    historia: "Laranja-coral sobre preto-tijolo. Quente, raro em finanças, e por isso arriscado: é a paleta que mais disputa com a cor de prejuízo.",
    melhorPara: "ver que não é o caminho, ou provar que é: só com a regra de neg rosa-vermelho e seta sempre",
    conflito: "ALTO: acento quente vizinho do vermelho de baixa; neg desloca para rosa-vermelho e todo P&L negativo leva seta",
    t: { bg: "#0B0605", panel: "#160C0A", panel2: "#1E120F", line: "#3F2119", line2: "#5C3024", text: "#FFF1EC", text2: "#C8A59A", mute: "#9E8277",
         accent: "#FF6A3D", on: "#1E0A03", pos: "#3FD98C", neg: "#FF2D6F", warn: "#FFD166", info: "#7DD3FC", glow: 0.35 }
  }
];
