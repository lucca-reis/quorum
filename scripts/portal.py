"""Dados do Executivo no Portal da Transparência (CGU): cartão de pagamento da Presidência e
remuneração de presidente, vice e ministros, nos últimos 12 meses.

Usa a API oficial (https://api.portaldatransparencia.gov.br/swagger-ui/index.html), que exige uma chave
gratuita. A chave fica no segredo PORTAL_TRANSPARENCIA_KEY do GitHub e nunca vai para o repositório.
Grava data/transparencia/exec.json. Roda uma vez por dia (.github/workflows/transparencia.yml).

A primeira versão também grava amostras das respostas em data/transparencia/exec-amostra.json, para conferir
o formato de cada endpoint (são dados públicos; a chave não aparece nelas)."""
import json, os, re, sys, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse

KEY = os.environ.get('PORTAL_TRANSPARENCIA_KEY', '').strip()
if not KEY:
    print('Sem chave do Portal da Transparência; nada a fazer.'); sys.exit(0)

API = 'https://api.portaldatransparencia.gov.br/api-de-dados/'
BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
HOJE = datetime.datetime.now(BR).date()
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'transparencia'
log, amostra = [], {}
chamadas = 0

def get(path, **q):
    global chamadas
    url = API + path + ('?' + urllib.parse.urlencode(q) if q else '')
    for n in range(3):
        try:
            req = urllib.request.Request(url, headers={'chave-api-dados': KEY, 'Accept': 'application/json',
                                                       'User-Agent': 'quorum (github.com/lucca-reis/quorum)'})
            time.sleep(0.5); chamadas += 1
            with urllib.request.urlopen(req, timeout=60) as r:
                js = json.loads(r.read().decode('utf-8') or 'null')
            if path not in amostra: amostra[path] = {'params': q, 'resposta': js[:2] if isinstance(js, list) else js}
            return js
        except urllib.error.HTTPError as ex:
            if ex.code == 429: time.sleep(30); continue
            corpo = ''
            try: corpo = ex.read().decode('utf-8', 'replace')[:300]
            except Exception: pass
            log.append(f'{path} {q}: HTTP {ex.code} {corpo}'); return None
        except Exception as ex:
            if n == 2: log.append(f'{path} {q}: {ex}'); return None
            time.sleep(5)

def paginas(path, limite=40, **q):
    out = []
    for p in range(1, limite + 1):
        js = get(path, pagina=p, **q)
        if not js: break
        out += js
        if len(js) < 15: break
    return out

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).upper().strip()

def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', norm(t).lower()).strip('-')

def valor(v):
    if isinstance(v, (int, float)): return float(v)
    t = str(v or '').strip()
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    try: return float(t)
    except ValueError: return 0.0

def dig(o, *ks):
    for k in ks:
        if not isinstance(o, dict): return None
        o = o.get(k)
    return o

MESES = []
d = HOJE.replace(day=1)
for _ in range(12):
    MESES.append(d)
    d = (d - datetime.timedelta(days=1)).replace(day=1)
MESES.reverse()

# ---------- quem é quem: presidente, vice e ministros, lidos do próprio site ----------
html = (ROOT / 'index.html').read_text(encoding='utf-8')
topo = html[html.index('const EXEC_TOP = ['):]
topo = topo[:topo.index('];')]
pessoas = [{'n': n, 'cargo': c} for n, c in re.findall(r"\{n:'([^']+)', role:'([^']+)'", topo)]
bloco = html[html.index('const EXEC_MIN = ['):]
bloco = bloco[:bloco.index('];')]
pessoas += [{'n': n, 'cargo': 'Ministro(a): ' + pasta, 'pasta': pasta} for pasta, n in re.findall(r"\['([^']+)','([^']+)'", bloco)]

# ---------- órgãos: Presidência (20101), Vice-Presidência e ministérios ----------
def lista_orgaos(desc):
    return [{'codigo': str(o.get('codigo')), 'nome': o.get('descricao') or o.get('nome') or ''} for o in (paginas('orgaos-siafi', 15, descricao=desc) or [])]
ORG = {o['codigo']: o for o in lista_orgaos('Presidência') + lista_orgaos('Vice-Presidência') + lista_orgaos('Ministério')}
def acha_orgao(chave, *excluir):
    k = norm(chave)
    for o in ORG.values():
        n = norm(o['nome'])
        if k in n and not any(norm(e) in n for e in excluir): return o
    return None
PRES = ORG.get('20101') or acha_orgao('PRESIDENCIA DA REPUBLICA', 'VICE', 'VINCULO')
VICE = acha_orgao('VICE-PRESIDENCIA')
# pasta do site -> órgão SIAFI do ministério (pelo nome; o que não casar fica sem órgão)
STOP = {'E', 'DA', 'DE', 'DO', 'DAS', 'DOS', 'MINISTERIO'}
def orgao_da_pasta(pasta):
    alvo = {w for w in norm(pasta).split() if w not in STOP}
    melhor, nota = None, 0
    for o in ORG.values():
        n = norm(o['nome'])
        if not n.startswith('MINISTERIO'): continue
        ws = {w for w in n.split() if w not in STOP}
        sc = len(alvo & ws) / max(1, len(alvo | ws))
        if sc > nota: melhor, nota = o, sc
    return melhor if nota >= 0.4 else None

def cartao_de(orgao):
    if not orgao: return None
    itens = []
    for m in MESES:
        mm = m.strftime('%m/%Y')
        for x in paginas('cartoes', 60, mesExtratoInicio=mm, mesExtratoFim=mm, codigoOrgao=orgao['codigo']):
            data = str(x.get('dataTransacao') or '')
            iso = None
            for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
                try: iso = datetime.datetime.strptime(data[:10], fmt).date().isoformat(); break
                except ValueError: pass
            itens.append({'d': iso or m.isoformat(), 'm': m.strftime('%Y-%m'), 'v': round(valor(x.get('valorTransacao')), 2),
                          'e': (dig(x, 'estabelecimento', 'nome') or 'Não informado')[:80],
                          'ug': (dig(x, 'unidadeGestora', 'nome') or '')[:80]})
    itens.sort(key=lambda i: i['d'], reverse=True)
    por_mes = {m.strftime('%Y-%m'): 0.0 for m in MESES}
    for i in itens: por_mes[i['m']] = por_mes.get(i['m'], 0) + i['v']
    sig = sum(i['v'] for i in itens if norm(i['e']).startswith('SIGILOS'))
    return {'orgao': orgao, 'total': round(sum(i['v'] for i in itens), 2), 'sigiloso': round(sig, 2), 'transacoes': len(itens),
            'meses': [[m, round(v, 2)] for m, v in por_mes.items()], 'itens': [i for i in itens if 'm' in i][:300],
            'fonte': f"https://portaldatransparencia.gov.br/cartoes/consulta?ordenarPor=dataTransacao&direcao=desc&orgaos={orgao['codigo']}"}

cartoes = {}
if PRES: cartoes['presidencia'] = cartao_de(PRES)
if VICE: cartoes['vice'] = cartao_de(VICE)

# ---------- remuneração: o cadastro de servidores usa os códigos de órgão do SIAPE, não os do SIAFI ----------
SIAPE = {}
for desc in ('Presidência', 'Vice-Presidência', 'Ministério', 'Advocacia-Geral', 'Controladoria-Geral', 'Banco Central', 'Casa Civil', 'Secretaria'):
    for o in paginas('orgaos-siape', 15, descricao=desc) or []:
        SIAPE[str(o.get('codigo'))] = {'codigo': str(o.get('codigo')), 'nome': o.get('descricao') or o.get('nome') or ''}
def siape_de(nome_orgao):
    if not nome_orgao: return []
    alvo = {w for w in norm(nome_orgao).split() if w not in STOP}
    notas = []
    for o in SIAPE.values():
        ws = {w for w in norm(o['nome']).split() if w not in STOP}
        sc = len(alvo & ws) / max(1, len(alvo | ws))
        if sc >= 0.34: notas.append((sc, o))
    return [o for _, o in sorted(notas, key=lambda x: -x[0])[:3]]

remun = {}
for p in pessoas:
    if p['cargo'] == 'Presidente da República': nome_org = 'Presidência da República'
    elif p['cargo'] == 'Vice-presidente': nome_org = 'Vice-Presidência da República'
    else: nome_org = p.get('pasta', '')
    org = None; achados = None
    for o in siape_de(nome_org):
        for campo in ('orgaoServidorExercicio', 'orgaoServidorLotacao'):
            achados = get('servidores', pagina=1, nome=p['n'], **{campo: o['codigo']})
            if achados: org = o; break
        if achados: break
    alvo = None
    for a in achados or []:
        nome = dig(a, 'servidor', 'pessoa', 'nome') or dig(a, 'pessoa', 'nome') or a.get('nome')
        if nome and (norm(nome) == norm(p['n']) or set(norm(p['n']).split()) <= set(norm(nome).split())):
            alvo = a; break
    item = {'n': p['n'], 'cargo': p['cargo'], 'orgao': org, 'meses': [], 'achado': bool(alvo)}
    if alvo:
        sid = dig(alvo, 'servidor', 'id') or alvo.get('id') or dig(alvo, 'servidor', 'idServidorAposentadoPensionista')
        for m in MESES[-6:]:
            for r in get('servidores/remuneracao', id=sid, mesAno=m.strftime('%Y%m'), pagina=1) or []:
                for dto in (r.get('remuneracoesDTO') or [r]):
                    bruto = valor(dto.get('remuneracaoBasicaBruta'))
                    liq = valor(dto.get('valorTotalRemuneracaoAposDeducoes'))
                    if bruto or liq: item['meses'].append([m.strftime('%Y-%m'), round(bruto, 2), round(liq, 2)])
        item['fonte'] = 'https://portaldatransparencia.gov.br/servidores'
    remun[slug(p['n'])] = item

OUT.mkdir(parents=True, exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'periodo': [MESES[0].isoformat(), HOJE.isoformat()],
       'cartoes': cartoes, 'pessoas': remun, 'orgaos': sorted(ORG.values(), key=lambda o: o['codigo']), 'siape': sorted(SIAPE.values(), key=lambda o: o['codigo']), 'chamadas': chamadas, 'erros': log[:60]}
(OUT / 'exec.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'exec-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:60000], encoding='utf-8')
print(json.dumps({'pres': PRES, 'vice': VICE, 'cartoes': {k: v and v['transacoes'] for k, v in cartoes.items()},
                  'achados': sum(r['achado'] for r in remun.values()), 'com_remuneracao': sum(bool(r['meses']) for r in remun.values()),
                  'chamadas': chamadas, 'erros': log[:10]}, ensure_ascii=False))
