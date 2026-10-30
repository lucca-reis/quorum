"""Votos nominais de cada deputado e senador nas votações dos projetos que aparecem no site.

Para cada projeto de PROJECTS (index.html) com sigla de proposição (PL, PEC, PLP, PDL, MPV…):
  - Câmara: /proposicoes → /proposicoes/{id}/votacoes → /votacoes/{id}/votos (dados abertos da Câmara)
  - Senado: /processo (código da matéria) → /votacao?codigoMateria= (dados abertos do Senado)
Grava data/votos.json: para cada projeto, as votações nominais com o voto de cada parlamentar.
Votações simbólicas não têm voto individual e não aparecem aqui. Roda uma vez por dia junto com a transparência.
Também grava data/votos-amostra.json com exemplos das respostas, para conferir o formato. Só usa a biblioteca padrão."""
import json, re, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data'
UA = {'Accept': 'application/json', 'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
log, amostra = [], {}

def get(url, chave=None):
    try:
        time.sleep(0.3)
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            js = json.loads(r.read().decode('utf-8') or 'null')
        if chave and chave not in amostra: amostra[chave] = {'url': url, 'resposta': js if not isinstance(js, list) else js[:3]}
        return js
    except Exception as ex:
        log.append(f'{url}: {ex}'); return None

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).upper().strip()

def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', norm(t).lower()).strip('-')

def achar(o, *nomes):
    """Primeiro valor encontrado para uma das chaves, procurando em qualquer nível."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in nomes and v not in (None, ''): return v
        for v in o.values():
            r = achar(v, *nomes)
            if r not in (None, ''): return r
    elif isinstance(o, list):
        for v in o:
            r = achar(v, *nomes)
            if r not in (None, ''): return r
    return None

def listas(o, chave):
    """Todas as listas de objetos que têm a chave `chave` dentro de cada item."""
    out = []
    if isinstance(o, list):
        if o and isinstance(o[0], dict) and chave in o[0]: out.append(o)
        for v in o: out += listas(v, chave)
    elif isinstance(o, dict):
        for v in o.values(): out += listas(v, chave)
    return out

# projetos do site: slug e código
html = (ROOT / 'index.html').read_text(encoding='utf-8')
bloco = html[html.index('const PROJECTS = {'):]
projetos = re.findall(r"\n  '([a-z0-9-]+)':\{ house:'(camara|senado|exec|stf)', type:'[^']*', code:'([^']+)'", bloco)
SIGLA_CAMARA = {'MP': 'MPV'}

saida = {}
for ref, house, code in projetos:
    m = re.match(r'(PL|PEC|PLP|PDL|MP|MPV|PDS|PLS|PRS|PLV)\s+(\d+)/(\d{4})', code)
    if not m or house == 'stf': continue
    sigla, num, ano = m.group(1), m.group(2), m.group(3)
    vots = []
    # ---------- Câmara ----------
    js = get('https://dadosabertos.camara.leg.br/api/v2/proposicoes?' + urllib.parse.urlencode({'siglaTipo': SIGLA_CAMARA.get(sigla, sigla), 'numero': num, 'ano': ano}), 'camara-proposicoes')
    pid = (js or {}).get('dados', [{}])[0].get('id') if (js or {}).get('dados') else None
    if pid:
        vs = (get(f'https://dadosabertos.camara.leg.br/api/v2/proposicoes/{pid}/votacoes', 'camara-votacoes') or {}).get('dados', [])
        for v in vs:
            votos = (get(f"https://dadosabertos.camara.leg.br/api/v2/votacoes/{v['id']}/votos", 'camara-votos') or {}).get('dados', [])
            if not votos: continue   # votação simbólica: sem voto individual
            vots.append({'casa': 'camara', 'id': v['id'], 'data': (v.get('dataHoraRegistro') or v.get('data') or '')[:16],
                         'descricao': (v.get('descricao') or '')[:240], 'orgao': v.get('siglaOrgao'),
                         'fonte': f"https://www.camara.leg.br/presenca-comissoes/votacao-portal?reuniao=&itemVotacao={v['id']}",
                         'votos': {slug(x['deputado_']['nome']): [x['deputado_']['nome'], x['deputado_'].get('siglaPartido'), x.get('tipoVoto')] for x in votos if x.get('deputado_')}})
    # ---------- Senado ----------
    proc = get('https://legis.senado.leg.br/dadosabertos/processo?' + urllib.parse.urlencode({'sigla': SIGLA_CAMARA.get(sigla, sigla), 'numero': num, 'ano': ano}), 'senado-processo')
    cod = None
    for p in (proc if isinstance(proc, list) else []):
        if norm(p.get('identificacao', '')).split(' ')[-1:] == [f'{num}/{ano}']:
            cod = p.get('codigoMateria'); break
    if cod:
        sv = get(f'https://legis.senado.leg.br/dadosabertos/votacao?codigoMateria={cod}', 'senado-votacao')
        for vot in (sv if isinstance(sv, list) else listas(sv, 'votos') and [sv] or []):
            lista_votos = vot.get('votos') if isinstance(vot, dict) else None
            if not lista_votos: continue
            vv = {}
            for x in lista_votos:
                nome = achar(x, 'nomeParlamentar', 'NomeParlamentar')
                voto = achar(x, 'siglaVotoParlamentar', 'descricaoVotoParlamentar', 'SiglaVoto', 'voto')
                if nome: vv[slug(nome)] = [nome, achar(x, 'siglaPartidoParlamentar', 'SiglaPartidoParlamentar'), voto]
            if vv:
                vots.append({'casa': 'senado', 'id': achar(vot, 'codigoSessaoVotacao', 'codigoVotacao', 'id'),
                             'data': str(achar(vot, 'dataSessao', 'dataHoraInicio', 'data') or '')[:16],
                             'descricao': str(achar(vot, 'descricaoVotacao', 'descricao') or '')[:240],
                             'fonte': f'https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod}', 'votos': vv})
    if vots: saida[ref] = sorted(vots, key=lambda x: x['data'])

OUT.mkdir(exist_ok=True)
(OUT / 'votos.json').write_text(json.dumps({'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'projetos': saida, 'erros': log[:40]},
                                           ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'votos-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:40000], encoding='utf-8')
print(json.dumps({'projetos_com_votos': len(saida), 'votacoes': sum(len(v) for v in saida.values()), 'erros': log[:6]}, ensure_ascii=False))
