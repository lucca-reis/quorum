"""Lê as consultas públicas abertas no portal e-Cidadania do Senado (votos SIM e NÃO de cada
proposição) e junta a data de apresentação e o apelido de cada uma, vindos da API de dados
abertos do Senado. Grava data/consultas.json, que a página #consultas do site lê ao abrir.

Roda de hora em hora pelo GitHub Actions (.github/workflows/atualizar.yml), depois de atualizar.py.
O voto acontece só no site oficial; aqui só lemos os números públicos.
Só usa a biblioteca padrão do Python."""
import json, urllib.request, datetime, zoneinfo, pathlib, re, html, time, sys

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
AGORA = datetime.datetime.now(BR)
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
ARQ = OUT / 'consultas.json'
BASE = 'https://www12.senado.leg.br/ecidadania/'
API = 'https://legis.senado.leg.br/dadosabertos/processo?tramitando=S'
UA = {'User-Agent': 'quorum (github.com/lucca-reis/quorum)'}
log = []

def baixar(url, accept='text/html', tentativas=3):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={**UA, 'Accept': accept})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as ex:
            if n == tentativas - 1: raise
            time.sleep(3 * (n + 1))

def numero(t):
    t = re.sub(r'\D', '', t or '')
    return int(t) if t else 0

def texto(t):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t or ''))).strip()

def curto(t, n=260):
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0].rstrip(',;:') + '…'

# ---------- lista de proposições abertas (cerca de 100 por página) ----------
def pagina(p):
    s = baixar(f'{BASE}pesquisamateria?p={p}')
    itens = []
    for bloco in s.split('<div class="resumo-materia">')[1:]:
        bloco = bloco.split('pagination-bar')[0]
        m = re.search(r'<header>\s*<a href="visualizacaomateria\?id=(\d+)"[^>]*>(.*?)</a>', bloco, re.S)
        if not m: continue
        ementa = re.search(r'<section><a [^>]*>(.*?)</a></section>', bloco, re.S)
        nums = re.search(r'<figure class="grafico-consulta-publica">\s*<header>\s*<span>([\d.]*)</span>\s*<span>([\d.]*)</span>', bloco, re.S)
        itens.append({'i': int(m.group(1)), 's': texto(m.group(2)), 'e': curto(texto(ementa.group(1) if ementa else '')),
                      'y': numero(nums.group(1)) if nums else 0, 'n': numero(nums.group(2)) if nums else 0})
    ult = re.search(r'title="último" href="[^"]*[?&]p=(\d+)', s)
    return itens, int(ult.group(1)) if ult else p

def resumo():
    """Totais gerais que o portal mostra na página principal da consulta pública."""
    s = texto(baixar(f'{BASE}principalmateria'))
    out = {}
    for chave, rot in (('proposicoes', 'proposições receberam votos'), ('pessoas', 'pessoas votaram'), ('votos', 'votos registrados')):
        m = re.search(r'([\d.]+)\s+' + rot, s)
        if m: out[chave] = numero(m.group(1))
    return out

anterior = {}
try:
    velho = json.loads(ARQ.read_text(encoding='utf-8'))
    anterior = {x['i']: x for x in velho.get('itens', [])}
except Exception:
    velho = {}

itens, ultima, p = [], 1, 1
while p <= ultima and p <= 300:
    try:
        lote, ult = pagina(p)
        itens += lote
        ultima = max(ultima, ult)
    except Exception as ex:
        log.append(f'página {p}: {ex}')
    p += 1
    time.sleep(0.8)

vistos = set()
itens = [x for x in itens if not (x['i'] in vistos or vistos.add(x['i']))]

# a lista veio pela metade? então mantém o arquivo anterior e só registra o erro
if len(itens) < 0.5 * len(anterior):
    print(f'Lista incompleta ({len(itens)} de {len(anterior)}); arquivo anterior mantido.', log)
    sys.exit(0)

# ---------- data de apresentação, apelido e autoria (API de dados abertos) ----------
info = {}
try:
    for x in json.loads(baixar(API, 'application/json')):
        info[x.get('codigoMateria')] = x
except Exception as ex:
    log.append(f'api processos: {ex}')

for x in itens:
    a, old = info.get(x['i']), anterior.get(x['i'], {})
    if a:
        x['d'] = (a.get('dataApresentacao') or '')[:10] or None
        x['a'] = (a.get('apelido') or '').strip() or None
        x['au'] = curto((a.get('autoria') or '').strip(), 120) or None
        x['st'] = (a.get('situacaoAtual') or '').strip().capitalize() or None
    else:
        for k in ('d', 'a', 'au', 'st'):
            if old.get(k): x[k] = old[k]
    # votos ganhos desde a última leitura (mais ou menos uma hora)
    if old: x['h'] = max(0, (x['y'] + x['n']) - (old.get('y', 0) + old.get('n', 0)))
    for k in [k for k, v in x.items() if v is None]: del x[k]

result = {'atualizado': AGORA.isoformat(timespec='minutes'), 'anterior': velho.get('atualizado'),
          'fonte': BASE + 'pesquisamateria', 'total': len(itens), 'resumo': {}, 'itens': itens, 'erros': log}
try:
    result['resumo'] = resumo()
except Exception as ex:
    log.append(f'resumo: {ex}')

OUT.mkdir(exist_ok=True)
ARQ.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'total': len(itens), 'paginas': ultima, 'com_data': sum('d' in x for x in itens), 'resumo': result['resumo'], 'erros': log}, ensure_ascii=False))
