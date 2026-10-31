"""Contatos oficiais e redes sociais de deputados, senadores, presidente e vice, para o cartão "Contato" dos perfis.

Fontes (todas oficiais):
  - Câmara (dados abertos): /deputados e /deputados/{id} → e-mail, telefone e endereço do gabinete, redes sociais cadastradas
  - Senado (dados abertos): /senador/lista/atual → e-mail, telefones e página; a página de perfil no site do Senado
    lista as redes sociais do senador (lida quando o site responde)
  - TSE (DivulgaCandContas, eleição de 2026): sites e redes sociais que cada candidato eleito declarou na candidatura;
    cobre quem toma posse em 2027 e ainda não está no cargo
Grava data/contatos.json, com uma entrada por pessoa, indexada pelo nome (vários nomes da mesma pessoa apontam para ela).
Também grava data/contatos-amostra.json com exemplos das respostas, para conferir o formato. Só usa a biblioteca padrão."""
import json, re, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse, traceback
from concurrent.futures import ThreadPoolExecutor

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
UA = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (compatible; quorum; +https://github.com/lucca-reis/quorum)'}
log, amostra = [], {}
UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()

def get(url, chave=None, texto=False, timeout=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
        js = raw if texto else json.loads(raw or 'null')
        if chave and chave not in amostra:
            amostra[chave] = {'url': url, 'resposta': (raw[:3000] if texto else js)}
        return js
    except Exception as ex:
        log.append(f'{url}: {ex}'); return None

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return ''.join(c for c in t if not unicodedata.combining(c))

def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', norm(t).lower()).strip('-')

def achar(o, *nomes):
    """Primeiro valor de uma das chaves, procurando em qualquer nível."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in nomes and v not in (None, '', [], {}): return v
        for v in o.values():
            r = achar(v, *nomes)
            if r not in (None, '', [], {}): return r
    elif isinstance(o, list):
        for v in o:
            r = achar(v, *nomes)
            if r not in (None, '', [], {}): return r
    return None

def urls_em(o):
    """Todos os endereços web dentro de uma resposta."""
    return re.findall(r'https?://[^\s"\'<>\\]+', json.dumps(o, ensure_ascii=False) if not isinstance(o, str) else o)

REDES = [('x', r'(?:twitter|x)\.com'), ('instagram', r'instagram\.com'), ('facebook', r'facebook\.com|fb\.com'),
         ('youtube', r'youtube\.com|youtu\.be'), ('tiktok', r'tiktok\.com'), ('threads', r'threads\.(?:net|com)'), ('bluesky', r'bsky\.app')]
NAO_PERFIL = {'share', 'sharer', 'intent', 'home', 'hashtag', 'search', 'p', 'reel', 'watch', 'plugins', 'dialog', 'tr', 'login', 'senadofederal',
              'camaradeputados', 'agenciasenado', 'user', 'channel', 'c', 'pages', 'groups', 'profile.php', 'tvsenado', 'radiosenado', 'tvcamara', 'camaradosdeputados', 'senadofederaloficial', 'tsejus', 'tse'}

def rede(url):
    """('instagram', 'https://instagram.com/fulano', 'fulano') para um link de rede social; None se não for um perfil."""
    u = url.strip().rstrip('/.,;)')
    if not re.match(r'https?://', u): u = 'https://' + u.lstrip('/')
    for k, dom in REDES:
        m = re.match(r'https?://(?:[a-z]+\.)?(?:' + dom + r')/(?:#!/)?(@?[A-Za-z0-9_.\-]+)', u, re.I)
        if m:
            h = m.group(1).lstrip('@')
            if h.lower() in NAO_PERFIL or len(h) < 2: return None
            base = {'x': 'https://x.com/', 'instagram': 'https://www.instagram.com/', 'tiktok': 'https://www.tiktok.com/@', 'threads': 'https://www.threads.net/@'}.get(k)
            return (k, (base + h) if base else u.split('?')[0], h)
    return None

pessoas = {}   # id → entrada
indice = {}    # slug do nome → id

def entrada(pid, **campos):
    e = pessoas.setdefault(pid, {'nomes': [], 'emails': [], 'tels': [], 'redes': {}, 'fontes': []})
    for k, v in campos.items():
        if v in (None, '', []): continue
        if k == 'nomes':
            for n in v:
                if n and n not in e['nomes']: e['nomes'].append(n)
        elif k in ('emails', 'tels'):
            for x in v:
                x = str(x).strip()
                if x and x.lower() not in [y.lower() for y in e[k]]: e[k].append(x)
        elif k == 'fontes':
            for f in v:
                if f not in e['fontes']: e['fontes'].append(f)
        elif k == 'links':
            for u in v:
                r = rede(u)
                if r and r[0] not in e['redes']: e['redes'][r[0]] = {'u': r[1], 'h': r[2]}
        elif not e.get(k):
            e[k] = v
    return e

# ---------- Câmara: deputados em exercício ----------
def camara():
    lista = get('https://dadosabertos.camara.leg.br/api/v2/deputados?itens=1000&ordem=ASC&ordenarPor=nome', 'camara-lista') or {}
    deps = lista.get('dados') or []
    def um(d):
        det = (get(f"https://dadosabertos.camara.leg.br/api/v2/deputados/{d['id']}", 'camara-deputado') or {}).get('dados') or {}
        st, gab = det.get('ultimoStatus') or {}, (det.get('ultimoStatus') or {}).get('gabinete') or {}
        return d, det, st, gab
    with ThreadPoolExecutor(max_workers=6) as ex:
        for d, det, st, gab in ex.map(um, deps):
            pid = f"camara-{d['id']}"
            end = ', '.join(x for x in [f"Gabinete {gab.get('sala')}" if gab.get('sala') else '', f"Anexo {gab.get('predio')}" if gab.get('predio') else '',
                                        f"{gab.get('andar')}º andar" if gab.get('andar') else ''] if x)
            tel = gab.get('telefone')
            entrada(pid, casa='camara', cargo='Deputado(a) federal', nomes=[d.get('nome'), st.get('nomeEleitoral'), st.get('nome'), det.get('nomeCivil')],
                    emails=[st.get('email') or d.get('email') or gab.get('email')], tels=[f'(61) {tel}' if tel and not tel.startswith('(') else tel],
                    gabinete=(end + ', Câmara dos Deputados, Brasília (DF)') if end else None,
                    pagina=f"https://www.camara.leg.br/deputados/{d['id']}", links=(det.get('redeSocial') or []) + ([det['urlWebsite']] if det.get('urlWebsite') else []),
                    fontes=[{'l': 'Câmara dos Deputados · dados abertos', 'u': f"https://dadosabertos.camara.leg.br/api/v2/deputados/{d['id']}"}])
    log.append(f'câmara: {len(deps)} deputados')

# ---------- Senado: senadores em exercício ----------
def senado():
    js = get('https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json', 'senado-lista') or {}
    lista = achar(js, 'Parlamentar') or []
    if isinstance(lista, dict): lista = [lista]
    def um(p):
        ide = p.get('IdentificacaoParlamentar') or p
        cod = ide.get('CodigoParlamentar')
        html = get(f'https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}', 'senado-perfil', texto=True, timeout=20) if cod else None
        return p, ide, cod, html
    with ThreadPoolExecutor(max_workers=4) as ex:
        for p, ide, cod, html in ex.map(um, lista):
            tels = achar(p, 'Telefone') or []
            if isinstance(tels, dict): tels = [tels]
            nums = [t.get('NumeroTelefone') for t in tels if isinstance(t, dict) and t.get('NumeroTelefone')]
            links = urls_em(html) if html else []
            entrada(f'senado-{cod}', casa='senado', cargo='Senador(a)', nomes=[ide.get('NomeParlamentar'), ide.get('NomeCompletoParlamentar')],
                    emails=[ide.get('EmailParlamentar')], tels=[f'(61) {n}' if n and not str(n).startswith('(') else n for n in nums],
                    gabinete='Senado Federal, Brasília (DF)', pagina=ide.get('UrlPaginaParlamentar') or f'https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}',
                    links=links, fontes=[{'l': 'Senado Federal · dados abertos', 'u': 'https://legis.senado.leg.br/dadosabertos/senador/lista/atual'}]
                    + ([{'l': 'Senado Federal · página do senador', 'u': f'https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}'}] if links else []))
    log.append(f'senado: {len(lista)} senadores')

# ---------- TSE: eleitos em 2026 (sites e redes declarados na candidatura) ----------
TSE = 'https://divulgacandcontas.tse.jus.br/divulga/rest/v1/'
def tse():
    ords = get(TSE + 'eleicao/ordinarias', 'tse-eleicoes') or []
    if isinstance(ords, dict): ords = achar(ords, 'eleicoes') or []
    ids = [str(e.get('id')) for e in ords if isinstance(e, dict) and str(e.get('ano')) == '2026' and e.get('id')]
    log.append(f'tse: eleições de 2026 {ids}')
    alvos = []   # (uf, eleição, cargo, candidato)
    for el in ids:
        for uf, cargo in [('BR', 1), ('BR', 2)] + [(u, c) for u in UFS for c in (5, 6)]:
            js = get(f'{TSE}candidatura/listar/2026/{uf}/{el}/{cargo}/candidatos', 'tse-lista')
            for c in (js or {}).get('candidatos') or []:
                tot = norm(c.get('descricaoTotalizacao') or '').lower()
                if 'eleito' in tot and 'nao eleito' not in tot:
                    alvos.append((uf, el, cargo, c))
            time.sleep(.15)
    def um(a):
        uf, el, cargo, c = a
        return a, get(f"{TSE}candidatura/buscar/2026/{uf}/{el}/candidato/{c['id']}", 'tse-candidato')
    CARGO = {1: 'Presidente da República', 2: 'Vice-presidente', 5: 'Senador(a)', 6: 'Deputado(a) federal'}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for (uf, el, cargo, c), det in ex.map(um, alvos):
            det = det or {}
            sites = det.get('sites') or []
            links = [s.get('url') if isinstance(s, dict) else s for s in sites] if sites else []
            entrada(f"tse-{c['id']}", eleito2026=CARGO.get(cargo), nomes=[c.get('nomeUrna'), c.get('nomeCompleto'), det.get('nomeUrna'), det.get('nomeCompleto')],
                    links=[u for u in links if u],
                    fontes=[{'l': 'TSE · DivulgaCandContas (candidatura 2026)', 'u': f"https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2026/{el}/{uf}/{c['id']}"}])
    log.append(f'tse: {len(alvos)} eleitos')

for etapa in (camara, senado, tse):
    try: etapa()
    except Exception: log.append(f'{etapa.__name__}: ' + traceback.format_exc()[-500:])

# junta pela pessoa: o mesmo nome em fontes diferentes vira uma entrada só (dados da Casa primeiro, redes do TSE completam)
final, por_nome = {}, {}
for pid, e in sorted(pessoas.items(), key=lambda kv: (kv[0].startswith('tse'), kv[0])):
    chaves = {slug(n) for n in e['nomes'] if n}
    alvo = next((por_nome[k] for k in chaves if k in por_nome), None)
    if alvo is None:
        alvo = pid; final[alvo] = {k: v for k, v in e.items()}
    else:
        f = final[alvo]
        for k in ('nomes', 'emails', 'tels', 'fontes'):
            for x in e.get(k, []):
                if x not in f[k]: f[k].append(x)
        for r, v in e['redes'].items(): f['redes'].setdefault(r, v)
        for k, v in e.items():
            if k not in f or f[k] in (None, '', []): f[k] = v
    for k in chaves: por_nome.setdefault(k, alvo)

OUT.mkdir(exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'pessoas': final, 'nomes': por_nome, 'erros': log[:60]}
(OUT / 'contatos.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'contatos-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:60000], encoding='utf-8')
print(json.dumps({'pessoas': len(final), 'com_x': sum('x' in p['redes'] for p in final.values()),
                  'com_instagram': sum('instagram' in p['redes'] for p in final.values()), 'erros': log[:12]}, ensure_ascii=False))
