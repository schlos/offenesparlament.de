import sys
import logging
from collections import defaultdict
from datetime import datetime

import sqlaload as sl

from offenesparlament.core import etl_engine

from offenesparlament.core import db
from offenesparlament.model import Gremium, Person, Rolle, \
        Wahlkreis, Ablauf, \
        Position, Beschluss, Beitrag, Zuweisung, Referenz, Dokument, \
        Schlagwort, Sitzung, Debatte, Zitat, Stimme, Abstimmung
from offenesparlament.model.person import obleute, mitglieder, \
        stellvertreter

log = logging.getLogger(__name__)


def load_ablaeufe(engine):
    _Ablauf = sl.get_table(engine, 'ablauf')

    for i, data in enumerate(sl.find(engine, _Ablauf, wahlperiode=str(17))):
        log.info("Loading Ablauf: %s - %s..." % (data['key'], data['titel']))
        load_ablauf(engine, data)
        if i % 500 == 0:
            db.session.commit()
    db.session.commit()


def load_ablauf(engine, data):
    ablauf = Ablauf.query.filter_by(
            wahlperiode=data.get('wahlperiode'),
            key=data.get('key')).first()
    if ablauf is None:
        ablauf = Ablauf()

    ablauf_id = data.get('ablauf_id')
    ablauf.key = data.get('key')
    ablauf.source_url = data.get('source_url')
    ablauf.wahlperiode = data.get('wahlperiode')
    ablauf.typ = data.get('typ')
    ablauf.klasse = data.get('class')
    ablauf.titel = data.get('titel')
    if not len(ablauf.titel):
        log.error("No titel!")
        return

    ablauf.initiative = data.get('initiative')
    ablauf.stand = data.get('stand')
    ablauf.signatur = data.get('signatur')
    ablauf.gesta_id = data.get('gesta_id')
    ablauf.eu_dok_nr = data.get('eu_dok_nr')
    ablauf.eur_lex_url = data.get('eur_lex_url')
    ablauf.eur_lex_pdf = data.get('eur_lex_pdf')
    ablauf.consilium_url = data.get('consilium_url')
    ablauf.abstrakt = data.get('abstrakt')
    ablauf.zustimmungsbeduerftig = data.get('zustimmungsbeduerftig')
    ablauf.sachgebiet = data.get('sachgebiet')
    ablauf.abgeschlossen = True if str(data.get('abgeschlossen')) \
            == 'True' else False
    db.session.add(ablauf)
    db.session.flush()

    worte = []
    _Schlagwort = sl.get_table(engine, 'schlagwort')
    for sw in sl.find(engine, _Schlagwort, wahlperiode=ablauf.wahlperiode,
            key=ablauf.key):
        wort = Schlagwort()
        wort.name = sw['wort']
        db.session.add(wort)
        worte.append(wort)
    ablauf.schlagworte = worte

    _Referenz = sl.get_table(engine, 'referenz')
    for ddata in sl.find(engine, _Referenz, wahlperiode=ablauf.wahlperiode,
            ablauf_key=ablauf.key):
        dokument = load_dokument(ddata, engine)
        referenz = Referenz.query.filter_by(
                dokument=dokument,
                seiten=ddata.get('seiten'),
                ).filter(Referenz.ablaeufe.any(id=ablauf.id)).first()
        if referenz is None:
            referenz = Referenz()
            referenz.ablaeufe.append(ablauf)
            referenz.dokument = dokument
        referenz.seiten = ddata.get('seiten')
        referenz.text = ddata.get('text')

    _Position = sl.get_table(engine, 'position')
    for position in sl.find(engine, _Position, ablauf_id=ablauf_id):
        load_position(position, ablauf_id, ablauf, engine)

    db.session.commit()


def load_position(data, ablauf_id, ablauf, engine):
    position = Position.query.filter_by(
            ablauf=ablauf,
            urheber=data.get('urheber'),
            fundstelle=data.get('fundstelle')).first()
    if position is not None:
        return
    position = Position()
    position.key = data.get('hash')
    position.zuordnung = data.get('zuordnung')
    position.urheber = data.get('urheber')
    position.fundstelle = data.get('fundstelle')
    position.fundstelle_url = data.get('fundstelle_url')
    position.date = date(data.get('date'))
    position.quelle = data.get('quelle')
    position.typ = data.get('typ')
    position.ablauf = ablauf

    if data.get('debatte_item_id'):
        dq = Debatte.query.filter(Debatte.nummer==data.get('debatte_item_id'))
        dq = dq.join(Sitzung)
        dq = dq.filter(Sitzung.wahlperiode==data.get('debatte_wp'))
        dq = dq.filter(Sitzung.nummer==data.get('debatte_session'))
        position.debatte = dq.first()

    _Referenz = sl.get_table(engine, 'referenz')
    for ddata in sl.find(engine, _Referenz, fundstelle=position.fundstelle,
            urheber=position.urheber, ablauf_id=ablauf_id):
        position.dokument = load_dokument(ddata, engine)

    db.session.add(position)

    _Zuweisung = sl.get_table(engine, 'zuweisung')
    for zdata in sl.find(engine, _Zuweisung, fundstelle=position.fundstelle,
            urheber=position.urheber, ablauf_id=ablauf_id):
        zuweisung = Zuweisung()
        zuweisung.text = zdata['text']
        zuweisung.federfuehrung = True if \
                str(zdata['federfuehrung']) == 'True' else False
        zuweisung.gremium = Gremium.query.filter_by(
                key=zdata.get('gremium_key')).first()
        zuweisung.position = position
        db.session.add(zuweisung)

    _Beschluss = sl.get_table(engine, 'beschluss')
    for bdata in sl.find(engine, _Beschluss, fundstelle=position.fundstelle,
            urheber=position.urheber, ablauf_id=ablauf_id):
        beschluss = Beschluss()
        beschluss.position = position
        beschluss.seite = bdata['seite']
        beschluss.tenor = bdata['tenor']
        beschluss.dokument_text = bdata['dokument_text'] or ''
        for dokument_name in beschluss.dokument_text.split(','):
            dokument_name = dokument_name.strip()
            dok = Dokument.query.filter_by(nummer=dokument_name).first()
            if dok is not None:
                beschluss.dokumente.append(dok)
        db.session.add(beschluss)

    _Beitrag = sl.get_table(engine, 'beitrag')
    for bdata in sl.find(engine, _Beitrag, fundstelle=position.fundstelle,
            urheber=position.urheber, ablauf_id=ablauf_id, matched=True):
        load_beitrag(bdata, position, engine)


def load_beitrag(data, position, engine):
    beitrag = Beitrag()
    beitrag.seite = data.get('seite')
    beitrag.art = data.get('art')
    beitrag.position = position

    beitrag.person = Person.query.filter_by(
            fingerprint=data.get('fingerprint')
            ).first()
    beitrag.rolle = Rolle.query.filter_by(
            person=beitrag.person,
            funktion=data.get('funktion'),
            ressort=data.get('ressort'),
            land=data.get('land')).first()
    db.session.add(beitrag)


def load_dokument(data, engine):
    dokument = Dokument.query.filter_by(
            hrsg=data.get('hrsg'),
            typ=data.get('typ'),
            nummer=data.get('nummer')).first()
    if dokument is None:
        dokument = Dokument()
        dokument.hrsg = data.get('hrsg')
        dokument.typ = data.get('typ')
        dokument.nummer = data.get('nummer')
    if data.get('link'):
        dokument.link = data.get('link')
    db.session.add(dokument)
    db.session.flush()
    return dokument


