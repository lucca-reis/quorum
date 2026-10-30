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
            log.append(f'{path} {q}: HTTP {ex.code}'); return None
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
pessoas = [{'n': n, 'cargo': c} for n, c in re.findall(r"\{n:'([^']+)', role:'(Presidente da República|Vice-presidente)'", html)]
bloco = html[html.index('const EXEC_MIN = ['):]
bloco = bloco[:bloco.index('];')]
pessoas += [{'n': n, 'cargo': 'Ministro(a): ' + pasta} for pasta, n in re.findall(r"\['([^']+)','([^']+)'", bloco)]

# ---------- órgão da Presidência (para o cartão de pagamento) ----------
orgaos = paginas('orgaos-siafi', 5, descricao='Presidência da República') or []
cands = [o for o in orgaos if 'PRESIDENCIA DA REPUBLICA' in norm(o.get('descricao') or o.get('nome'))]
orgao = None
for o in cands:
    cod = o.get('codigo') or o.get('codigoSIAFI')
    teste = get('cartoes', mesExtratoInicio=HOJE.strftime('%m/%Y'), mesExtratoFim=HOJE.strftime('%m/%Y'), codigoOrgao=cod, pagina=1)
    if teste is None: continue
    orgao = {'codigo': cod, 'nome': o.get('descricao') or o.get('nome')}
    if teste: break

cartao = None
if orgao:
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
                          'e': (dig(x, 'estabelecimento', 'nome') or dig(x, 'estabelecimento', 'razaoSocialReceita') or 'Sigiloso ou não informado')[:80],
                          't': dig(x, 'tipoCartao', 'descricao') or '',
                          'ug': (dig(x, 'unidadeGestora', 'nome') or '')[:80]})
    itens.sort(key=lambda i: i['d'], reverse=True)
    por_mes = {m.strftime('%Y-%m'): 0.0 for m in MESES}
    for i in itens: por_mes[i['m']] = por_mes.get(i['m'], 0) + i['v']
    cartao = {'orgao': orgao, 'total': round(sum(i['v'] for i in itens), 2), 'transacoes': len(itens),
              'meses': [[m, round(v, 2)] for m, v in por_mes.items()], 'itens': itens[:400],
              'fonte': 'https://portaldatransparencia.gov.br/cartoes'}

# ---------- remuneração de cada pessoa (quando ela aparece no cadastro de servidores e agentes) ----------
remun = {}
for p in pessoas:
    achados = get('servidores', nome=p['n'], pagina=1) or []
    alvo = None
    for a in achados:
        nome = dig(a, 'servidor', 'pessoa', 'nome') or dig(a, 'pessoa', 'nome') or a.get('nome')
        if norm(nome) == norm(p['n']) or norm(p['n']) in norm(nome):
            alvo = a; break
    if not alvo:
        remun[slug(p['n'])] = {'n': p['n'], 'cargo': p['cargo'], 'meses': [], 'achado': False}
        continue
    sid = dig(alvo, 'servidor', 'id') or alvo.get('id') or dig(alvo, 'servidor', 'idServidorAposentadoPensionista')
    meses = []
    for m in MESES[-6:]:
        js = get('servidores/remuneracao', id=sid, mesAno=m.strftime('%Y%m'), pagina=1) or []
        for r in js:
            for dto in (r.get('remuneracoesDTO') or [r]):
                bruto = valor(dto.get('remuneracaoBasicaBruta') or dto.get('valorTotalRemuneracaoAposDeducoes'))
                liq = valor(dto.get('valorTotalRemuneracaoAposDeducoes'))
                if bruto or liq: meses.append([m.strftime('%Y-%m'), round(bruto, 2), round(liq, 2)])
    remun[slug(p['n'])] = {'n': p['n'], 'cargo': p['cargo'], 'meses': meses, 'achado': True,
                           'fonte': 'https://portaldatransparencia.gov.br/servidores'}

OUT.mkdir(parents=True, exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'periodo': [MESES[0].isoformat(), HOJE.isoformat()],
       'cartao': cartao, 'pessoas': remun, 'chamadas': chamadas, 'erros': log[:50]}
(OUT / 'exec.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'exec-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:60000], encoding='utf-8')
print(json.dumps({'orgao': orgao, 'cartao': cartao and cartao['transacoes'], 'achados': sum(r['achado'] for r in remun.values()),
                  'com_remuneracao': sum(bool(r['meses']) for r in remun.values()), 'chamadas': chamadas, 'erros': log[:10]}, ensure_ascii=False))
