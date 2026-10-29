"""Busca nas APIs de dados abertos da Câmara e do Senado as sessões do plenário
de hoje e dos próximos dias e grava data/live.json, que o site lê ao abrir.

Roda de hora em hora pelo GitHub Actions (.github/workflows/atualizar.yml).
Só usa a biblioteca padrão do Python."""
import json, urllib.request, datetime, zoneinfo, pathlib, re, sys

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
AGORA = datetime.datetime.now(BR)
HOJE = AGORA.date()
FIM = HOJE + datetime.timedelta(days=14)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
UA = {'Accept': 'application/json', 'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
log = []

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8'))

def iso(dt):
    return dt.isoformat(timespec='minutes') if dt else None

def parse_dt(s):
    if not s: return None
    s = s.strip().replace('Z', '+00:00')
    for f in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
        try:
            d = datetime.datetime.strptime(s, f)
            return d if d.tzinfo else d.replace(tzinfo=BR)
        except ValueError:
            pass
    return None

# ---------- Câmara: eventos do órgão Plenário (id 180) ----------
def camara():
    url = ('https://dadosabertos.camara.leg.br/api/v2/eventos?idOrgao=180'
           f'&dataInicio={HOJE - datetime.timedelta(days=1)}&dataFim={FIM}&ordem=ASC&ordenarPor=dataHoraInicio&itens=100')
    dados = get(url).get('dados', [])
    out = []
    for e in dados:
        ini, fim = parse_dt(e.get('dataHoraInicio')), parse_dt(e.get('dataHoraFim'))
        sit = (e.get('situacao') or '').strip()
        out.append({
            'id': e.get('id'), 'inicio': iso(ini), 'fim': iso(fim), 'situacao': sit,
            'tipo': e.get('descricaoTipo') or '', 'descricao': (e.get('descricao') or '').strip()[:300],
            'video': e.get('urlRegistro') or None,
            'aoVivo': bool(re.search(r'andamento', sit, re.I)),
        })
    return out

# ---------- Senado: agenda do plenário dia a dia ----------
def find_list(obj, key):
    """Procura recursivamente a lista de objetos com a chave `key` (o formato do Senado varia)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == key.lower():
                return v if isinstance(v, list) else [v]
            r = find_list(v, key)
            if r: return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_list(v, key)
            if r: return r
    return []

def senado():
    out = []
    d = HOJE
    while d <= HOJE + datetime.timedelta(days=7):
        url = f'https://legis.senado.leg.br/dadosabertos/plenario/agenda/dia/{d:%Y%m%d}.json'
        try:
            js = get(url)
        except Exception as ex:
            log.append(f'senado {d}: {ex}')
            d += datetime.timedelta(days=1); continue
        if d == HOJE:
            (OUT / 'debug-senado.json').write_text(json.dumps(js, ensure_ascii=False, indent=1)[:20000], encoding='utf-8')
        for s in find_list(js, 'Sessao'):
            if not isinstance(s, dict): continue
            data = s.get('DataSessao') or s.get('Data') or str(d)
            hora = s.get('HoraInicioSessao') or s.get('HoraInicio') or s.get('Hora') or ''
            ini = parse_dt(f'{data}T{hora[:5]}') if hora else None
            sit = s.get('SituacaoSessao') or s.get('Situacao') or ''
            if isinstance(sit, dict): sit = sit.get('Descricao') or sit.get('DescricaoSituacao') or ''
            tipo = s.get('TipoSessao') or s.get('DescricaoTipoSessao') or ''
            if isinstance(tipo, dict): tipo = tipo.get('Descricao') or ''
            out.append({
                'id': s.get('CodigoSessao'), 'inicio': iso(ini) or str(data), 'fim': None, 'situacao': str(sit),
                'tipo': str(tipo), 'descricao': str(s.get('NomeSessao') or s.get('DescricaoSessao') or '')[:300],
                'video': None, 'aoVivo': bool(re.search(r'andamento|aberta|iniciada', str(sit), re.I)),
            })
        d += datetime.timedelta(days=1)
    return out

result = {'atualizado': iso(AGORA), 'camara': None, 'senado': None, 'erros': log}
for nome, fn in (('camara', camara), ('senado', senado)):
    try:
        result[nome] = fn()
    except Exception as ex:
        log.append(f'{nome}: {ex}')

OUT.mkdir(exist_ok=True)
(OUT / 'live.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}, ensure_ascii=False))
