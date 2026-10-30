"""Gastos da cota parlamentar de deputados e senadores nos últimos 12 meses.

Lê os arquivos oficiais de cada casa:
  - Câmara: https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip  (Cota para o Exercício da Atividade Parlamentar)
  - Senado: https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_AAAA.csv  (CEAPS)
e grava:
  - data/transparencia/resumo.json: totais por casa, por mês e por tipo de gasto, e o total de cada parlamentar
  - data/transparencia/p/<casa>-<nome>.json: os gastos de cada parlamentar, do mais recente ao mais antigo

Roda uma vez por dia pelo GitHub Actions (.github/workflows/transparencia.yml). Só usa a biblioteca padrão.
Os valores são os que as casas publicam; nada é calculado além de somas."""
import csv, io, json, re, zipfile, unicodedata, datetime, zoneinfo, pathlib, urllib.request, sys

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
HOJE = datetime.datetime.now(BR).date()
ANO = HOJE.year
# janela de 12 meses: do primeiro dia do mês, 11 meses atrás, até hoje
_m = HOJE.month - 11
INICIO = datetime.date(ANO + (_m - 1) // 12, (_m - 1) % 12 + 1, 1)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'transparencia'
UA = {'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
log = []

def baixar(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()

def slug(t):
    t = unicodedata.normalize('NFD', t or '')
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')

def num(t):
    t = (t or '').strip()
    if not t: return 0.0
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    try: return float(t)
    except ValueError: return 0.0

# nomes curtos para os tipos de gasto, iguais nas duas casas
CATS = [
    (r'locomo[cç][aã]o, hosped', 'Locomoção e hospedagem'), (r'material', 'Material de escritório'), (r'passage', 'Passagens'), (r'combust', 'Combustível'), (r'divulga', 'Divulgação do mandato'),
    (r'escrit|alugu|im[oó]ve', 'Escritório'), (r'consult|assessor|pesquis|t[eé]cnic', 'Consultorias'),
    (r'loca[cç][aã]o ou fretamento de ve|ve[ií]culo', 'Aluguel de veículos'), (r'aeronave|embarca', 'Fretamento de aeronaves'),
    (r'hosped', 'Hospedagem'), (r'aliment', 'Alimentação'), (r't[aá]xi|ped[aá]gio|estacion|locomo', 'Táxi e deslocamentos'),
    (r'telef', 'Telefone'), (r'postais|correio', 'Correios'), (r'seguran', 'Segurança'),
    (r'curso|palestra|evento', 'Cursos e eventos'), (r'assinatura|publica', 'Assinaturas'),
]
def cat(t):
    t = (t or '').lower()
    for re_, nome in CATS:
        if re.search(re_, t): return nome
    return 'Outros'

def no_periodo(d):
    return d is not None and INICIO <= d <= HOJE

def data_iso(t, fmt):
    try: return datetime.datetime.strptime((t or '')[:10], fmt).date()
    except ValueError: return None

def camara():
    linhas = []
    for ano in sorted({INICIO.year, ANO}):
        try:
            z = zipfile.ZipFile(io.BytesIO(baixar(f'https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip')))
            nome = next(n for n in z.namelist() if n.lower().endswith('.csv'))
            txt = z.read(nome).decode('utf-8-sig', 'replace')
        except Exception as ex:
            log.append(f'câmara {ano}: {ex}'); continue
        for r in csv.DictReader(io.StringIO(txt), delimiter=';'):
            if not (r.get('nuDeputadoId') and r.get('ideCadastro')): continue   # lideranças e órgãos ficam de fora
            d = data_iso(r.get('datEmissao'), '%Y-%m-%d')
            mes = f"{r.get('numAno')}-{int(r.get('numMes') or 0):02d}"
            if d is None or not no_periodo(d):
                # sem data do documento: usa o mês de competência
                try: d = datetime.date(int(r['numAno']), int(r['numMes']), 1)
                except (ValueError, KeyError): continue
                if not no_periodo(d): continue
            linhas.append({'nome': r['txNomeParlamentar'].strip(), 'id': r['ideCadastro'], 'p': r.get('sgPartido', ''), 'uf': r.get('sgUF', ''),
                           'd': d.isoformat(), 'm': mes, 'c': cat(r.get('txtDescricao')), 'f': (r.get('txtFornecedor') or '').strip()[:80],
                           'v': num(r.get('vlrLiquido')),
                           # só o fim do link da nota fiscal; o site completa com https://www.camara.leg.br/cota-parlamentar/documentos/publ/
                           'u': (r.get('urlDocumento') or '').split('/documentos/publ/')[-1].removesuffix('.pdf') if 'documentos/publ/' in (r.get('urlDocumento') or '') else ''})
    return linhas

def senado():
    linhas = []
    for ano in sorted({INICIO.year, ANO}):
        try:
            txt = baixar(f'https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv').decode('latin-1')
        except Exception as ex:
            log.append(f'senado {ano}: {ex}'); continue
        corpo = txt.split('\n', 1)[1] if txt.startswith('"ULTIMA') else txt
        for r in csv.DictReader(io.StringIO(corpo), delimiter=';'):
            d = data_iso(r.get('DATA'), '%d/%m/%Y')
            try: mes = f"{int(r['ANO'])}-{int(r['MES']):02d}"
            except (ValueError, KeyError): continue
            if d is None or not no_periodo(d):
                d = datetime.date(int(mes[:4]), int(mes[5:]), 1)
                if not no_periodo(d): continue
            linhas.append({'nome': r['SENADOR'].strip().title(), 'id': '', 'p': '', 'uf': '',
                           'd': d.isoformat(), 'm': mes, 'c': cat(r.get('TIPO_DESPESA')), 'f': (r.get('FORNECEDOR') or '').strip()[:80],
                           'v': num(r.get('VALOR_REEMBOLSADO')), 'u': ''})
    return linhas

MESES = []
_d = INICIO
while _d <= HOJE:
    MESES.append(f'{_d.year}-{_d.month:02d}')
    _d = datetime.date(_d.year + (_d.month == 12), _d.month % 12 + 1, 1)

def resumir(linhas, casa, fonte):
    total = round(sum(x['v'] for x in linhas), 2)
    por_mes = {m: 0.0 for m in MESES}
    por_cat = {}
    pessoas = {}
    for x in linhas:
        if x['m'] in por_mes: por_mes[x['m']] += x['v']
        por_cat[x['c']] = por_cat.get(x['c'], 0) + x['v']
        k = slug(x['nome'])
        p = pessoas.setdefault(k, {'n': x['nome'], 'p': x['p'], 'uf': x['uf'], 't': 0.0, 'q': 0, 'u': '', 'itens': [], 'cats': {}, 'meses': {m: 0.0 for m in MESES}})
        p['t'] += x['v']; p['q'] += 1; p['u'] = max(p['u'], x['d'])
        p['cats'][x['c']] = p['cats'].get(x['c'], 0) + x['v']
        if x['m'] in p['meses']: p['meses'][x['m']] += x['v']
        p['itens'].append({k2: x[k2] for k2 in ('d', 'c', 'f', 'v', 'u') if x[k2] != ''})
    pasta = OUT / 'p'
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = set()
    for k, p in pessoas.items():
        p['itens'].sort(key=lambda i: i['d'], reverse=True)
        arq = {'n': p['n'], 'casa': casa, 'periodo': [INICIO.isoformat(), HOJE.isoformat()], 'total': round(p['t'], 2),
               'meses': [[m, round(v, 2)] for m, v in p['meses'].items()],
               'cats': sorted([[c, round(v, 2)] for c, v in p['cats'].items()], key=lambda c: -c[1]),
               'itens': [{**i, 'v': round(i['v'], 2)} for i in p['itens']], 'fonte': fonte}
        nome = f'{casa}-{k}.json'
        (pasta / nome).write_text(json.dumps(arq, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        feitos.add(nome)
    return {'total': total, 'parlamentares': len(pessoas), 'documentos': len(linhas),
            'meses': [[m, round(v, 2)] for m, v in por_mes.items()],
            'cats': sorted([[c, round(v, 2)] for c, v in por_cat.items()], key=lambda c: -c[1]),
            'pessoas': {k: {'n': p['n'], 't': round(p['t'], 2), 'q': p['q'], 'u': p['u']} for k, p in pessoas.items()},
            'fonte': fonte}, feitos

resultado = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'periodo': [INICIO.isoformat(), HOJE.isoformat()], 'erros': log}
anterior = {}
try: anterior = json.loads((OUT / 'resumo.json').read_text(encoding='utf-8'))
except Exception: pass
todos = set()
for casa, fn, fonte in (('camara', camara, 'https://www.camara.leg.br/transparencia/gastos-parlamentares'),
                        ('senado', senado, 'https://www12.senado.leg.br/transparencia/sen/verba-indenizatoria-ceaps')):
    linhas = fn()
    if not linhas:
        # a casa não respondeu hoje: mantém o que já havia
        resultado[casa] = anterior.get(casa)
        todos |= {f.name for f in (OUT / 'p').glob(f'{casa}-*.json')} if (OUT / 'p').exists() else set()
        continue
    resultado[casa], feitos = resumir(linhas, casa, fonte)
    todos |= feitos
# apaga arquivos de quem saiu da janela de 12 meses
if (OUT / 'p').exists():
    for f in (OUT / 'p').glob('*.json'):
        if f.name not in todos: f.unlink()
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'resumo.json').write_text(json.dumps(resultado, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(json.dumps({c: (resultado[c] or {}).get('parlamentares') for c in ('camara', 'senado')} | {'erros': log}, ensure_ascii=False))
