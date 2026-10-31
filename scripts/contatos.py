"""Contatos oficiais e redes sociais de deputados, senadores, presidente e vice, para o cartão "Contato" dos perfis.

Fontes (todas oficiais):
  - Câmara (dados abertos): /deputados e /deputados/{id} → e-mail, telefone e endereço do gabinete, redes sociais cadastradas
  - Senado (dados abertos): /senador/lista/atual → e-mail, telefones e página; a página de perfil no site do Senado
    lista as redes sociais do senador (lida quando o site responde)
  - TSE (dados abertos, arquivos de candidatos de 2026 e 2022): sites e redes sociais que cada eleito declarou na candidatura;
    cobre quem toma posse em 2027 e ainda não está no cargo, e os senadores eleitos em 2022
Grava data/contatos.json, com uma entrada por pessoa, indexada pelo nome (vários nomes da mesma pessoa apontam para ela).
Também grava data/contatos-amostra.json com exemplos das respostas, para conferir o formato. Só usa a biblioteca padrão."""
import json, re, io, csv, time, zipfile, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse, traceback
from concurrent.futures import ThreadPoolExecutor

BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
OUT = pathlib.Path(__file__).resolve().parent.parent / 'data'
UA = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (compatible; quorum; +https://github.com/lucca-reis/quorum)'}
log, amostra = [], {}
UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()

def get(url, chave=None, texto=False, timeout=30, tentativas=3):
    for t in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                raw = r.read().decode('utf-8', 'replace')
            js = raw if texto else json.loads(raw or 'null')
            if chave and chave not in amostra:
                amostra[chave] = {'url': url, 'resposta': (raw[:3000] if texto else js)}
            return js
        except urllib.error.HTTPError as ex:
            if ex.code in (403, 404) or t == tentativas-1: log.append(f'{url}: {ex}'); return None
        except Exception as ex:
            if t == tentativas-1: log.append(f'{url}: {ex}'); return None
        time.sleep(2 + 3*t)   # a API da Câmara às vezes devolve 504; tenta de novo

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
                # o TSE marca campo vazio como #NULO# ou #NE#; nomes assim juntariam pessoas diferentes
                if n and not str(n).startswith('#') and len(slug(n)) > 3 and n not in e['nomes']: e['nomes'].append(n)
        elif k in ('emails', 'tels'):
            for x in v:
                x = str(x).strip()
                if x and x.lower() not in [y.lower() for y in e[k]]: e[k].append(x)
        elif k == 'fontes':
            for f in v:
                if f not in e['fontes']: e['fontes'].append(f)
        elif k == 'links':
            # guarda todas as contas de cada rede; no fim fica a que tem o nome da pessoa (campanhas declaram também perfis de comitê)
            for u in v:
                r = rede(u)
                if r: e.setdefault('cands', {}).setdefault(r[0], []).append({'u': r[1], 'h': r[2]})
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
            links = [u for u in (urls_em(html) if html else []) if rede(u)]
            entrada(f'senado-{cod}', casa='senado', cargo='Senador(a)', nomes=[ide.get('NomeParlamentar'), ide.get('NomeCompletoParlamentar')],
                    emails=[ide.get('EmailParlamentar')], tels=[f'(61) {n}' if n and not str(n).startswith('(') else n for n in nums],
                    gabinete='Senado Federal, Brasília (DF)', pagina=ide.get('UrlPaginaParlamentar') or f'https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}',
                    links=links, fontes=[{'l': 'Senado Federal · dados abertos', 'u': 'https://legis.senado.leg.br/dadosabertos/senador/lista/atual'}]
                    + ([{'l': 'Senado Federal · página do senador', 'u': f'https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}'}] if links else []))
    log.append(f'senado: {len(lista)} senadores')

# ---------- TSE: eleitos em 2026 e senadores eleitos em 2022 (sites e redes declarados na candidatura) ----------
# Os arquivos de dados abertos do TSE (cdn.tse.jus.br) trazem os candidatos e, à parte, as redes sociais de cada um.
CDN = 'https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/'
def zip_csv(url):
    """Linhas do CSV nacional (ou de todos os estados) dentro de um zip do TSE."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
    except Exception as ex:
        log.append(f'{url}: {ex}'); return []
    nomes = [n for n in z.namelist() if n.lower().endswith('.csv')]
    br = [n for n in nomes if 'brasil' in n.lower()]
    linhas = []
    for n in (br or nomes):
        with z.open(n) as f:
            linhas += list(csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'))
    return linhas

def tse():
    CARGO = {'PRESIDENTE': 'Presidente da República', 'VICE-PRESIDENTE': 'Vice-presidente', 'SENADOR': 'Senador(a)', 'DEPUTADO FEDERAL': 'Deputado(a) federal'}
    for ano, cargos in ((2026, set(CARGO)), (2022, {'SENADOR'})):
        cands = zip_csv(f'{CDN}consulta_cand_{ano}.zip')
        eleitos = {}
        for c in cands:
            cargo, sit = norm(c.get('DS_CARGO', '')).upper(), norm(c.get('DS_SIT_TOT_TURNO', '')).upper()
            if cargo in cargos and 'ELEITO' in sit and 'NAO ELEITO' not in sit:
                eleitos[c.get('SQ_CANDIDATO')] = c
        if cands and 'tse-cand' not in amostra: amostra['tse-cand'] = {'ano': ano, 'colunas': list(cands[0].keys())}
        redes = {}
        for r in zip_csv(f'{CDN}rede_social_candidato_{ano}.zip'):
            if r.get('SQ_CANDIDATO') in eleitos: redes.setdefault(r['SQ_CANDIDATO'], []).append(r.get('DS_URL', ''))
        for sq, c in eleitos.items():
            entrada(f'tse-{ano}-{sq}', nomes=[c.get('NM_URNA_CANDIDATO'), c.get('NM_CANDIDATO'), c.get('NM_SOCIAL_CANDIDATO')],
                    links=redes.get(sq, []),
                    fontes=[{'l': f'TSE · dados abertos (candidaturas {ano})', 'u': f'https://dadosabertos.tse.jus.br/dataset/candidatos-{ano}'}] if redes.get(sq) else [])
        log.append(f'tse {ano}: {len(cands)} candidaturas, {len(eleitos)} eleitos, {len(redes)} com redes')

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
        for r, v in e.get('cands', {}).items(): f.setdefault('cands', {}).setdefault(r, []).extend(v)
        for k, v in e.items():
            if k not in f or f[k] in (None, '', []): f[k] = v
    for k in chaves: por_nome.setdefault(k, alvo)

def melhor(nomes, contas):
    partes = {p for n in nomes for p in slug(n).split('-') if len(p) >= 4}
    junto = {slug(n).replace('-', '') for n in nomes}
    def nota(c):
        # quanto do nome da conta é o nome da pessoa ("oficial" conta como nome): "lulaoficial" ganha de "lulaverso"
        h = norm(c['h']).lower().replace('_', '').replace('.', '')
        if not h: return (0, 0)
        casado = sum(len(p) for p in partes if p in h) + (7 if 'oficial' in h else 0)
        return (min(casado, len(h)) / len(h) + (1 if any(j and j in h for j in junto) else 0), -len(h))
    return max(contas, key=nota) if contas else None
for f in final.values():
    for r, contas in f.pop('cands', {}).items():
        f['redes'][r] = melhor(f['nomes'], contas)

OUT.mkdir(exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'), 'pessoas': final, 'nomes': por_nome, 'erros': log[:60]}
(OUT / 'contatos.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'contatos-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:60000], encoding='utf-8')
print(json.dumps({'pessoas': len(final), 'com_x': sum('x' in p['redes'] for p in final.values()),
                  'com_instagram': sum('instagram' in p['redes'] for p in final.values()), 'erros': log[:12]}, ensure_ascii=False))
