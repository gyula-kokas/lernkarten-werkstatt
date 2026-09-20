#!/usr/bin/env python3
"""Lokale Lernkarten-Werkstatt. Start: python3 bilder_waehlen.py"""
import argparse, base64, copy, difflib, hashlib, html, json, re, secrets, subprocess, sys, threading, urllib.parse, urllib.request, webbrowser, unicodedata
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'image-library'; DATA.mkdir(exist_ok=True)
DICT_DIR=ROOT/'dictionary'; DICT_DIR.mkdir(exist_ok=True)
DICT_FILE=DICT_DIR/'nouns.json'
LOCK=threading.Lock(); TOKEN=secrets.token_urlsafe(24)
JOB={'running':False,'log':'Noch kein Build gestartet.'}
TRANSLATIONS=json.loads((ROOT/'tools/image-search-en.json').read_text(encoding='utf-8'))
from tools import image_providers
from tools.stoffnamen import STOFFNAMEN
from tools.tts_piper import VOICE as TTS_VOICE, ENGINE as TTS_ENGINE, MP3_BITRATE as TTS_BITRATE, probe as tts_probe, synthesize_mp3
SOURCES={'clipsafari','openmoji','twemoji'}
ALLOWED_HOSTS={'www.clipsafari.com','images.clipsafari.com','spaces-cdn.clipsafari.com','raw.githubusercontent.com'}
_DICT_CACHE={}; _DICT_MTIME=None
TTS_CACHE=ROOT/'tts-cache'; TTS_CACHE.mkdir(exist_ok=True)


def fetch(url):
    host=urllib.parse.urlsplit(url).hostname or ''
    if host not in ALLOWED_HOSTS:raise ValueError('Unzulässige Downloadquelle')
    req=urllib.request.Request(url,headers={'User-Agent':'Lernkarten-Werkstatt/0.1'})
    with urllib.request.urlopen(req,timeout=45) as response:
        if (urllib.parse.urlsplit(response.url).hostname or '') not in ALLOWED_HOSTS:raise ValueError('Unzulässige Weiterleitung')
        data=response.read(8*1024*1024+1)
    if len(data)>8*1024*1024:raise ValueError('Datei größer als 8 MB')
    return data


def fetch_public_json(url):
    host=urllib.parse.urlsplit(url).hostname or ''
    if host not in {'www.wikidata.org','de.wiktionary.org'}:raise ValueError('Unzulässige Wörterbuchquelle')
    req=urllib.request.Request(url,headers={'User-Agent':'Lernkarten-Werkstatt/0.1 (local editor)'})
    with urllib.request.urlopen(req,timeout=12) as response:
        return json.loads(response.read(2*1024*1024).decode('utf-8'))


class Cards(HTMLParser):
    def __init__(self):super().__init__();self.items={};self.active=None;self.pending=""
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='div' and 'card-img-top-clips' in a.get('class',''):
            m=re.search(r"background-image:url\(['\"]?([^)'\"]+)",a.get('style',''));self.pending=m.group(1) if m else ''
        if tag=='a':
            href=a.get('href','')
            if re.fullmatch(r'/clips/[a-zA-Z0-9-]+',href):
                self.active=href;self.items.setdefault(href,{'slug':href.split('/')[-1],'title':'','thumbnail':self.pending})
            else:self.active=None
        if tag=='img' and self.active:
            self.items[self.active]['thumbnail']=a.get('src','');self.items[self.active]['title']=a.get('alt','')
    def handle_endtag(self,tag):
        if tag=='a':self.active=None
    def handle_data(self,data):
        if self.active and data.strip() and not self.items[self.active]['title']:self.items[self.active]['title']=data.strip()


def search(query,page=1):
    url='https://www.clipsafari.com/clips?'+urllib.parse.urlencode({'q':query,'page':page})
    p=Cards();p.feed(fetch(url).decode())
    return [dict(x,provider='clipsafari',source='https://www.clipsafari.com/clips/'+x['slug'],license='CC0-1.0') for x in p.items.values() if x['thumbnail']][:24]


def search_sources(query,page=1,provider='all'):
    from concurrent.futures import ThreadPoolExecutor
    providers=['clipsafari','openmoji','twemoji'] if provider=='all' else [provider]
    if not set(providers)<=SOURCES:raise ValueError('Unbekannte Bildquelle')
    def one(source):
        try:return source,search(query,page) if source=='clipsafari' else image_providers.search(source,query,page),None
        except Exception as exc:return source,[],str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:responses=list(pool.map(one,providers))
    items=[];errors=[]
    for i in range(24):
        for source,rows,error in responses:
            if i<len(rows):items.append(rows[i])
    for source,rows,error in responses:
        if error:errors.append(source+': '+error)
    return {'items':items,'errors':errors}


def clean_svg(data,prefix):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('SVG enthält eine externe Dokumentdefinition')
    root=ET.fromstring(data)
    if any(e.tag.split('}')[-1] in {'image','script','foreignObject'} for e in root.iter()):raise ValueError('SVG enthält Rasterbilder oder aktive Inhalte')
    ns='http://www.w3.org/2000/svg';ET.register_namespace('',ns)
    if root.tag!='{'+ns+'}svg':raise ValueError('Keine SVG-Datei')
    allowed={'svg','g','defs','path','rect','circle','ellipse','line','polyline','polygon','linearGradient','radialGradient','stop','clipPath','mask','title','desc','use'}
    for parent in root.iter():
        for child in list(parent):
            if child.tag.split('}')[-1] not in allowed:parent.remove(child)
    for el in root.iter():
        for k,v in list(el.attrib.items()):
            local=k.split('}')[-1]
            if local.lower().startswith('on') or local in {'base','class'}:del el.attrib[k];continue
            if local=='href' and not v.startswith('#'):raise ValueError('Externe SVG-Referenz')
            refs=re.findall(r'url\((.*?)\)',v,re.I)
            if any(not ref.strip().strip("\"'").startswith('#') for ref in refs) or re.search(r'javascript:|@import|expression\(',v,re.I) or '\\' in v:
                raise ValueError('Externer oder aktiver SVG-Inhalt')
    if 'viewBox' not in root.attrib:
        def dim(k):return float(re.sub(r'px$','',root.get(k,'')))
        root.set('viewBox',f'0 0 {dim("width")} {dim("height")}')
    root.attrib.pop('width',None);root.attrib.pop('height',None)
    ids={el.get('id'):prefix+el.get('id') for el in root.iter() if el.get('id')}
    for el in root.iter():
        for attr,value in list(el.attrib.items()):
            if attr=='id':el.set(attr,ids[value])
            elif attr.split('}')[-1]=='href' and value[1:] in ids:el.set(attr,'#'+ids[value[1:]])
            else:
                def remap(match):
                    ident=match.group(1).strip().strip("\"'")[1:]
                    return 'url(#'+ids.get(ident,ident)+')'
                el.set(attr,re.sub(r'url\((.*?)\)',remap,value,flags=re.I))
    result=ET.tostring(root,encoding='unicode')
    if not any(e.tag.split('}')[-1] in {'path','rect','circle','ellipse','polygon','polyline'} for e in root.iter()):raise ValueError('Keine unterstützten Vektorformen')
    return result


def download(slug):
    if not re.fullmatch('[a-zA-Z0-9-]+',slug):raise ValueError('Ungültige Bildkennung')
    cache=DATA/(slug+'.json')
    if cache.exists():return json.loads(cache.read_text(encoding='utf-8'))
    if slug.startswith(('openmoji--','twemoji--','mdi--')):
        item=image_providers.resolve(slug)
        svg=clean_svg(fetch(item['download']),'asset-'+slug+'-')
        value={k:item[k] for k in ('slug','provider','source','author','license','licenseUrl','title')}
        value['svg']=svg;atomic(cache,value);return value
    source='https://www.clipsafari.com/clips/'+slug;page=fetch(source).decode()
    if 'CC0' not in page:raise ValueError('Keine CC0-Angabe auf der Bildseite gefunden')
    match=re.search(r'href="([^"]+filename=[^\"]*\.svg)"',page)
    if not match:raise ValueError('Kein SVG-Download gefunden')
    url=html.unescape(match.group(1));svg=clean_svg(fetch(url),'asset-'+slug+'-')
    author=re.search(r'by:\s*(?:<[^>]+>\s*)*([^<\n]+)',page)
    value={'slug':slug,'source':source,'author':html.unescape(author.group(1).strip()) if author else '', 'license':'CC0-1.0','svg':svg}
    atomic(cache,value);return value


def atomic(path,value):
    import tempfile
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
        json.dump(value,f,ensure_ascii=False,indent=2);tmp=Path(f.name)
    tmp.replace(path)


def selections():
    p=DATA/'selections.json';return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def theme_paths():
    return {p.name:p for p in sorted((ROOT/'themes').glob('*.json'))}


def themes():
    return {name:json.loads(path.read_text(encoding='utf-8')) for name,path in theme_paths().items()}


def editable_theme_path(name):
    path=theme_paths().get(name)
    if not path:raise ValueError('Dieses Theme ist nur ein Beispiel oder existiert nicht.')
    return path


def key(theme,word):return theme+'::'+word


def validate_entry_payload(d):
    word=str(d.get('word','')).strip()
    article=str(d.get('article','')).strip().lower()
    plural=str(d.get('plural','')).strip()
    acc=str(d.get('accusativeSentence','')).strip()
    dat=str(d.get('dativeSentence','')).strip()
    editor_type=str(d.get('editorType','other')).strip().lower()
    if not word:raise ValueError('Wort darf nicht leer sein.')
    if article not in {'der','die','das'}:raise ValueError('Artikel muss der, die oder das sein.')
    if len(word)>80 or len(plural)>120 or len(acc)>300 or len(dat)>300:raise ValueError('Ein Feld ist ungewöhnlich lang.')
    allowed_types={'animal','person','plant','food','object','vehicle','place','bodypart','nature','other'}
    if editor_type not in allowed_types:editor_type='other'
    return word,article,plural,acc,dat,editor_type


def save_entry(name,old_word,payload):
    path=editable_theme_path(name);doc=json.loads(path.read_text(encoding='utf-8'))
    entries=doc.get('entries') or []
    idx=next((i for i,e in enumerate(entries) if str(e.get('word',''))==old_word),None)
    if idx is None:raise ValueError('Wort wurde im Theme nicht gefunden.')
    word,article,plural,acc,dat,editor_type=validate_entry_payload(payload)
    if word!=old_word and any(str(e.get('word','')).casefold()==word.casefold() for i,e in enumerate(entries) if i!=idx):
        raise ValueError('Dieses Wort gibt es im Theme bereits.')
    e=dict(entries[idx]);e.update(word=word,article=article,plural=plural,pluralWithArticle=('die '+plural if plural else ''),accusativeSentence=acc,dativeSentence=dat,editorType=editor_type)
    entries[idx]=e;doc['entries']=entries;doc['entryCount']=len(entries);atomic(path,doc)
    if word!=old_word:
        with LOCK:
            s=selections();old_key=key(name,old_word)
            if old_key in s:s[key(name,word)]=s.pop(old_key);atomic(DATA/'selections.json',s)
    return e


def add_entry(name,word,allow_unknown=False):
    path=editable_theme_path(name);doc=json.loads(path.read_text(encoding='utf-8'));entries=doc.get('entries') or []
    word=str(word).strip()
    if not word:raise ValueError('Bitte ein Wort eingeben.')
    if any(str(e.get('word','')).casefold()==word.casefold() for e in entries):raise ValueError('Dieses Wort gibt es bereits.')
    lookup=dictionary_lookup(word)
    if lookup.get('found'):
        d=lookup['entry'];word=d.get('word') or word;article=d.get('article') or 'das';plural=d.get('plural') or ''
    elif not allow_unknown:
        suggestions=', '.join(x.get('word','') for x in lookup.get('suggestions',[])[:5])
        suffix=(' Meintest du: '+suggestions+'?' if suggestions else '')
        raise ValueError('Wort nicht im deutschen Wörterbuch gefunden.'+suffix+' Für Sonderfälle kann „trotzdem anlegen“ verwendet werden.')
    else:
        article='das';plural=''
    e={'word':word,'article':article,'plural':plural,'accusativeSentence':'','dativeSentence':'','imageIndex':len(entries),'pluralWithArticle':('die '+plural if plural else ''),'editorType':infer_theme_type(doc.get('themeName',''))}
    entries.append(e);doc['entries']=entries;doc['entryCount']=len(entries);atomic(path,doc);return e


def delete_entry(name,word):
    path=editable_theme_path(name);doc=json.loads(path.read_text(encoding='utf-8'));entries=doc.get('entries') or []
    new=[e for e in entries if str(e.get('word',''))!=word]
    if len(new)==len(entries):raise ValueError('Wort nicht gefunden.')
    doc['entries']=new;doc['entryCount']=len(new);atomic(path,doc)
    with LOCK:
        s=selections();s.pop(key(name,word),None);atomic(DATA/'selections.json',s)
    return True


def slugify(text):
    text=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    text=re.sub(r'[^a-z0-9]+','-',text).strip('-')
    return text or 'thema'


def create_theme(theme_name):
    theme_name=str(theme_name).strip()
    if not theme_name:raise ValueError('Themenname fehlt.')
    base=slugify(theme_name);folder=ROOT/'themes';folder.mkdir(exist_ok=True)
    nums=[]
    for p in folder.glob('theme-*.json'):
        m=re.match(r'theme-(\d+)',p.name)
        if m:nums.append(int(m.group(1)))
    number=max(nums,default=0)+1
    filename=f'theme-{number:02d}-{base}.json';theme_id=f'theme-{number:02d}-{base}'
    doc={'themeId':theme_id,'themeName':theme_name,'language':'de','version':1,'entryCount':0,'imageMode':'per-entry-svg','entries':[]}
    atomic(folder/filename,doc);return filename,doc


def load_dictionary():
    global _DICT_CACHE,_DICT_MTIME
    try:mtime=DICT_FILE.stat().st_mtime
    except FileNotFoundError:return {}
    if _DICT_MTIME!=mtime:
        try:_DICT_CACHE=json.loads(DICT_FILE.read_text(encoding='utf-8'));_DICT_MTIME=mtime
        except Exception:_DICT_CACHE={};_DICT_MTIME=mtime
    return _DICT_CACHE


def _plain_wiki_value(value):
    # Reduce the simple markup normally used in noun overview fields.
    value=html.unescape(str(value or '')).strip()
    value=re.sub(r'<!--.*?-->', '', value, flags=re.S)
    value=re.sub(r'\[\[[^\]|]+\|([^\]]+)\]\]', r'\1', value)
    value=re.sub(r'\[\[([^\]]+)\]\]', r'\1', value)
    value=value.replace(chr(39)*3, '').replace(chr(39)*2, '')
    value=re.sub(r'<[^>]+>', '', value)
    return value.strip()


def wiktionary_noun_lookup(word):
    # Fallback for words missing in the local dictionary. Successful results
    # are cached in dictionary/nouns.json.
    params=urllib.parse.urlencode({
        'action':'parse', 'page':word, 'prop':'wikitext',
        'format':'json', 'formatversion':'2', 'redirects':'1',
    })
    data=fetch_public_json('https://de.wiktionary.org/w/api.php?'+params)
    text=str((data.get('parse') or {}).get('wikitext') or '')
    if not text:return None

    blocks=re.findall(r'\{\{Deutsch Substantiv Übersicht\s*(.*?)\n\}\}', text, flags=re.S|re.I)
    for block in blocks:
        fields={}
        for line in block.splitlines():
            m=re.match(r'\s*\|\s*([^=]+?)\s*=\s*(.*?)\s*$', line)
            if m:fields[m.group(1).strip()]=_plain_wiki_value(m.group(2))
        genus=(fields.get('Genus') or fields.get('Genus 1') or '').strip().lower()
        article={'m':'der','f':'die','n':'das'}.get(genus)
        if not article:continue

        plural=''
        for field_name in ('Nominativ Plural','Nominativ Plural 1','Nominativ Plural 2'):
            candidate=_plain_wiki_value(fields.get(field_name,''))
            if candidate and candidate not in {'—','-','–','?','kein Plural'}:
                candidate=re.split(r'\s*(?:,|/|;| oder )\s*',candidate,1,flags=re.I)[0].strip()
                if candidate and '{{' not in candidate:
                    plural=candidate
                    break
        if not plural:continue

        lemma=_plain_wiki_value(fields.get('Nominativ Singular') or word)
        if not lemma or '{{' in lemma:lemma=word
        return {'word':lemma,'article':article,'plural':plural,'source':'de.wiktionary.org'}
    return None


def cache_dictionary_entry(entry):
    global _DICT_CACHE,_DICT_MTIME
    if not entry:return
    with LOCK:
        current=dict(load_dictionary())
        current[str(entry['word']).casefold()]=entry
        atomic(DICT_FILE,current)
        _DICT_CACHE=current
        try:_DICT_MTIME=DICT_FILE.stat().st_mtime
        except OSError:_DICT_MTIME=None


def dictionary_lookup(word):
    word=str(word).strip();d=load_dictionary();k=word.casefold();hit=d.get(k)
    if hit:return {'found':True,'entry':hit,'suggestions':[],'count':len(d),'online':False}

    online_error=''
    try:
        online=wiktionary_noun_lookup(word)
        if online:
            cache_dictionary_entry(online)
            return {'found':True,'entry':online,'suggestions':[],'count':len(load_dictionary()),'online':True}
    except Exception as exc:
        online_error=str(exc)

    d=load_dictionary()
    candidates=[x for x in d.keys() if x[:1]==k[:1] and abs(len(x)-len(k))<=3]
    if len(candidates)>8000:candidates=candidates[:8000]
    close=difflib.get_close_matches(k,candidates,n=6,cutoff=.72)
    return {
        'found':False,'entry':None,'suggestions':[d[x] for x in close],
        'count':len(d),'online':False,'onlineError':online_error
    }


def classify_word(word):
    params=urllib.parse.urlencode({'action':'wbsearchentities','search':word,'language':'de','uselang':'de','type':'item','limit':7,'format':'json','origin':'*'})
    data=fetch_public_json('https://www.wikidata.org/w/api.php?'+params)
    rows=data.get('search') or []
    exact=[r for r in rows if str(r.get('label','')).casefold()==str(word).casefold()] or rows
    text=' '.join((str(r.get('label',''))+' '+str(r.get('description',''))) for r in exact[:3]).casefold()
    groups=[
        ('animal',['tier','säugetier','vogel','fisch','insek','reptil','amphib','pferd','hund','katze','nagetier','primat']),
        ('plant',['pflanze','baum','blume','strauch','kraut','gewächs']),
        ('food',['lebensmittel','nahrungsmittel','speise','getränk','obst','gemüse','frucht','gericht']),
        ('vehicle',['fahrzeug','verkehrsmittel','automobil','auto','zug','bahn','schiff','flugzeug','fahrrad']),
        ('bodypart',['körperteil','organ','anatom']),
        ('person',['person','mensch','beruf','personbezeichnung']),
        ('place',['ort','stadt','raum','gebäude','landschaft','stätte']),
        ('object',['gegenstand','gerät','werkzeug','spielzeug','möbel','instrument','kleidungsstück','behälter','sportgerät']),
        ('nature',['gestein','mineral','naturphänomen','wetter','gewässer']),
    ]
    for kind,needles in groups:
        if any(n in text for n in needles):return {'type':kind,'evidence':text[:300]}
    return {'type':'other','evidence':text[:300]}



def infer_theme_type(theme_name):
    text=str(theme_name or '').casefold()
    groups=[
        ('animal',['tier','tiere','zoo','bauernhof','waldtiere','haustier']),
        ('food',['essen','trinken','lebensmittel','küche','obst','gemüse']),
        ('vehicle',['fahrzeug','fahrzeuge','verkehr','reise','reisen','bahn','zug']),
        ('plant',['pflanze','pflanzen','garten','blume','blumen']),
        ('bodypart',['körper','körperteil','gesundheit']),
        ('person',['mensch','menschen','beruf','berufe','familie']),
        ('place',['ort','orte','stadt','gebäude','zuhause','schule']),
        ('object',['spielzeug','werkzeug','möbel','kleidung','haushalt','gegenstand']),
    ]
    for kind,needles in groups:
        if any(x in text for x in needles): return kind
    return 'other'


CASE_FORMS={'acc':{'der':'den','die':'die','das':'das'},'dat':{'der':'dem','die':'der','das':'dem'}}


def sentence_has_case(sentence,article,kind,word):
    """Prüfen, ob der Satz die Kasusform des Artikels beim Nomen enthält.

    Dieselbe Regel wie maskedCaseSentence() in der Lernkarten-Vorlage: zwischen
    Artikel und Nomen dürfen bis zu zwei Wörter stehen (Adjektiv), das Nomen darf
    flektiert sein (Bär -> Bären, Roter Panda -> Roten Panda).
    """
    form=CASE_FORMS.get(kind,{}).get(str(article or '').strip())
    text=str(sentence or '').strip()
    parts=[p for p in re.split(r'\s+',str(word or '').strip()) if p]
    if not form or not text or not parts: return False
    pattern=re.compile(r'\b'+re.escape(form)+r'\b(?:\s+\S+){0,2}\s+'+re.escape(parts[-1]),re.IGNORECASE)
    return bool(pattern.search(text))


def dictionary_check(word, article='', plural=''):
    """Compare editor data with the authoritative local/live noun lookup."""
    r=dictionary_lookup(word)
    if not r.get('found'):
        return {'known':False,'ok':False,'message':'Wort nicht im Wörterbuch gefunden.','lookup':r}
    e=r['entry']
    mismatches=[]
    if article and article != e.get('article'): mismatches.append(f"Artikel: erwartet {e.get('article')}")
    expected_plural=str(e.get('plural') or '').strip()
    if plural and expected_plural and plural != expected_plural: mismatches.append(f"Mehrzahl: erwartet {expected_plural}")
    return {'known':True,'ok':not mismatches,'message':' · '.join(mismatches) if mismatches else 'Wörterbuchdaten stimmen.','entry':e,'lookup':r}


def image_duplicates():
    """Bild-Slug -> Wörter, die ihn verwenden (alle Themen)."""
    gruppen={}
    for k,v in selections().items():
        slug=str((v or {}).get('slug') or '').strip()
        wort=k.split('::',1)[1] if '::' in k else k
        if slug: gruppen.setdefault(slug,set()).add(wort)
    return gruppen


def audit_theme(name):
    doc=themes()[name]; selected=selections(); gruppen=image_duplicates(); issues=[]; stats={'total':0,'ready':0,'warning':0,'error':0}
    seen={}
    for i,e in enumerate(doc.get('entries') or []):
        stats['total']+=1
        word=str(e.get('word','')).strip(); row=[]; level='ready'
        if not word:
            row.append('Wort fehlt'); level='error'
        k=word.casefold()
        if k in seen:
            row.append(f'Doppeltes Wort (auch Zeile {seen[k]+1})'); level='error'
        else: seen[k]=i
        if e.get('article') not in {'der','die','das'}:
            row.append('Artikel fehlt/ungültig'); level='error'
        d=load_dictionary(); de=d.get(k) or {}
        # Deutsch ist mehrdeutig (der/die Paprika) und der übliche Artikel ist
        # nicht immer die erste Wörterbuch-Bedeutung (Butter, Kiwi, Taxi).
        # Darum gilt jede belegte Variante als richtig.
        artikel_varianten={str(x).strip() for x in (de.get('articles') or [])} | {str(de.get('article') or '').strip()}
        plural_varianten={str(x).strip() for x in (de.get('plurals') or [])} | {str(de.get('plural') or '').strip()}
        plural_varianten.discard('')
        # Stoffnamen (Milch, Reis, Blut) haben keine Mehrzahl - „die Milche" ist
        # falsch. Muss mit STOFFNAMEN in tools/build_decks.py übereinstimmen.
        stoffname=k in STOFFNAMEN
        if not str(e.get('plural','')).strip():
            # Nur melden, wenn das Wörterbuch eine Mehrzahl kennt und es kein
            # Stoffname ist.
            if plural_varianten and not stoffname:
                row.append('Mehrzahl fehlt'); level='warning' if level!='error' else level
        if not str(e.get('accusativeSentence','')).strip():
            row.append('Akkusativsatz fehlt'); level='error'
        if not str(e.get('dativeSentence','')).strip():
            row.append('Dativsatz fehlt'); level='error'
        # Der Lernkarten-Druck maskiert die Kasusform im Satz. Fehlt sie, bleibt
        # die Karte ohne Satzkontext - das faellt sonst erst beim Drucken auf.
        for kind,field,label in (('acc','accusativeSentence','Akkusativ'),('dat','dativeSentence','Dativ')):
            text=str(e.get(field,'')).strip()
            if text and not sentence_has_case(text,e.get('article'),kind,word):
                form=CASE_FORMS[kind].get(str(e.get('article','')).strip(),'')
                row.append(f'{label}satz enthält „{form} {word}“ nicht'); level='warning' if level!='error' else level
        image_ok=bool(e.get('imageSvg') or selected.get(key(name,word)))
        if not image_ok:
            row.append('Bild fehlt'); level='error'
        # Ein Bild, das viele verschiedene Wörter zeigt, trägt die Bedeutung nicht
        # mehr (z.B. 16 Baustellenfahrzeuge mit demselben Lastwagen-Symbol).
        else:
            slug=str((selected.get(key(name,word)) or {}).get('slug') or '')
            andere=sorted(gruppen.get(slug,set())-{word}) if slug else []
            if len(andere)>=2:
                rest='' if len(andere)<=4 else f' +{len(andere)-4}'
                row.append(f"Bild auch für {', '.join(andere[:4])}{rest}"); level='warning' if level!='error' else level
        # Dictionary check is local-only here to keep audit fast and deterministic.
        if de:
            if e.get('article') not in artikel_varianten:
                row.append(f"Artikel weicht vom Wörterbuch ab ({de.get('article')})"); level='error'
            if plural_varianten and not (stoffname and not str(e.get('plural','')).strip()) and str(e.get('plural','')).strip() not in plural_varianten:
                row.append(f"Mehrzahl weicht vom Wörterbuch ab ({de.get('plural')})"); level='warning' if level!='error' else level
        else:
            row.append('Noch nicht lokal im Wörterbuch geprüft'); level='warning' if level!='error' else level
        if row:
            issues.append({'index':i,'word':word or '(leer)','level':level,'issues':row})
            stats['error' if level=='error' else 'warning']+=1
        else:
            stats['ready']+=1
    return {'stats':stats,'issues':issues}


def uploaded_image_asset(name, word, filename, data_url):
    """Create a safe local SVG wrapper for a user supplied image."""
    if not isinstance(data_url,str) or not data_url.startswith('data:'):
        raise ValueError('Ungültige Bilddaten.')
    m=re.fullmatch(r'data:(image/(?:png|jpeg|webp|svg\+xml));base64,([A-Za-z0-9+/=\s]+)',data_url,re.S)
    if not m: raise ValueError('Erlaubt sind PNG, JPEG, WebP oder SVG.')
    mime=m.group(1)
    try: raw=base64.b64decode(re.sub(r'\s+','',m.group(2)),validate=True)
    except Exception: raise ValueError('Bilddaten sind beschädigt.')
    if len(raw)>6*1024*1024: raise ValueError('Bild ist größer als 6 MB.')
    prefix=hashlib.sha256((name+'::'+word+'::upload').encode()).hexdigest()[:12]+'-'
    if mime=='image/svg+xml':
        svg=clean_svg(raw,prefix)
    else:
        encoded=base64.b64encode(raw).decode('ascii')
        svg=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
             f'<rect width="100" height="100" fill="white"/>'
             f'<image href="data:{mime};base64,{encoded}" x="2" y="2" width="96" height="96" preserveAspectRatio="xMidYMid meet"/>'
             f'</svg>')
    slug='upload-'+hashlib.sha256((name+'::'+word+'::'+filename+str(len(raw))).encode()).hexdigest()[:20]
    asset={'slug':slug,'svg':svg,'source':'Lokaler Upload: '+str(filename or 'Bild'),'author':'Benutzer-Upload','license':'Vom Benutzer bereitgestellt','licenseUrl':'','provider':'local-upload','title':str(filename or word)}
    atomic(DATA/(slug+'.json'),asset)
    with LOCK:
        sel=selections();sel[key(name,word)]={'slug':slug,'query':''};atomic(DATA/'selections.json',sel)
    return asset


def start_build_all():
    with LOCK:
        if JOB['running']: raise ValueError('Ein Build läuft bereits')
        folder=ROOT/'selected-themes'; folder.mkdir(exist_ok=True)
        # Export every theme first, so the resulting file is deterministic and complete.
        for name in theme_paths(): export_theme(name)
        JOB.update(running=True,log='Alle Themes exportiert. Baue gemeinsame einzelne HTML-Datei …\n')
    def run():
        try:
            target=ROOT/'output-selected';target.mkdir(exist_ok=True)
            output=target/'lernkarten-alle-themes.html';temp_output=target/'lernkarten-alle-themes.building.html'
            cmd=[sys.executable,str(ROOT/'build_simple.py'),'--themes',str(folder),'--output',str(temp_output)]
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            for line in proc.stdout:
                with LOCK: JOB['log']=(JOB['log']+line)[-60000:]
            if proc.wait()!=0: raise RuntimeError('Build fehlgeschlagen. Vorhandene fertige HTML bleibt erhalten.')
            temp_output.replace(output)
            with LOCK: JOB['log']+='\nFertig: '+str(output)+'\n'
        except Exception as exc:
            with LOCK: JOB['log']+='\nFEHLER: '+str(exc)+'\n'
        finally:
            with LOCK: JOB['running']=False
    threading.Thread(target=run,daemon=True).start()

def tts_status():
    ok, detail = tts_probe()
    return {
        'ready': ok,
        'engine': TTS_ENGINE,
        'voice': TTS_VOICE,
        'codec': 'MP3 (MPEG-1 Layer III)',
        'bitrate': TTS_BITRATE,
        'detail': detail,
        'fallback': False,
    }


def tts_audio(text):
    text=str(text or '').strip()
    if not text:
        raise ValueError('Kein Text für die Aussprache.')
    return synthesize_mp3(text, TTS_CACHE)


def export_theme(name):
    d=copy.deepcopy(themes()[name]);selected=selections();missing=[]
    for e in d['entries']:
        choice=selected.get(key(name,e['word']))
        if not choice:
            if e.get('imageSvg'):continue
            missing.append(e['word']);continue
        asset=json.loads((DATA/(choice['slug']+'.json')).read_text(encoding='utf-8'));e['imageSvg']=asset['svg'] if asset.get('provider')=='local-upload' else clean_svg(asset['svg'].encode(),hashlib.sha256(key(name,e['word']).encode()).hexdigest()[:12]+'-')
        e['imageSource']=asset['source'];e['imageAuthor']=asset['author'];e['imageLicense']=asset['license'];e['imageLicenseUrl']=asset.get('licenseUrl','https://creativecommons.org/publicdomain/zero/1.0/');e['imageChanges']='Technische SVG-Bereinigung und angepasste Darstellung.'
        e.pop('editorType',None);e.pop('imageSearch',None)
    if missing:raise ValueError(f'{len(missing)} Bilder fehlen: '+', '.join(missing[:12]))
    for e in d['entries']:
        e.pop('editorType',None);e.pop('imageSearch',None)
    d['imageMode']='per-entry-svg';d.pop('sourceImage',None);d.pop('sourceGrid',None);d.pop('cuttingMode',None);d.pop('vectorizer',None)
    folder=ROOT/'selected-themes';folder.mkdir(exist_ok=True);atomic(folder/name,d);return folder/name


def start_build(name):
    with LOCK:
        if JOB['running']:raise ValueError('Ein Build läuft bereits')
        path=export_theme(name);JOB.update(running=True,log='Theme gespeichert. Baue einzelne HTML-Datei …\n')
    def run():
        try:
            import tempfile
            with tempfile.TemporaryDirectory(prefix='ddd-selected-') as raw:
                folder=Path(raw);(folder/path.name).write_bytes(path.read_bytes())
                target=ROOT/'output-selected';target.mkdir(exist_ok=True)
                output=target/(path.stem+'.html');temp_output=target/(path.stem+'.building.html')
                cmd=[sys.executable,str(ROOT/'build_simple.py'),'--themes',str(folder),'--output',str(temp_output)]
                proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
                for line in proc.stdout:
                    with LOCK:JOB['log']=(JOB['log']+line)[-60000:]
                if proc.wait()!=0:raise RuntimeError('Build fehlgeschlagen. Vorhandene fertige HTML bleibt erhalten.')
                temp_output.replace(output)
                with LOCK:JOB['log']+='\nFertig: '+str(output)+'\n'
        except Exception as exc:
            with LOCK:JOB['log']+='\nFEHLER: '+str(exc)+'\n'
        finally:
            with LOCK:JOB['running']=False
    threading.Thread(target=run,daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,ctype='application/json'):
        data=value.encode() if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',ctype+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def send_bytes(self,data,status=200,ctype='application/octet-stream'):
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':return self.send({'error':'Ungültiger Host'},403)
        q=urllib.parse.urlsplit(self.path);args=urllib.parse.parse_qs(q.query)
        try:
            if q.path=='/':return self.send((ROOT/'tools/image-picker.html').read_text(encoding='utf-8').replace('__TOKEN__',TOKEN),ctype='text/html')
            if q.path=='/api/themes':return self.send({'themes':themes(),'selected':selections(),'translations':TRANSLATIONS,'dictionaryCount':len(load_dictionary())})
            if q.path=='/api/search':return self.send(search_sources(args.get('q',[''])[0][:120],max(1,min(100,int(args.get('page',['1'])[0]))),args.get('source',['all'])[0]))
            if q.path=='/api/selected':return self.send(json.loads((DATA/(args['slug'][0]+'.json')).read_text(encoding='utf-8')) if re.fullmatch('[a-zA-Z0-9-]+',args['slug'][0]) else {},ctype='application/json')
            if q.path=='/api/job':return self.send(dict(JOB))
            if q.path=='/api/tts-status':return self.send(tts_status())
            if q.path=='/api/dictionary':return self.send(dictionary_lookup(args.get('word',[''])[0][:80]))
            if q.path=='/api/classify':return self.send(classify_word(args.get('word',[''])[0][:80]))
            if q.path=='/api/audit':return self.send(audit_theme(args.get('theme',[''])[0]))
            return self.send({'error':'Nicht gefunden'},404)
        except Exception as exc:self.send({'error':str(exc)},400)
    def do_POST(self):
        if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}' or self.headers.get('X-Token')!=TOKEN:return self.send({'error':'Ungültige Anfrage'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>9*1024*1024:raise ValueError('Anfrage zu groß')
            d=json.loads(self.rfile.read(size) or b'{}')
            if self.path=='/api/tts':
                audio=tts_audio(d.get('text',''))
                return self.send_bytes(audio,ctype='audio/mpeg')
            if self.path=='/api/create-theme':
                name,doc=create_theme(d.get('themeName',''));return self.send({'name':name,'theme':doc})
            name=d.get('theme','')
            if self.path=='/api/build-all':start_build_all();return self.send({'started':True})
            if self.path=='/api/add-entry':return self.send({'entry':add_entry(name,d.get('word',''),bool(d.get('allowUnknown')))})
            if self.path=='/api/delete-entry':delete_entry(name,d.get('word',''));return self.send({'ok':True})
            if self.path=='/api/save-entry':return self.send({'entry':save_entry(name,d.get('oldWord',''),d)})
            t=themes()[name];word=d.get('word')
            if self.path=='/api/upload-image':
                if word not in [e['word'] for e in t['entries']]:raise ValueError('Unbekanntes Wort')
                return self.send(uploaded_image_asset(name,word,d.get('filename','Bild'),d.get('dataUrl','')))
            if self.path=='/api/select':
                if word not in [e['word'] for e in t['entries']]:raise ValueError('Unbekanntes Wort')
                asset=download(d['slug'])
                with LOCK:
                    s=selections();s[key(name,word)]={'slug':asset['slug'],'query':d.get('query','')};atomic(DATA/'selections.json',s)
                return self.send(asset)
            if self.path=='/api/export':return self.send({'path':str(export_theme(name))})
            if self.path=='/api/build':start_build(name);return self.send({'started':True})
            self.send({'error':'Nicht gefunden'},404)
        except Exception as exc:self.send({'error':str(exc)},400)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    ready,detail=tts_probe()
    if not ready:
        raise SystemExit('Pflicht-TTS nicht bereit: '+detail+'\nDie Lernkarten-Werkstatt startet absichtlich nicht ohne Piper + ffmpeg.')
    print('TTS OK: '+detail,flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);url=f'http://127.0.0.1:{server.server_port}/';print('Lernkarten-Werkstatt: '+url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
