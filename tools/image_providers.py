"""Searchable SVG catalogs; image bytes load only after selection.

* ``openmoji`` / ``twemoji`` – emoji artwork, index in ``catalog.json`` (an emoji
  code can be drawn by either set: two different pictures of the same motif).
* ``fluent`` – Microsoft Fluent Emoji (MIT), the *third* drawing of the same
  motif; the index in ``fluent.json`` is written by ``import_fluent_emoji.py`` and
  keeps the OpenMoji code of every drawing.
* ``mdi`` – Material Design Icons (Pictogrammers, Apache 2.0) for objects the
  emoji sets do not have (radiator, kettle, bookshelf, forest, …).
"""
import functools
import json
import re
import urllib.parse
from pathlib import Path

@functools.lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent/'image-sources/catalog.json').read_text())

@functools.lru_cache(maxsize=1)
def mdi_catalog():
    return json.loads((Path(__file__).parent/'image-sources/mdi.json').read_text())

@functools.lru_cache(maxsize=1)
def fluent_index():
    return json.loads((Path(__file__).parent/'image-sources/fluent.json').read_text())

@functools.lru_cache(maxsize=1)
def fluent_by_code():
    """OpenMoji-Code -> Fluent-Zeichnung desselben Motivs."""
    return {str(row['code']):row for row in fluent_index()['items'] if row.get('code')}

@functools.lru_cache(maxsize=1)
def fluent_by_slug():
    return {str(row['slug']):row for row in fluent_index()['items']}

def fluent_candidate(row):
    """Katalogzeile (OpenMoji-Code) -> Fluent-Zeichnung, oder ``None``."""
    item=fluent_by_code().get(str(row['code']))
    if item is None:return None
    data=fluent_index();ref=data.get('ref','main')
    url=f"https://raw.githubusercontent.com/microsoft/fluentui-emoji/{ref}/{urllib.parse.quote(str(item['file']),safe='/')}"
    return dict(slug=item['slug'],provider='fluent',title=item['title'],
                thumbnail=url,download=url,source=f"{data['repository']}/blob/{ref}/{urllib.parse.quote(str(item['file']),safe='/')}",
                author=data.get('author','Microsoft Corporation and contributors'),
                license=data.get('license','MIT'),licenseUrl=data.get('licenseUrl',data['repository']))

def candidate(provider, row):
    data=catalog()
    if provider=='openmoji':
        code=row['code']
        url=f"https://raw.githubusercontent.com/hfg-gmuend/openmoji/{data['openmojiRef']}/color/svg/{code}.svg"
        source=f'https://openmoji.org/library/emoji-{code}/'
        author=f"{row['author']} / OpenMoji contributors"
        license='CC-BY-SA-4.0'
        license_url='https://creativecommons.org/licenses/by-sa/4.0/'
    elif provider=='twemoji':
        code=row['twemoji']
        if not code:return None
        url=f"https://raw.githubusercontent.com/jdecked/twemoji/{data['twemojiRef']}/assets/svg/{code}.svg"
        source=f"https://github.com/jdecked/twemoji/blob/{data['twemojiRef']}/assets/svg/{code}.svg"
        author='Twitter, Inc. and other Twemoji contributors'
        license='CC-BY-4.0'
        license_url='https://creativecommons.org/licenses/by/4.0/'
    elif provider=='fluent':
        return fluent_candidate(row)
    elif provider=='mdi':
        code=row['name']
        ref=mdi_catalog()['mdiRef']
        url=f"https://raw.githubusercontent.com/Templarian/MaterialDesign/{ref}/svg/{code}.svg"
        source=f"https://github.com/Templarian/MaterialDesign/blob/{ref}/svg/{code}.svg"
        author='Pictogrammers (Material Design Icons)'
        license='Apache-2.0'
        license_url='https://www.apache.org/licenses/LICENSE-2.0'
    else:raise ValueError('Unbekannte Bildquelle')
    return dict(slug=provider+'--'+code, provider=provider, title=row['title'],
                thumbnail=url, download=url, source=source, author=author,
                license=license, licenseUrl=license_url)

def search(provider, query, page=1):
    tokens=re.findall(r'[a-z0-9]+',query.lower())
    if not tokens:return []
    if provider=='mdi':
        found=[]
        for row in mdi_catalog()['items']:
            words=set(re.findall(r'[a-z0-9]+',row['name']))
            if not all(t in words for t in tokens):continue
            found.append(candidate('mdi',row))
        return found[(page-1)*24:page*24]
    if provider=='fluent':
        return fluent_search(tokens,query,page)
    found=[];seen=set()
    for row in catalog()['items']:
        text=row['title'].lower()+' '+row['tags'].lower()
        words=set(re.findall(r'[a-z0-9]+',text))
        if not all(t in words for t in tokens):continue
        item=candidate(provider,row)
        if item is None or item['slug'] in seen:continue
        seen.add(item['slug'])
        score=0 if row['title'].lower()==query.lower().strip() else 1 if all(t in row['title'].lower().split() for t in tokens) else 2
        found.append((score,item))
    found.sort(key=lambda pair:(pair[0],pair[1]['title']))
    return [item for _,item in found[(page-1)*24:page*24]]

def fluent_search(tokens,query,page=1):
    """Fluent-Zeichnungen zur Suchanfrage: Treffer über die Stichwörter des
    OpenMoji-Katalogs (gleiches Motiv, gleicher Code) plus Titeltreffer aus dem
    Fluent-Index (Motivnamen, die es nur dort gibt, z. B. „Blackbird“)."""
    found=[];seen=set()
    for row in catalog()['items']:
        text=(row['title']+' '+row['tags']).lower()
        words=set(re.findall(r'[a-z0-9]+',text))
        if not all(t in words for t in tokens):continue
        item=fluent_candidate(row)
        if item is None or item['slug'] in seen:continue
        seen.add(item['slug']);found.append(item)
    for row in fluent_index()['items']:
        words=set(re.findall(r'[a-z0-9]+',str(row['title']).lower()))
        if not all(t in words for t in tokens):continue
        item=candidate('fluent',{'code':row.get('code') or '',})
        item=item or fluent_by_slug_item(row)
        if item is None or item['slug'] in seen:continue
        seen.add(item['slug']);found.append(item)
    return found[(page-1)*24:page*24]

def fluent_by_slug_item(row):
    """Fluent-Indexzeile ohne OpenMoji-Code direkt in einen Kandidaten wandeln."""
    data=fluent_index();ref=data.get('ref','main')
    url=f"https://raw.githubusercontent.com/microsoft/fluentui-emoji/{ref}/{urllib.parse.quote(str(row['file']),safe='/')}"
    return dict(slug=row['slug'],provider='fluent',title=row['title'],thumbnail=url,download=url,
                source=f"{data['repository']}/blob/{ref}/{urllib.parse.quote(str(row['file']),safe='/')}",
                author=data.get('author','Microsoft Corporation and contributors'),
                license=data.get('license','MIT'),licenseUrl=data.get('licenseUrl',data['repository']))

def resolve(slug):
    provider,code=slug.split('--',1)
    if provider=='fluent':
        row=fluent_by_slug().get(slug)
        if row is None:raise ValueError('Bild nicht im Katalog gefunden')
        return candidate('fluent',{'code':row.get('code') or ''}) or fluent_by_slug_item(row)
    if provider=='mdi':
        for row in mdi_catalog()['items']:
            if row['name']==code:return candidate('mdi',row)
        raise ValueError('Bild nicht im Katalog gefunden')
    if provider not in {'openmoji','twemoji'}:raise ValueError('Unbekannte Bildquelle')
    for row in catalog()['items']:
        if row['code' if provider=='openmoji' else 'twemoji']==code:
            return candidate(provider,row)
    raise ValueError('Bild nicht im Katalog gefunden')
