"""Últimas notícias oficiais dos tribunais superiores (STJ, TST, TSE, STM) e dos ministérios.

- Ministérios: o feed RSS de notícias de cada ministério no gov.br (…/pt-br/assuntos/noticias/RSS).
- Tribunais: os sites do TSE, TST e STM bloqueiam acessos automáticos; por isso as notícias de cada tribunal vêm
  do Google Notícias, filtradas pelo próprio site do tribunal (site:tse.jus.br), e o link leva à notícia oficial.

Grava data/instituicoes.json, que as páginas #tribunal-* e #ministerio-* leem. Roda de hora em hora junto com
atualizar.py (.github/workflows/atualizar.yml). Só guarda título, data e link de cada notícia.
Só usa a biblioteca padrão do Python."""
import json, re, html, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse
from email.utils import parsedate_to_datetime

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
AGORA = datetime.datetime.now(BR)
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'instituicoes.json'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; quorum; +https://github.com/lucca-reis/quorum)'}
MAX = 15
log = []

def baixar(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', 'replace')

def slug(t):
    t = unicodedata.normalize('NFD', t or '')
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')

def limpa(t):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t or ''))).strip()

def iso(t):
    t = (t or '').strip()
    try: return parsedate_to_datetime(t).astimezone(BR).isoformat(timespec='minutes')
    except Exception: pass
    try: return datetime.datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(BR).isoformat(timespec='minutes')
    except Exception: return None

def itens_rss(xml, corta=None):
    out = []
    for bloco in re.findall(r'<(?:item|entry)\b.*?</(?:item|entry)>', xml, re.S):
        tit = limpa((re.search(r'<title[^>]*>(.*?)</title>', bloco, re.S) or [None, ''])[1])
        tit = re.sub(r'^<!\[CDATA\[|\]\]>$', '', tit)
        link = (re.search(r'<link>(.*?)</link>', bloco, re.S) or re.search(r'<link[^>]*href="([^"]+)"', bloco) or re.search(r'rdf:about="([^"]+)"', bloco) or [None, ''])[1].strip()
        data = (re.search(r'<(?:pubDate|dc:date|updated|published)>(.*?)</', bloco, re.S) or [None, ''])[1]
        if corta: tit = re.sub(corta, '', tit).strip()
        # sufixos que o Google Notícias acrescenta ao título ("— Ministério da Fazenda - www.gov.br")
        tit = re.sub(r'\s+[-—–]\s+(www\.)?gov\.br$', '', tit, flags=re.I)
        tit = re.sub(r'\s+[—–]\s+(Minist[ée]rio|Secretaria|Advocacia|Controladoria|Gabinete|Casa Civil)[^—–]*$', '', tit).strip()
        if tit and link: out.append({'t': tit[:220], 'u': html.unescape(link), 'd': iso(data)})
    out.sort(key=lambda x: x['d'] or '', reverse=True)
    vistos, unicos = set(), []
    for x in out:
        k = slug(x['t'])
        if k in vistos: continue
        vistos.add(k); unicos.append(x)
    return unicos[:MAX]

# ---------- tribunais superiores ----------
TRIB = {'stj': ('stj.jus.br', 'Superior Tribunal de Justiça'), 'tst': ('tst.jus.br', 'Tribunal Superior do Trabalho'),
        'tse': ('tse.jus.br', 'Tribunal Superior Eleitoral'), 'stm': ('stm.jus.br', 'Superior Tribunal Militar')}
tribunais = {}
for k, (dom, nome) in TRIB.items():
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': f'site:{dom}', 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'})
    try:
        tribunais[k] = {'fonte': f'https://www.{dom}', 'via': 'Google Notícias', 'itens': itens_rss(baixar(url), r'\s+-\s+' + re.escape(nome) + r'.*$|\s+-\s+(STJ|TST|TSE|STM)$')}
    except Exception as ex:
        log.append(f'{k}: {ex}')
    time.sleep(1)

# ---------- ministérios: endereço de cada um no gov.br ----------
GOVBR = {
    'Casa Civil': 'casacivil', 'Relações Institucionais': 'sri', 'Saúde': 'saude', 'Trabalho e Emprego': 'trabalho-e-emprego',
    'Desenvolvimento e Assistência Social': 'mds', 'Mulheres': 'mulheres', 'Secretaria-Geral da Presidência': 'secretariageral',
    'Ciência, Tecnologia e Inovação': 'mcti', 'Empreendedorismo e Microempresa': 'memp', 'Previdência Social': 'previdencia',
    'Agricultura e Pecuária': 'agricultura', 'Minas e Energia': 'mme', 'Fazenda': 'fazenda', 'Planejamento e Orçamento': 'planejamento',
    'Desenvolvimento, Indústria e Comércio': 'mdic', 'Gestão e Inovação': 'gestao', 'Justiça e Segurança Pública': 'mj',
    'Defesa': 'defesa', 'Relações Exteriores': 'mre', 'Educação': 'mec', 'Meio Ambiente': 'mma', 'Desenvolvimento Agrário': 'mda',
    'Pesca e Aquicultura': 'mpa', 'Cidades': 'cidades', 'Transportes': 'transportes', 'Portos e Aeroportos': 'portos-e-aeroportos',
    'Integração e Desenvolvimento Regional': 'mdr', 'Comunicações': 'mcom', 'Cultura': 'cultura', 'Turismo': 'turismo',
    'Esporte': 'esporte', 'Igualdade Racial': 'igualdaderacial', 'Direitos Humanos e Cidadania': 'mdh', 'Povos Indígenas': 'povosindigenas',
    'Comunicação Social (Secom)': 'secom', 'Gabinete de Segurança Institucional': 'gsi', 'Advocacia-Geral da União': 'agu',
    'Controladoria-Geral da União': 'cgu',
}
html_site = (ROOT / 'index.html').read_text(encoding='utf-8')
bloco = html_site[html_site.index('const EXEC_MIN = ['):]
pastas = re.findall(r"\['([^']+)','[^']+'", bloco[:bloco.index('];')])
def um_ministerio(pasta):
    g = GOVBR.get(pasta)
    item = {'pasta': pasta, 'fonte': f'https://www.gov.br/{g}' if g else None, 'itens': []}
    if g:
        for caminho in ('/pt-br/assuntos/noticias/RSS', '/pt-br/assuntos/noticias/noticias/RSS'):
            try:
                it = itens_rss(baixar(f'https://www.gov.br/{g}{caminho}'))
                if it: item['itens'] = it; item['rss'] = f'https://www.gov.br/{g}{caminho}'; break
            except Exception:
                pass
    if not item['itens']:
        # sem feed no gov.br: notícias do próprio site do ministério pelo Google Notícias
        q = f'site:gov.br/{g}' if g else f'"{pasta}" site:gov.br'
        try:
            item['itens'] = itens_rss(baixar('https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q, 'hl': 'pt-BR', 'gl': 'BR', 'ceid': 'BR:pt-419'})), r'\s+-\s+(gov\.br|Gov\.br|Governo Federal).*$')
            item['via'] = 'Google Notícias'
        except Exception as ex:
            log.append(f'{pasta}: {ex}')
    if not item['itens']: log.append(f'sem notícias: {pasta}')
    return slug(pasta), item

# alguns de cada vez, para terminar em poucos minutos sem sobrecarregar os sites
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=5) as ex:
    ministerios = dict(ex.map(um_ministerio, pastas))

res = {'atualizado': AGORA.isoformat(timespec='minutes'), 'tribunais': tribunais, 'ministerios': ministerios, 'erros': log}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'tribunais': {k: len(v['itens']) for k, v in tribunais.items()},
                  'ministerios_com_rss': sum('rss' in v for v in ministerios.values()),
                  'ministerios_com_noticias': sum(bool(v['itens']) for v in ministerios.values()), 'erros': log[:10]}, ensure_ascii=False))
