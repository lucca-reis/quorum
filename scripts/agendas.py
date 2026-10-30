"""Agenda dos ministros no e-Agendas (CGU): compromissos dos últimos 14 dias e dos próximos 14 dias.

API pública documentada em https://github.com/cgugovbr/eagendas-publico/tree/main/api-consulta
Exige um token pessoal, guardado no segredo EAGENDAS_TOKEN do GitHub (nunca no repositório).
Grava data/agendas.json, que as páginas #ministerio-* leem. Na primeira versão também grava
data/agendas-amostra.json com exemplos das respostas, para conferir o formato (dados públicos, sem o token).
Roda de hora em hora junto com atualizar.py. Só usa a biblioteca padrão do Python."""
import json, os, re, sys, time, datetime, zoneinfo, pathlib, unicodedata, urllib.request, urllib.parse

TOKEN = os.environ.get('EAGENDAS_TOKEN', '').strip()
if not TOKEN:
    print('Sem token do e-Agendas; nada a fazer.'); sys.exit(0)

API = 'https://eagendas.cgu.gov.br/api/v2/'
BR = zoneinfo.ZoneInfo('America/Sao_Paulo')
HOJE = datetime.datetime.now(BR).date()
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data'
log, amostra = [], {}

def get(path, **q):
    url = API + path + ('?' + urllib.parse.urlencode(q) if q else '')
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + TOKEN, 'Accept': 'application/json',
                                               'User-Agent': 'quorum (github.com/lucca-reis/quorum)'})
    try:
        time.sleep(0.3)
        with urllib.request.urlopen(req, timeout=30) as r:
            js = json.loads(r.read().decode('utf-8') or 'null')
        if path.split('/')[0] not in amostra:
            amostra[path.split('/')[0]] = {'params': q, 'resposta': js}
        return js
    except urllib.error.HTTPError as ex:
        corpo = ''
        try: corpo = ex.read().decode('utf-8', 'replace')[:300]
        except Exception: pass
        log.append(f'{path} {q}: HTTP {ex.code} {corpo}'); return None
    except Exception as ex:
        log.append(f'{path} {q}: {ex}'); return None

def lista(js, chave):
    """As respostas vêm como {sucesso, resposta: {<chave>: [...]}}; aceita variações."""
    if isinstance(js, list): return js
    r = (js or {}).get('resposta', js) or {}
    if isinstance(r, list): return r
    for k in (chave, chave.replace('-', '_'), 'dados', 'itens'):
        if isinstance(r.get(k), list): return r[k]
    for v in r.values():
        if isinstance(v, list): return v
    return []

def norm(t):
    t = unicodedata.normalize('NFD', str(t or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in t if not unicodedata.combining(c))).upper().strip()

def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', norm(t).lower()).strip('-')

def br(d): return d.strftime('%d-%m-%Y')

def campo(o, *ks):
    for k in ks:
        v = o.get(k) if isinstance(o, dict) else None
        if v not in (None, '', []): return v
    return None

# ministros, lidos do próprio site
html = (ROOT / 'index.html').read_text(encoding='utf-8')
bloco = html[html.index('const EXEC_MIN = ['):]
pares = re.findall(r"\['([^']+)','([^']+)'", bloco[:bloco.index('];')])

saida = {}
for pasta, nome in pares:
    item = {'pasta': pasta, 'ministro': nome, 'achado': False, 'itens': []}
    # procura pelo nome completo e, se não achar, pelos dois primeiros nomes
    cands = []
    for busca in (nome, ' '.join(nome.split()[:2])):
        cands = lista(get('agentes-publicos-obrigados', nome_apo=busca, situacao='ativo'), 'agentes-publicos-obrigados')
        if cands: break
    alvo = None
    for c in cands:
        n = campo(c, 'nome', 'nome_apo', 'nomeApo')
        if n and set(norm(nome).split()) <= set(norm(n).split()):
            alvo = c; break
    if not alvo and len(cands) == 1: alvo = cands[0]
    if alvo:
        apo = campo(alvo, 'id', 'apo_id')
        item.update({'achado': True, 'apo': apo, 'cargo': campo(alvo, 'cargo_comissao', 'cargo', 'cargoComissao'),
                     'orgao': campo(alvo, 'orgao', 'orgao_sigla', 'nome_orgao')})
        comps = lista(get('compromissos', apo_id=apo, data_inicio=br(HOJE - datetime.timedelta(days=14)),
                          data_termino=br(HOJE + datetime.timedelta(days=14))), 'compromissos')
        for c in comps:
            item['itens'].append({
                'inicio': campo(c, 'data_inicio', 'dataInicio', 'inicio', 'data_hora_inicio', 'data'),
                'fim': campo(c, 'data_termino', 'dataTermino', 'fim', 'data_hora_termino'),
                't': str(campo(c, 'assunto', 'titulo', 'descricao', 'objetivo') or 'Compromisso')[:200],
                'local': str(campo(c, 'local', 'local_compromisso') or '')[:120] or None,
                'tipo': campo(c, 'tipo', 'tipo_compromisso'),
                'id': campo(c, 'id'),
            })
        item['itens'].sort(key=lambda x: str(x['inicio'] or ''))
    saida[slug(pasta)] = item

OUT.mkdir(exist_ok=True)
res = {'atualizado': datetime.datetime.now(BR).isoformat(timespec='minutes'),
       'periodo': [str(HOJE - datetime.timedelta(days=14)), str(HOJE + datetime.timedelta(days=14))],
       'fonte': 'https://eagendas.cgu.gov.br', 'ministerios': saida, 'erros': log[:40]}
(OUT / 'agendas.json').write_text(json.dumps(res, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(OUT / 'agendas-amostra.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1)[:40000], encoding='utf-8')
print(json.dumps({'achados': sum(v['achado'] for v in saida.values()), 'com_compromissos': sum(bool(v['itens']) for v in saida.values()),
                  'erros': log[:8]}, ensure_ascii=False))
