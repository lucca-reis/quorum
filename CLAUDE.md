# quorum

Site estático (GitHub Pages) com dados sobre os Três Poderes: Câmara, Senado, STF e Presidência.
Endereço: https://lucca-reis.github.io/quorum/

## Arquivos

- `index.html`: o site inteiro (HTML, CSS e JS num arquivo só). Os dados escritos à mão ficam em constantes JS dentro dele:
  - `AGENDA.camara`, `AGENDA.senado`, `AGENDA.stf`, `AGENDA.exec`: linha do tempo de cada poder. Cada dia tem `{date:'AAAA-MM-DD', kind, time?, label?, items:[...]}`. Item com `ref` aponta para um projeto em `PROJECTS`; item sem `ref` tem `id` (título curto) e `t` (texto).
  - `PROJECTS`: uma página por proposta ou processo (`#p-slug`), com resumo, etapas, votação, links e fontes.
  - `PANEL_SOURCES`, `STF_SOURCES`, `EXEC_SOURCES`: fontes mostradas no ícone "i".
- `data/live.json`: gerado de hora em hora pelo robô (`scripts/atualizar.py`, `.github/workflows/atualizar.yml`) a partir das APIs de dados abertos da Câmara e do Senado. Não editar à mão.

## Regras para atualizar o conteúdo

- Texto em português, linguagem simples, parafraseado das fontes. Nunca copiar trechos longos.
- Toda informação nova precisa de fonte com link (notícias oficiais: Agência Câmara, Agência Senado, STF Notícias, gov.br/planalto, Agência Brasil, Diário Oficial).
- Campo que a fonte não informa fica como "não informado". Nunca inventar números, votos ou resultados.
- Não usar fotos de pessoas.
- Manter o estilo do código existente; mudanças pequenas e localizadas.
- Depois de editar, abrir o `index.html` no Playwright (Chromium já instalado) e conferir que não há erro de JavaScript no console.
- Mensagem de commit em português, curta, dizendo o que mudou.
