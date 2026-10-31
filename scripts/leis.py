"""Proposições que viraram norma (lei, emenda constitucional, decreto legislativo…) nos últimos 12 meses,
com o partido de quem as apresentou. Alimenta o gráfico "Partidos que mais aprovaram projetos" da Visão geral.

Fonte: arquivos anuais de dados abertos da Câmara (todas as leis passam pela Câmara, inclusive as que começaram no Senado).
A API de busca por situação da Câmara não responde a tempo (504), então o robô lê os arquivos completos:
  https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-AAAA.csv
      → situação atual de cada proposição apresentada no ano ("Transformado em Norma Jurídica") e a data
  https://dadosabertos.camara.leg.br/arquivos/proposicoesAutores/csv/proposicoesAutores-AAAA.csv
      → autores, com o partido de cada um na época
Conta pelo primeiro autor. Grava data/leis.json. Só usa a biblioteca padrão."""
import csv, io, json, re, datetime, zoneinfo, pathlib, unicodedata, urllib.request, traceback

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
HOJE = datetime.datetime.now(BR).date()
INICIO = HOJE.replace(year=HOJE.year - 1)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
ARQ = 'https://dadosabertos.camara.leg.br/arquivos/'
UA = {'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
TIPOS = {'PL', 'PLP', 'PEC', 'MPV', 'PDL', 'PLV', 'PDC'}
log = []

def baixar(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read().decode('utf-8-sig', 'replace')

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).upper().strip()

def col(row, *nomes):
    for n in nomes:
        if n in row and row[n] not in (None, ''): return row[n]
    return ''

itens = []
def coletar():
    # leis aprovadas agora podem ter sido apresentadas muitos anos antes: lê os arquivos desde 2003
    for ano in range(HOJE.year, 2002, -1):
        try:
            txt = baixar(f'{ARQ}proposicoes/csv/proposicoes-{ano}.csv')
        except Exception as ex:
            log.append(f'proposicoes {ano}: {ex}'); continue
        achadas = {}
        for r in csv.DictReader(io.StringIO(txt), delimiter=';'):
            if col(r, 'siglaTipo') not in TIPOS: continue
            sit = norm(col(r, 'ultimoStatus_descricaoSituacao', 'statusProposicao_descricaoSituacao'))
            if 'NORMA JURIDICA' not in sit: continue
            quando = col(r, 'ultimoStatus_dataHora', 'statusProposicao_dataHora')[:10]
            if not (INICIO.isoformat() <= quando <= HOJE.isoformat()): continue
            achadas[col(r, 'id')] = {'s': r['siglaTipo'], 'n': col(r, 'numero'), 'a': col(r, 'ano'), 'e': col(r, 'ementa')[:200], 'd': quando,
                                     'u': f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={col(r, 'id')}"}
        if not achadas: continue
        try:
            aut = baixar(f'{ARQ}proposicoesAutores/csv/proposicoesAutores-{ano}.csv')
        except Exception as ex:
            log.append(f'autores {ano}: {ex}'); aut = ''
        primeiros = {}
        for r in csv.DictReader(io.StringIO(aut), delimiter=';'):
            pid = col(r, 'idProposicao')
            if pid not in achadas: continue
            ordem = int(col(r, 'ordemAssinatura') or 99)
            if pid not in primeiros or ordem < primeiros[pid][0]:
                primeiros[pid] = (ordem, r)
        for pid, p in achadas.items():
            r = primeiros.get(pid, (0, {}))[1]
            tipo, nome, partido = col(r, 'tipoAutor'), col(r, 'nomeAutor') or 'não informado', col(r, 'siglaPartidoAutor') or None
            grupo = partido or ('Poder Executivo' if 'EXECUTIVO' in norm(tipo + ' ' + nome) or 'PRESIDENCIA DA REPUBLICA' in norm(nome)
                                else 'Senado (sem partido no arquivo)' if 'SENAD' in norm(tipo + ' ' + nome)
                                else 'Comissões e outros órgãos' if tipo else 'não informado')
            itens.append({**p, 'autor': nome, 'tipo': tipo, 'partido': partido, 'grupo': grupo})

try:
    coletar()
except Exception:
    log.append('falha: ' + traceback.format_exc()[-600:])

cont = {}
for i in itens: cont[i['grupo']] = cont.get(i['grupo'], 0) + 1
OUT.mkdir(exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'periodo': [INICIO.isoformat(), HOJE.isoformat()],
       'total': len(itens), 'grupos': sorted(cont.items(), key=lambda x: -x[1]), 'itens': sorted(itens, key=lambda i: i['d'], reverse=True),
       'fonte': 'https://dadosabertos.camara.leg.br/swagger/api.html#staticfile', 'erros': log[:30]}
(OUT / 'leis.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'normas': len(itens), 'grupos': res['grupos'][:15], 'erros': log[:5]}, ensure_ascii=False))
