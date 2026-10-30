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
- `data/live.json`: gerado de hora em hora pelo robô (`scripts/atualizar.py`, `.github/workflows/atualizar.yml`) a partir das APIs de dados abertos da Câmara e do Senado. Não editar à mão.

## Regras para atualizar o conteúdo

- Texto em português, linguagem simples, parafraseado das fontes. Nunca copiar trechos longos.
- Toda informação nova precisa de fonte com link (notícias oficiais: Agência Câmara, Agência Senado, STF Notícias, gov.br/planalto, Agência Brasil, Diário Oficial).
- Campo que a fonte não informa fica como "não informado". Nunca inventar números, votos ou resultados.
- Não usar fotos de pessoas.
- Manter o estilo do código existente; mudanças pequenas e localizadas.
- Depois de editar, abrir o `index.html` no Playwright (Chromium já instalado) e conferir que não há erro de JavaScript no console.
- Mensagem de commit em português, curta, dizendo o que mudou.
