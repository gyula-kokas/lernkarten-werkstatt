#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import shutil
import struct
import threading
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bilder_waehlen as editor
import tools.build_decks as build_decks
import build_simple
import tools.tts_piper as tts


def pcm_bytes(samples):
    return struct.pack('<%dh'%len(samples),*samples)


def check_audio():
    # Aufbereitung: Stille weg, gleicher Pegel, Länge stimmt
    stille=[0]*20000
    sprache=[300,-300]*2500
    samples=tts.process_samples(pcm_bytes(stille+sprache+stille),22050)
    peak=max(abs(x) for x in samples)
    assert abs(peak-round(tts.TARGET_PEAK*32767))<=1, f'Peak ist {peak}'
    dauer_ms=1000*len(samples)/22050
    erwartet=tts.LEAD_SILENCE_MS+tts.TAIL_SILENCE_MS+1000*len(sprache)/22050
    assert abs(dauer_ms-erwartet)<25, f'{dauer_ms:.0f} ms statt {erwartet:.0f} ms'
    assert len(samples)<len(stille+sprache+stille)/4, 'Stille muss deutlich gekürzt sein'
    assert len(tts.process_samples(pcm_bytes([0]*1000),16000))==1000, 'reine Stille darf nicht abstürzen'
    stereo=tts.process_samples(pcm_bytes([300,300]*500),16000,channels=2)
    assert len(stereo)>500 and abs(max(abs(x) for x in stereo)-round(tts.TARGET_PEAK*32767))<=1, 'Stereo muss zu Mono gemischt werden'

    # MP3-Kodierung: eine Framemarke, kein WAV, deutlich kleiner als PCM
    if shutil.which('ffmpeg'):
        pcm=samples.tobytes()
        mp3=tts.encode_mp3(pcm,22050)
        assert tts.mp3_looks_valid(mp3), 'MP3 muss mit ID3 oder Framemarke beginnen'
        assert not mp3.startswith(b'RIFF'), 'Es darf kein WAV mehr entstehen'
        assert len(mp3)<len(pcm)/2, f'MP3 ist {len(mp3)} statt <{len(pcm)//2} Bytes'
        assert not tts.mp3_looks_valid(b'RIFF'+bytes(500)), 'WAV darf nicht als MP3 durchgehen'
    else:
        print('Hinweis: ffmpeg fehlt, MP3-Kodierung wird übersprungen.')

    texts=tts.texts_for_entries([{'entries':[{'word':'Hund','article':'der',
        'plural':'Hunde','pluralWithArticle':'die Hunde',
        'accusativeSentence':'Das Kind sieht den Hund.','dativeSentence':'Das Kind schaut zu dem Hund.'}]}])
    assert tts.PROMPT_PREFIX in texts, texts
    assert 'Hund.' in texts, 'Wortclip muss für die Ansage vorhanden sein'
    assert not any(t.startswith('Das Wort heißt Hund') for t in texts), \
        'Die Ansage wird aus Bausteinen gebaut, nicht als ganzer Satz'
    assert not any(t.startswith('Hör noch einmal') for t in texts), \
        'Der zweite Prompt nutzt dieselben Bausteine'
    assert tts.prompt_parts('Hund')==[tts.PROMPT_PREFIX,'Hund.'], tts.prompt_parts('Hund')
    assert tts.prompt_parts('Roter Panda')==[tts.PROMPT_PREFIX,'Roter Panda.']
    assert tts.prompt_parts('')==[]
    assert 'Das Kind sieht den Hund.' in texts and 'Das Kind schaut zu dem Hund.' in texts
    assert 'die Hunde.' in texts, 'Mehrzahl muss für die Mehrzahl-Aufgabe gesprochen werden können'
    assert tts.plural_phrase({'plural':'Katzen'})=='die Katzen.'
    assert tts.plural_phrase({'plural':'Autos','pluralWithArticle':'die Autos'})=='die Autos.'


def check_parallel_audio():
    """Mehrere Worker müssen dieselben Clips liefern wie ein einzelner."""
    assert tts.default_workers()>=1 and tts.threads_per_worker(4)>=1
    assert tts.threads_per_worker(1)==max(1, os.cpu_count() or 2)
    gesehen=[]

    class FakeProcess:
        instances=[]

        def __init__(self, threads=0):
            self.threads=threads
            FakeProcess.instances.append(self)

        def stop(self):
            pass

    def fake_render(text, cache_dir, process):
        gesehen.append((text,process.threads))
        return b'x'*700

    echter_render, echter_klasse = tts._render, tts._PiperProcess
    tts._render, tts._PiperProcess = fake_render, FakeProcess
    try:
        viele=[f'Text {i}.' for i in range(12)]
        out=tts.synthesize_many(viele,None,workers=3)
        assert list(out)==viele, 'Reihenfolge muss erhalten bleiben'
        assert len(FakeProcess.instances)==3, f'Es müssen 3 Worker sein, waren {len(FakeProcess.instances)}'
        assert all(p.threads==tts.threads_per_worker(3) for p in FakeProcess.instances)
        assert sorted(text for text,_ in gesehen)==sorted(viele), 'Kein Text darf doppelt oder fehlen'
        assert len(gesehen)==len(viele)
    finally:
        tts._render, tts._PiperProcess = echter_render, echter_klasse


def check_sentence_case():
    """Dieselbe Regel wie maskedCaseSentence() in der Lernkarten-Vorlage.

    Der Druck maskiert die Kasusform im Satz. Fehlt sie, bleibt die Karte ohne
    Satzkontext. Ein fehlendes Muster muss auffallen, ein flektiertes Nomen darf
    nicht als Fehler gemeldet werden.
    """
    ok=lambda text,article,kind,word: editor.sentence_has_case(text,article,kind,word)
    assert ok('Das Kind findet den Bären.','der','acc','Bär'), 'schwaches Nomen (Bär -> Bären)'
    assert ok('Das Kind sieht den Roten Panda.','der','acc','Roter Panda'), 'mehrteiliges Wort mit Adjektiv'
    assert not ok('Das Kind trinkt Milch.','der','acc','Hund'), 'fehlende Kasusform muss auffallen'
    assert not ok('Nach dem Blitz kommt der Donner.','der','dat','Hund'), 'fremde Wortgruppe zählt nicht'
    fehler=[]
    for pfad in sorted((ROOT/'themes').glob('*.json')):
        doc=json.loads(pfad.read_text(encoding='utf-8'))
        for theme in (doc if isinstance(doc,list) else doc.get('themes',[doc])):
            for e in theme.get('entries',[]):
                for kind,feld,label in (('acc','accusativeSentence','Akkusativ'),('dat','dativeSentence','Dativ')):
                    if not editor.sentence_has_case(e.get(feld,''),e.get('article'),kind,e.get('word')):
                        fehler.append(f"{pfad.name}: {e.get('word')} ({label})")
    assert not fehler, f'Sätze ohne Kasusmuster: {fehler[:5]}'


def check_build_audio():
    """Der Builder muss MP3-Data-URIs einbetten, ohne echte Stimme zu brauchen."""
    echter_probe, echter_synth = build_simple.probe, build_simple.synthesize_many
    build_simple.probe = lambda: (True,'Testmock')
    build_simple.synthesize_many = lambda texts,cache,progress=None: {
        text: b'ID3\x04\x00\x00\x00\x00\x00\x00'+b'\xff\xfb\x90\x00'+bytes(600) for text in texts if text}
    try:
        tts_doc=build_simple.build_audio([{'entries':[{'word':'Hund','article':'der',
            'accusativeSentence':'Das Kind sieht den Hund.','dativeSentence':'Das Kind schaut zu dem Hund.'}]}],ROOT/'tts-cache')
    finally:
        build_simple.probe, build_simple.synthesize_many = echter_probe, echter_synth
    assert tts_doc['mode']=='embedded-piper-mp3', tts_doc['mode']
    assert tts_doc['engine']==tts.ENGINE and tts_doc['voice']==tts.VOICE
    assert tts_doc['bitrate']==tts.MP3_BITRATE and tts_doc['sampleRate']==tts.MP3_SAMPLE_RATE
    werte=list(tts_doc['audioByText'].values())
    assert werte and all(v.startswith('data:audio/mpeg;base64,') for v in werte), werte[:1]
    assert not any('audio/wav' in v or 'mbrola' in v for v in werte), 'Kein WAV/MBROLA mehr einbetten'


def check_vorlage_aufbau():
    """Die Vorlage muss die Daten in der richtigen Reihenfolge einbetten.

    Themen stehen im Hauptskript, die Audioclips erst am Dateiende: der Browser
    liest eine 37-MB-Datei von der Platte, und die Karten sollen nicht warten,
    bis die 26 MB Ton gelesen sind. Kommen die Klänge nach vorn, steigt die
    Wartezeit bis zum ersten Blatt wieder auf das Doppelte.
    """
    vorlage=(ROOT/'der_die_das_template.html').read_text(encoding='utf-8')
    assert vorlage.count(build_simple.THEME_MARKER)==1, 'Themen-Marker fehlt oder doppelt'
    assert vorlage.count(build_simple.TTS_MARKER)==1, 'Ton-Marker fehlt oder doppelt'
    themen=vorlage.index('const BUILTIN_THEMES')
    block=vorlage.index('id="ttsData"')
    assert block>themen, 'Der Ton-Block muss nach den Themes stehen'
    assert 'ladeTon(daten)' in vorlage[block:], 'Nachlauf für die Tondaten fehlt'
    assert 'let EMBEDDED_TTS' in vorlage, 'EMBEDDED_TTS muss veränderlich sein (ladeTon)'
    return 'Vorlage: Themes im Skript, Ton am Dateiende'


MAX_WOERTER=25


def theme_limits():
    """Wortgrenze je Thema aus dem Deck-Plan (Vorgabe 25, „max“ erhöht sie).

    Einzelne Themen dürfen größer sein - der Körper hat über 40 Körperteile
    und bekommt im Druck dann einfach mehrere Blätter.
    """
    grenzen={}
    for pfad in sorted((ROOT/'tools/decks').glob('*.json')):
        doc=json.loads(pfad.read_text(encoding='utf-8'))
        for theme in doc.get('themes',[]):
            grenzen[str(theme.get('id'))]=int(theme.get('max') or MAX_WOERTER)
    return grenzen


def check_decks():
    """Deck-Regeln: höchstens 25 Wörter, ein Bild = ein Wort, saubere Grammatik.

    Ein Thema ist eine Lektion. Teilen sich zwei Wörter eines Themas ein Bild,
    ist im Spiel nicht entscheidbar, welches gemeint ist; deshalb prüft dieser
    Test die Bilddopplung auf den fertigen Build-Daten.
    """
    grenzen=theme_limits()
    for pfad in sorted((ROOT/'themes').glob('*.json')):
        doc=json.loads(pfad.read_text(encoding='utf-8'))
        for theme in (doc if isinstance(doc,list) else doc.get('themes',[doc])):
            woerter=[str(e.get('word','')) for e in theme.get('entries',[])]
            # theme-65-koerper.json -> koerper
            kennung=str(theme.get('themeId') or pfad.stem).split('-',2)[-1]
            grenze=grenzen.get(kennung,MAX_WOERTER)
            assert len(woerter)<=grenze, f"{pfad.name}: {len(woerter)} Wörter (höchstens {grenze})"
            gefaltet=[w.casefold() for w in woerter]
            assert len(gefaltet)==len(set(gefaltet)), f"{pfad.name}: doppelte Wörter"

    for pfad in sorted((ROOT/'selected-themes').glob('*.json')):
        doc=json.loads(pfad.read_text(encoding='utf-8'))
        for theme in (doc if isinstance(doc,list) else doc.get('themes',[doc])):
            bilder={}
            for e in theme.get('entries',[]):
                quelle=str(e.get('imageSource') or '')
                if not quelle:
                    continue
                assert quelle not in bilder, (
                    f"{pfad.name}: gleiches Bild für „{bilder[quelle]}“ und „{e.get('word')}“")
                bilder[quelle]=e.get('word')


def check_dictionary():
    """Artikel und Mehrzahl gegen das Offline-Wörterbuch prüfen.

    Ohne Wörterbuchdatei wird nur die Struktur geprüft - CI hat keinen Dump.
    """
    sys.path.insert(0,str(ROOT/'tools'))
    import audit_words
    pfad=ROOT/'dictionary'/'nouns.json'
    if not pfad.exists():
        return 'Wörterbuch fehlt, Grammatikprüfung übersprungen'
    report=audit_words.Report(dic=audit_words.load_dictionary(pfad))
    report.plural_index=audit_words.build_plural_index(report.dic)
    for _,theme,entry in audit_words.load_entries(ROOT/'themes'):
        audit_words.check_entry(report,theme,entry)
    fehler=[f for f in report.findings if f.kind not in audit_words.NOTE_KINDS]
    assert not fehler, f"Wörterbuch-Abweichungen: {[f'{f.word}: {f.detail}' for f in fehler[:5]]}"
    return f"{report.total} Einträge, {len(report.findings)} Hinweise"


def check_werkstatt_bilder():
    """Der Deck-Bau darf die Bildwahl der Werkstatt nicht überschreiben.

    Der Plan entscheidet nur über Wörter, die noch kein Bild haben. Hat die
    Werkstatt eins gewählt (image-library/selections.json), bleibt genau dieses
    Bild stehen - auch wenn der Plan einen anderen Katalogtreffer vorschlägt.
    Sonst wären handgezeichnete Bilder (ClipSafari) nach einem Deck-Bau weg.
    """
    vorhanden=build_decks.werkstatt_bilder()
    if not vorhanden:
        return 'keine Werkstatt-Bildwahl vorhanden'
    # Ein Bild, das zwei *verschiedene* Wörter belegen, ist ein Datenfehler: dann
    # darf der Bau umverteilen. Dasselbe Wort in zwei Themen behält sein Bild.
    doppelt={}
    for (kennung,wort),wahl in vorhanden.items():
        doppelt.setdefault(str(wahl.get('slug') or ''),set()).add(wort)
    dictionary=json.loads((ROOT/'dictionary'/'nouns.json').read_text(encoding='utf-8'))
    sentences=build_decks.load_sentences(ROOT/'tools'/'saetze')
    plans,_=build_decks.build(ROOT/'tools'/'decks',dictionary,sentences,False,vorhanden=vorhanden)
    unangetastet=0
    geaendert=[]
    for plan in plans:
        kennung=str(plan['theme']['id'])
        for entry in plan['entries']:
            wahl=vorhanden.get((kennung,entry['word'].casefold())) or {}
            slug=str(wahl.get('slug') or '')
            if not slug or not (ROOT/'image-library'/f'{slug}.json').exists():
                continue
            if len(doppelt.get(slug,set()))>1:
                continue
            unangetastet+=1
            if entry['_slug']!=slug:
                geaendert.append(f"{entry['word']}: {slug} -> {entry['_slug']}")
    assert not geaendert, f'Werkstatt-Bilder überschrieben: {geaendert[:5]}'
    assert unangetastet>0, 'kein einziges Werkstatt-Bild erkannt'
    return f'{unangetastet} Werkstatt-Bilder unangetastet'


def check_bildquellen():
    """Die Suchkataloge der Bildquellen prüfen - vollständig, auflösbar, offline.

    Jede Zeichnung einer Sammlung muss über ihren Slug zu einer Quelle mit
    Lizenzangabe führen; die Indizes halten fest, aus welchem Commit sie kommen.
    """
    sys.path.insert(0,str(ROOT/'tools'))
    import image_providers
    kataloge=ROOT/'tools'/'image-sources'
    for name,mindest in (('catalog.json',1000),('mdi.json',1000),('fluent.json',1000)):
        items=json.loads((kataloge/name).read_text(encoding='utf-8')).get('items') or []
        assert len(items)>=mindest, f'{name}: nur {len(items)} Einträge'
    fluent=json.loads((kataloge/'fluent.json').read_text(encoding='utf-8'))
    assert len(str(fluent.get('ref') or ''))>=7, 'Fluent-Index braucht einen festgehaltenen Commit'
    for row in fluent['items']:
        assert str(row['slug']).startswith('fluent--'), row
        assert str(row['file']).startswith('assets/') and str(row['file']).endswith('.svg'), row
    waffel=image_providers.resolve('fluent--1F9C7')
    assert waffel['license']=='MIT' and waffel['download'].startswith('https://'), waffel
    treffer=[t['slug'] for t in image_providers.search('fluent','waffle')]
    assert 'fluent--1F9C7' in treffer, f'Fluent-Suche findet die Waffel nicht: {treffer[:5]}'
    return (f"3 Kataloge · Fluent {len(fluent['items'])} Zeichnungen, "
            f"Stand {str(fluent['ref'])[:10]}")


def main():
    check_audio()
    check_parallel_audio()
    check_sentence_case()
    check_build_audio()
    check_decks()
    bildhinweis=check_werkstatt_bilder()
    quellen=check_bildquellen()
    hinweis=check_dictionary()
    vorlage=check_vorlage_aufbau()
    z=editor.dictionary_lookup('Zebra')
    assert z['found'] and z['entry']['article']=='das' and z['entry']['plural']=='Zebras'
    demo=editor.audit_theme('theme-50-haustiere.json')
    assert demo['stats']['error']==0, demo
    exported=editor.export_theme('theme-50-haustiere.json')
    data=json.loads(exported.read_text(encoding='utf-8'))
    assert data['entries'] and all('editorType' not in e for e in data['entries'])
    assert all(e.get('imageSvg') for e in data['entries'])
    themes=build_simple.load_themes(ROOT/'selected-themes')
    assert themes
    print(f'OK: Audio-Aufbereitung, Satzmuster, MP3-Build-Eingabe, Wörterbuch, Audit, Export '
          f'und Bildschutz geprüft. ({hinweis}, {bildhinweis})')
    print(f'OK: {quellen}')
    print(f'OK: {vorlage}')


if __name__=='__main__':
    main()
