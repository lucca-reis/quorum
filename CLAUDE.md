# quorum

Site estático (GitHub Pages) com dados sobre os Três Poderes: Câmara, Senado, STF e Presidência.
Endereço: https://lucca-reis.github.io/quorum/

## Arquivos

- `index.html`: o site inteiro (HTML, CSS e JS num arquivo só). Os dados escritos à mão ficam em constantes JS dentro dele:
  - `AGENDA.camara`, `AGENDA.senado`, `AGENDA.stf`, `AGENDA.exec`: linha do tempo de cada poder. Cada dia tem `{date:'AAAA-MM-DD', kind, time?, label?, items:[...]}`. Item com `ref` aponta para um projeto em `PROJECTS`; item sem `ref` tem `id` (título curto) e `t` (texto).
  - `PROJECTS`: uma página por proposta ou processo (`#p-slug`), com resumo, etapas, votação, links e fontes.
  - `PANEL_SOURCES`, `STF_SOURCES`, `EXEC_SOURCES`: fontes mostradas no ícone "i".
- Cartões: cada item de `PROJECTS` vira um cartão no feed da página inicial e das seções. O histórico do cartão vem dos dias de `AGENDA` que citam o item (`ref`) e de `steps` do próprio projeto. O cartão sobe no feed pela data (e `time`) mais recente em que foi tratado. Para um cartão mostrar a data de criação, o primeiro item de `steps` deve ser a apresentação ou publicação (ex.: "Apresentado na Câmara", "MP publicada"). Escreva cada passo de `steps` começando pelo poder onde aconteceu ("Câmara aprova…", "Senado aprova…", "Presidente sanciona…"), porque é isso que define por onde o cartão passou. Resultado de sessão em `r` com "vai à sanção" ou "segue ao Senado" move o cartão para o próximo poder.
- Placar: quando a fonte informar os números de uma votação, preencha `votes.tally` (`[['Votação', sim, não]]`, um item por turno) e, se os lados não forem sim/não, `votes.labels`. É isso que desenha o mini plenário de bolinhas no cartão. Sem números na fonte, não preencha `tally`; se o resultado disser "unanimidade" ou "votação simbólica", o mini plenário aparece com todas as cadeiras pintadas e a legenda "sem placar divulgado".
- Símbolos dos poderes (família "pontos", em `GLYPHS`/`glyph()`): Legislativo = pontos em semicírculo, Executivo = um ponto, Judiciário = 11 pontos em U. Só no calendário; menu e cartões ficam só com texto.
- Visão geral (`#visao-geral`, funções `vg*` e `renderVg`): painel montado só com dados que o site já tem: itens em curso por poder, linha "por onde andam", prazos de MPs (120 dias, sem contar o recesso, marcados como estimativa) e de sanção (só quando a fonte dá a data), últimas votações com placar, enquetes em alta e composição das casas e do STF.
- Cartões abertos: descrição, depois campos rotulados (Autoria, Relatoria, Criado, Próximo passo) e a votação num bloco próprio.
- Menu superior: Visão geral, Executivo (Presidência), Legislativo (abre Senado e Congresso ao passar o mouse ou tocar), Judiciário (STF) e Enquetes (`#consultas`, as consultas públicas do e-Cidadania).
- Cartões na Presidência não mostram placar do Congresso: mostram a marca de assinatura do presidente (desenho estilizado, não a assinatura real) com a data quando ele sancionou, editou a MP ou enviou a proposta; "Aguarda sanção" enquanto espera; "Vetado" se houver veto.
- `data/consultas.json`: gerado de hora em hora por `scripts/consultas.py` a partir do portal e-Cidadania do Senado (votos SIM e NÃO de cada proposição aberta) e da API de processos do Senado (data de apresentação, apelido, autoria). A página `#consultas` lê esse arquivo. O voto acontece só no site oficial: o botão "Dar seu voto" abre a página da proposição no e-Cidadania. Não editar à mão.
- `data/live.json`: gerado de hora em hora pelo robô (`scripts/atualizar.py`, `.github/workflows/atualizar.yml`) a partir das APIs de dados abertos da Câmara e do Senado. Não editar à mão.

## Regras para atualizar o conteúdo

- Texto em português, linguagem simples, parafraseado das fontes. Nunca copiar trechos longos.
- Toda informação nova precisa de fonte com link (notícias oficiais: Agência Câmara, Agência Senado, STF Notícias, gov.br/planalto, Agência Brasil, Diário Oficial).
- Campo que a fonte não informa fica como "não informado". Nunca inventar números, votos ou resultados.
- Não usar fotos de pessoas.
- Manter o estilo do código existente; mudanças pequenas e localizadas.
- Depois de editar, abrir o `index.html` no Playwright (Chromium já instalado) e conferir que não há erro de JavaScript no console.
- Mensagem de commit em português, curta, dizendo o que mudou.
