"""Proposições que viraram norma (lei, emenda constitucional, decreto legislativo…) nos últimos 12 meses,
com o partido de quem as apresentou. Alimenta o gráfico "Partidos que mais aprovaram projetos" da Visão geral.

Fonte: dados abertos da Câmara (todas as leis passam pela Câmara, inclusive as que começaram no Senado):
  /referencias/proposicoes/codSituacao  → código da situação "Transformado em Norma Jurídica"
  /proposicoes?codSituacao=…&dataInicio=…  → proposições nessa situação com tramitação no período
  /proposicoes/{id}                    → data em que virou norma
  /proposicoes/{id}/autores            → primeiro autor
  /deputados/{id}                      → partido atual do deputado autor
Partido de senadores: lista de senadores em exercício do Senado. Grava data/leis.json. Só usa a biblioteca padrão."""
import json, re, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
HOJE = datetime.datetime.now(BR).date()
INICIO = HOJE.replace(year=HOJE.year - 1)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
CAM = 'https://dadosabertos.camara.leg.br/api/v2/'
UA = {'Accept': 'application/json', 'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
log = []

def get(url):
    for n in range(3):
        try:
            time.sleep(0.25)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode('utf-8') or 'null')
        except Exception as ex:
            if n == 2: log.append(f'{url}: {ex}'); return None
            time.sleep(3)

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).upper().strip()

itens, props = [], {}
def coletar():
    global itens, props
    # 1) código da situação "Transformado(a) em Norma Jurídica"
    refs = (get(CAM + 'referencias/proposicoes/codSituacao') or {}).get('dados', [])
    cods = [r['cod'] for r in refs if 'NORMA JURIDICA' in norm(r.get('nome') or r.get('descricao'))]
    if not cods: log.append('situação "Transformado em Norma Jurídica" não encontrada')

    # 2) proposições nessa situação com tramitação no período
    props = {}
    for cod in cods:
        for pag in range(1, 40):
            js = get(CAM + 'proposicoes?' + urllib.parse.urlencode({'codSituacao': cod, 'dataInicio': INICIO.isoformat(), 'dataFim': HOJE.isoformat(),
                                                                    'itens': 100, 'pagina': pag, 'ordem': 'DESC', 'ordenarPor': 'id'}))
            dados = (js or {}).get('dados', [])
            for p in dados: props[p['id']] = p
            if len(dados) < 100: break

    # partidos dos senadores em exercício (para autores do Senado)
    sen = {}
    js = get('https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json')
    try:
        for p in js['ListaParlamentarEmExercicio']['Parlamentares']['Parlamentar']:
            i = p['IdentificacaoParlamentar']
            sen[norm(i.get('NomeParlamentar'))] = i.get('SiglaPartidoParlamentar')
    except Exception as ex:
        log.append(f'senadores: {ex}')

    partido_dep = {}
    itens = []
    for pid, p in props.items():
        det = (get(CAM + f'proposicoes/{pid}') or {}).get('dados', {})
        st = det.get('statusProposicao') or {}
        quando = (st.get('dataHora') or '')[:10]
        if not quando or not (INICIO.isoformat() <= quando <= HOJE.isoformat()): continue
        if 'NORMA JURIDICA' not in norm(st.get('descricaoSituacao')): continue
        autores = (get(CAM + f'proposicoes/{pid}/autores') or {}).get('dados', [])
        autores.sort(key=lambda a: (a.get('ordemAssinatura') or 99, -(a.get('proponente') or 0)))
        a = autores[0] if autores else {}
        tipo, nome, partido = a.get('tipo') or '', a.get('nome') or 'não informado', None
        if 'Deputad' in tipo and a.get('uri'):
            did = a['uri'].rstrip('/').split('/')[-1]
            if did not in partido_dep:
                partido_dep[did] = ((get(CAM + f'deputados/{did}') or {}).get('dados', {}).get('ultimoStatus') or {}).get('siglaPartido')
            partido = partido_dep[did]
        elif 'Senad' in tipo:
            partido = sen.get(norm(re.sub(r'^Senador[a]?\s+', '', nome)))
        grupo = partido or ('Poder Executivo' if 'Executivo' in tipo else 'Senado (sem partido identificado)' if 'Senad' in tipo
                            else 'Comissões e outros órgãos' if tipo else 'não informado')
        itens.append({'s': p.get('siglaTipo'), 'n': p.get('numero'), 'a': p.get('ano'), 'e': (p.get('ementa') or '')[:200], 'd': quando,
                      'autor': nome, 'tipo': tipo, 'grupo': grupo, 'partido': partido,
                      'u': f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}"})


try:
    coletar()
except Exception as ex:
    import traceback
    log.append('falha: ' + traceback.format_exc()[-600:])

cont = {}
for i in itens: cont[i['grupo']] = cont.get(i['grupo'], 0) + 1
OUT.mkdir(exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'periodo': [INICIO.isoformat(), HOJE.isoformat()],
       'total': len(itens), 'grupos': sorted(cont.items(), key=lambda x: -x[1]), 'itens': sorted(itens, key=lambda i: i['d'], reverse=True),
       'fonte': 'https://dadosabertos.camara.leg.br', 'erros': log[:30]}
(OUT / 'leis.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'candidatas': len(props), 'normas': len(itens), 'grupos': res['grupos'][:12], 'erros': log[:5]}, ensure_ascii=False))
