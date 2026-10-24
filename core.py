"""RWS waterhoogte en vensterlogica; niet gebruiken als vaarvrijgave."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bisect import bisect_left
import requests

TZ=ZoneInfo('Europe/Amsterdam')
API='https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen'
CATALOG='https://ddapi20-waterwebservices.rijkswaterstaat.nl/METADATASERVICES/OphalenCatalogus'
NAP_DIEPTE=4.0
MAX_GAP=timedelta(minutes=30)


def station_codes():
    r=requests.post(CATALOG,json={'CatalogusFilter':{'Compartimenten':True,'Grootheden':True}},timeout=25)
    r.raise_for_status()
    data=r.json()
    return [(x.get('Code',''),str(x.get('Naam') or x.get('Omschrijving') or '')) for x in data.get('LocatieLijst',[]) if 'scheven' in (x.get('Code','')+' '+str(x.get('Naam') or x.get('Omschrijving') or '')).lower()]


def get_points(begin,eind,station,proces):
    body={'Locatie':{'Code':station},'AquoPlusWaarnemingMetadata':{'AquoMetadata':{'Compartiment':{'Code':'OW'},'Grootheid':{'Code':'WATHTE'},'ProcesType':proces}},'Periode':{'Begindatumtijd':begin.isoformat(timespec='milliseconds'),'Einddatumtijd':eind.isoformat(timespec='milliseconds')}}
    r=requests.post(API,json=body,timeout=30)
    if r.status_code==204: return []
    r.raise_for_status()
    data=r.json()
    if data.get('Succesvol') is False: raise RuntimeError(str(data.get('Foutmelding') or data)[:400])
    result={}
    for serie in data.get('WaarnemingenLijst',[]):
        meta=serie.get('AquoPlusWaarnemingMetadata',{}).get('AquoMetadata',{})
        if meta.get('Eenheid',{}).get('Code','cm')!='cm' or meta.get('Hoedanigheid',{}).get('Code','NAP')!='NAP':continue
        for item in serie.get('MetingenLijst',[]):
            if str(item.get('Kwaliteitswaardecode',{}).get('Code','00')) not in ('00','10','20','25','30','40'):continue
            try:
                h=float(item['Meetwaarde']['Waarde_Numeriek'])
                t=datetime.fromisoformat(item['Tijdstip']).astimezone(TZ)
                if -500<h<500: result[t]=h
            except (TypeError,ValueError,KeyError):pass
    return sorted(result.items())


def height_at(points,t):
    ts=[p[0] for p in points];i=bisect_left(ts,t)
    if i<len(points) and points[i][0]==t:return points[i][1]
    if i==0 or i==len(points):return None
    t0,h0=points[i-1];t1,h1=points[i]
    if not timedelta(0)<t1-t0<=MAX_GAP:return None
    return h0+(h1-h0)*(t-t0)/(t1-t0)


def safe_windows(points,start,end,min_cm):
    # Evaluate each continuous valid segment separately, with precise threshold crossings.
    windows=[];opened=None;prior_end=None
    for (t0,h0),(t1,h1) in zip(points,points[1:]):
        if t1<=start or t0>=end:continue
        if t1-t0>MAX_GAP or t1<=t0:
            if opened is not None:
                windows.append((opened,prior_end or t0));opened=None
            prior_end=None;continue
        a=max(start,t0);b=min(end,t1)
        if a>=b:continue
        if opened is not None and prior_end is not None and a>prior_end:
            windows.append((opened,prior_end));opened=None
        ha=h0+(h1-h0)*(a-t0)/(t1-t0)
        hb=h0+(h1-h0)*(b-t0)/(t1-t0)
        if ha>=min_cm and opened is None:opened=a
        if (ha>=min_cm)!=(hb>=min_cm):
            crossing=a+(b-a)*((min_cm-ha)/(hb-ha))
            if ha>=min_cm:
                windows.append((opened,crossing));opened=None
            else:opened=crossing
        prior_end=b
    if opened is not None:windows.append((opened,prior_end))
    return [(a,b) for a,b in windows if a is not None and b is not None and b>a]


def clock(t):return t.strftime('%a %d-%m %H:%M')


def find_options(windows,target,n=3):
    previous=[(a,b) for a,b in windows if b<=target]
    later=[(a,b) for a,b in windows if a>=target]
    return previous[-n:][::-1],later[:n]
