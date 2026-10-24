from datetime import datetime,timedelta,date,time
from zoneinfo import ZoneInfo
import streamlit as st
from core import TZ,NAP_DIEPTE,station_codes,get_points,height_at,safe_windows,find_options,clock

st.set_page_config(page_title='Scheveningen | Vertrekcheck',page_icon='⛵',layout='centered')
st.title('⛵ Scheveningen — vertrekcheck')
st.caption('Tweede haven · indicatieve kielspeling boven de pijp · Nederlandse lokale tijd')
st.warning('Dit is GEEN vaarvrijgave. Controleer de actuele pijphoogte/diepte, lokale peilverschillen, golven, squat en havenbeperkingen. RWS-metingen zijn niet automatisch de waterstand direct boven de pijp.')
with st.form('vertrekcheck'):
    c1,c2=st.columns(2)
    with c1:
        chosen_date=st.date_input('Vertrekdatum',value=date.today(),format='DD-MM-YYYY')
        draft=st.number_input('Diepgang (m)',min_value=0.1,max_value=12.0,value=3.75,step=0.05)
    with c2:
        chosen_time=st.time_input('Gewenste vertrektijd',value=time(12,0),step=300)
        margin=st.number_input('Extra veiligheidsmarge (m)',min_value=0.0,max_value=3.0,value=0.30,step=0.05)
    with st.expander('Geavanceerd'):
        station=st.text_input('RWS stationcode (automatisch zoeken bij lege waarde)',value='').strip()
        back=st.number_input('Zoek uren eerder',min_value=6,max_value=96,value=36,step=6)
        forward=st.number_input('Zoek uren later',min_value=6,max_value=96,value=36,step=6)
    pressed=st.form_submit_button('Controleer vertrektijd',type='primary',use_container_width=True)

@st.cache_data(ttl=3600,show_spinner=False)
def stations():return station_codes()
@st.cache_data(ttl=600,show_spinner=False)
def load_points(b,e,code,proces):return get_points(b,e,code,proces)

if pressed:
    naive=datetime.combine(chosen_date,chosen_time)
    departure=naive.replace(tzinfo=TZ)
    if departure.astimezone(ZoneInfo('UTC')).astimezone(TZ).replace(tzinfo=None)!=naive:
        st.error('Deze lokale tijd bestaat niet door de overgang naar zomertijd.');st.stop()
    if departure.fold==0 and naive.replace(tzinfo=TZ,fold=0).utcoffset()!=naive.replace(tzinfo=TZ,fold=1).utcoffset():
        st.warning('Deze tijd valt in de wintertijdomschakeling en komt tweemaal voor; de eerste keer is gekozen.')
    begin=departure-timedelta(hours=back)
    end=departure+timedelta(hours=forward)
    with st.spinner('Waterstanden ophalen bij Rijkswaterstaat…'):
        try:
            codes=stations() if not station else []
            if not station:
                if len(codes)==1:station=codes[0][0]
                else:
                    st.error('RWS-station voor Scheveningen kon niet eenduidig worden bepaald. Gevonden stations: '+str(codes)+'. Vul de juiste stationcode in onder Geavanceerd.');st.stop()
            now=datetime.now(TZ)
            processes=['verwachting','astronomisch'] if departure>now else ['meting','verwachting','astronomisch']
            selected=[];source=None;errors=[]
            for proc in processes:
                try:
                    arr=load_points(begin,end,station,proc)
                    if height_at(arr,departure) is not None:
                        selected=arr;source=proc;break
                    errors.append(proc+': geen gegevens voor het gevraagde tijdstip')
                except Exception as ex:errors.append(proc+': '+str(ex)[:180])
            if not selected:
                st.error('Geen betrouwbare waterhoogte gevonden. Er wordt geen JA of NEE gegeven.')
                st.write('Station:',station,'— details:', '; '.join(errors));st.stop()
        except Exception as ex:
            st.error('RWS-koppeling mislukt: '+str(ex));st.stop()
    h=height_at(selected,departure)
    needed_cm=(draft+margin-NAP_DIEPTE)*100
    clearance=NAP_DIEPTE+h/100-draft
    st.subheader('Resultaat')
    if clearance>=margin:
        st.success(f'JA — volgens het berekende dieptemodel voldoende water. Kielspeling: {clearance:.2f} m.')
    else:
        st.error(f'NEE — volgens het dieptemodel onvoldoende water. Tekort inclusief veiligheidsmarge: {margin-clearance:.2f} m.')
    a,b,c=st.columns(3)
    a.metric('Waterhoogte',f'{h:+.0f} cm NAP')
    b.metric('Waterdiepte',f'{NAP_DIEPTE+h/100:.2f} m')
    c.metric('Vereist peil',f'{needed_cm:+.0f} cm NAP')
    st.caption(f'Bron: RWS · station {station} · type {source} · lineair geïnterpoleerd tussen meet-/rekenpunten. ' + ('Astronomisch getij bevat geen weersinvloeden.' if source=='astronomisch' else ''))
    windows=safe_windows(selected,begin,end,needed_cm)
    if clearance<margin:
        earlier,later=find_options(windows,departure,3)
        c1,c2=st.columns(2)
        with c1:
            st.subheader('← Eerdere opties')
            if earlier:
                for x,y in earlier:st.write(f'**{clock(x)}** tot **{clock(y)}**')
            else:st.info('Geen vensters in de beschikbare reeks.')
        with c2:
            st.subheader('Latere opties →')
            if later:
                for x,y in later:st.write(f'**{clock(x)}** tot **{clock(y)}**')
            else:st.info('Geen vensters in de beschikbare reeks.')
    else:
        st.info('Dit gekozen vertrektijdstip valt binnen een berekend geschikt venster.')
    with st.expander('Alle gevonden vensters'):
        for x,y in windows:st.write(f'{clock(x)} – {clock(y)}')
    try:
        import pandas as pd
        df=pd.DataFrame({'tijd':[x for x,_ in selected],'Waterstand (cm NAP)':[y for _,y in selected]}).set_index('tijd')
        st.line_chart(df)
        st.caption('De grafiek toont de complete opgehaalde waterstandreeks; controleer de grenswaarde hierboven.')
    except ImportError:pass
st.markdown('[Waterinfo Scheveningen](https://waterinfo.rws.nl/publiek/waterhoogte/scheveningen/details) · [RWS API-documentatie](https://rijkswaterstaatdata.nl/waterdata/)')
