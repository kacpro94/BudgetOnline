import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import traceback
import altair as alt
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Budżet (Google Sheets)", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GdbHX0mKbwyJhjmcG3jgtN9E8BJVSSunRYvfSLUjSIc/edit?usp=sharing"  # <--- WAŻNE: Wklej link!
WORKSHEET_NAME = "dane"


LISTA_KATEGORII = [
    'Nieistotne', 'Wynagrodzenie', 'Wpływy', 'Elektronika', 'Wyjścia i wydarzenia',
    'Żywność i chemia domowa', 'Przejazdy', 'Sport i hobby ', 'Wpływy - inne',
    'Odzież i obuwie', 'Podróże i wyjazdy', 'Rozrywka', 'Zdrowie i uroda',
    'Regularne oszczędzanie', 'Serwis i części', 'Multimedia, książki i prasa',
    'Wypłata gotówki', 'Opłaty i odsetki', 'Auto i transport - inne',
    'Czynsz i wynajem', 'Paliwo', 'Akcesoria i wyposażenie ',
    'Jedzenie poza domem', 'Prezenty i wsparcie', 'Bez kategorii','ZaMieszkanie'
]




def wyczysc_kwote(wartosc):
    if pd.isna(wartosc) or wartosc == "":
        return 0.0
    
    # Jeśli to już jest liczba, zwracamy jako float
    if isinstance(wartosc, (int, float)):
        return float(wartosc)
    
    # Konwersja na tekst
    s = str(wartosc)
    
    # 1. Usuwamy waluty i śmieci tekstowe
    s = s.replace(" PLN", "").replace(" zł", "").replace("PLN", "")
    
    # 2. Usuwamy spacje (zwykłe i tzw. twarde spacje bankowe \xa0)
    s = s.replace(" ", "").replace("\xa0", "")
    
    # 3. Zamieniamy przecinek na kropkę (kluczowy moment!)
    s = s.replace(",", ".")
    
    try:
        return float(s)
    except ValueError:
        return 0.0

def pobierz_dane():
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(columns=['id', 'data', 'kategoria', 'opis', 'kwota'])

        df.columns = df.columns.str.lower().str.strip()
        df['data'] = pd.to_datetime(df['data'], errors='coerce')
        

        df['kwota'] = df['kwota'].apply(wyczysc_kwote)
        
        df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
        
        return df
    except Exception as e:
        st.error(f"⚠️ Błąd pobierania danych: {e}")
        return pd.DataFrame(columns=['id', 'data', 'kategoria', 'opis', 'kwota'])

def zapisz_calosc(df_to_save):
    """Nadpisuje cały arkusz (używane przy edycji tabeli i imporcie CSV)."""
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        df_export = df_to_save.copy()
        df_export['data'] = df_export['data'].dt.strftime('%Y-%m-%d')
        
        headers = df_export.columns.tolist()
        values = df_export.values.tolist()
        
        worksheet.clear()
        worksheet.update([headers] + values)
        
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"❌ Błąd zapisu do Google Sheets: {e}")

def dodaj_wiersz(nowy_wiersz_dict):
    """Dodaje jeden wiersz na koniec (używane w 'Dodaj ręcznie')."""
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        
        # Formatowanie wartości
        values = [
            int(nowy_wiersz_dict['id']),
            nowy_wiersz_dict['data'].strftime('%Y-%m-%d'),
            str(nowy_wiersz_dict['kategoria']),
            str(nowy_wiersz_dict['opis']),
            float(nowy_wiersz_dict['kwota'])
        ]
        
        worksheet.append_row(values)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ Błąd dodawania wiersza: {e}")


def przetworz_csv(uploaded_file):
    uploaded_file.seek(0)
    try:
        # PODEJŚCIE 1 (mBank)
        dane = pd.read_csv(uploaded_file, delimiter=';', encoding='utf-8', index_col=False, skiprows=25)
        dane.columns = dane.columns.str.replace("#", "").str.strip()
        
        dane = dane.rename(columns={
            'Data operacji': 'data', 'Opis operacji': 'opis',
            'Kwota': 'kwota', 'Kategoria': 'kategoria'
        })

        if 'Rachunek' in dane.columns:
            dane = dane.drop('Rachunek', axis=1)

        if dane['data'].isna().any():
            pierwszy_pusty = dane[dane['data'].isna()].index[0]
            dane = dane.iloc[:pierwszy_pusty]

        dane['data'] = pd.to_datetime(dane['data'],  errors='coerce')
        
        dane['kwota'] = dane['kwota'].apply(wyczysc_kwote)
        
        if 'kategoria' not in dane.columns: dane['kategoria'] = "Bez kategorii"
        else: dane['kategoria'] = dane['kategoria'].fillna("Bez kategorii")
        
        dane = dane.dropna(subset=['data'])
        return dane[['data', 'kategoria', 'opis', 'kwota']]

    except Exception:

        uploaded_file.seek(0)
        dane = pd.read_csv(uploaded_file, encoding='cp1250', delimiter=';', index_col=False, skiprows=19)
        dane.columns = dane.columns.str.replace("#", "").str.strip()
        
        dane = dane.rename(columns={
            'Data transakcji': 'data', 'Dane kontrahenta': 'opis',
            'Kwota transakcji (waluta rachunku)': 'kwota'
        })

        if dane['data'].isna().any():
            pierwszy_pusty = dane[dane['data'].isna()].index[0]
            dane = dane.iloc[:pierwszy_pusty]

        dane['data'] = pd.to_datetime(dane['data'], errors='coerce')
        dane = dane.dropna(subset=['data'])
        
        dane['kategoria'] = "Bez kategorii"
        dane["opis"] = "ING " + dane["opis"].fillna("")
        
        dane['kwota'] = dane['kwota'].apply(wyczysc_kwote)
        dane['kwota'] = dane['kwota'] / 2

        return dane[['data', 'kategoria', 'opis', 'kwota']]
    


# ==========================================
# GŁÓWNA LOGIKA APLIKACJI
# ==========================================

st.sidebar.title("Nawigacja")
st.sidebar.text("Wybór banku")
ing = st.sidebar.checkbox("ING", value=True, key="bank_ing")
mbank = st.sidebar.checkbox("mBank", value=True, key="bank_mbank")

df_full = pobierz_dane()
selected_banks = []
if ing:
    selected_banks.append("ING")
if mbank:
    selected_banks.append("mBank")
strona = st.sidebar.radio("Idź do:", ["Tabela danych", "Wydatki w czasie", "Wydatki według kategorii", "🔧 Panel Admina"])
df_filtered_bank = df_full.copy()

# 2. Filtrujemy tylko kopię roboczą
if len(selected_banks) == 1:
    if selected_banks[0] == 'ING':
        df_filtered_bank = df_filtered_bank[df_filtered_bank['opis'].astype(str).str.contains('ing', case=False, na=False)]
    elif selected_banks[0] == 'mBank':
        df_filtered_bank = df_filtered_bank[~df_filtered_bank['opis'].astype(str).str.contains('ing', case=False, na=False)]

# ------------------------------------------------------------------
# STRONA 1: TABELA DANYCH (View, Import, Edit)
# ------------------------------------------------------------------
if strona == "Tabela danych":
    
    # --- SEKCJA IMPORTU CSV ---
    with st.expander("📥 Wgraj wyciąg z banku (CSV)"):
        uploaded_file = st.file_uploader("Wybierz plik CSV (mBank / ING)", type="csv")
        
        if uploaded_file is not None:
            file_key = f"csv_data_{uploaded_file.name}"
            
            if file_key not in st.session_state:
                st.write("Przetwarzanie pliku...")
                # Tutaj Twoja funkcja z dodanym seek(0) na początku (dla pewności)
                df_new = przetworz_csv(uploaded_file)
                st.session_state[file_key] = df_new
            
            # Pobieramy dane z sesji
            df_to_add = st.session_state[file_key]
            print (df_to_add.tail(5))
            
            if not df_to_add.empty:
                st.write("Podgląd:")
                st.dataframe(df_to_add)
                
                # Przycisk korzysta teraz z danych w session_state, a nie z pliku
                if st.button("🔥 Dodaj te transakcje do chmury"):
                    try:
                        # 1. Obliczamy ID
                        max_id = df_full['id'].max() if not df_full.empty else 0
                        if pd.isna(max_id): max_id = 0
                        
                        # Tworzymy kopię, żeby nie modyfikować oryginału w sesji
                        df_upload = df_to_add.copy()
                        df_upload['id'] = range(int(max_id) + 1, int(max_id) + 1 + len(df_upload))
                        #print(df_upload)
                        # 2. Łączymy stare dane z nowymi
                        df_updated = pd.concat([df_full, df_upload], ignore_index=True)
                        print(df_updated)
                        # 3. Zapisujemy całość
                        zapisz_calosc(df_updated)
                        
                        st.success(f"Dodano {len(df_upload)} transakcji!")
                        
                        # Czyścimy dane z sesji po udanym zapisie, żeby nie dodać ich 2 razy
                        del st.session_state[file_key]
                        
                        # Odświeżamy aplikację
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Wystąpił błąd podczas zapisu: {e}")
                        st.write(traceback.format_exc()) # Pokaże dokładny błąd
            else:
                st.error("Plik jest pusty lub format nieznany.")

    st.divider()
    st.subheader("📝 Edycja i Przegląd Wydatków")

    # --- FILTRY I DATY (Twoja logika z session_state) ---
    def ustaw_obecny_miesiac():
        dzisiaj = datetime.date.today()
        pierwszy_dzien = dzisiaj.replace(day=1)
        st.session_state['wybrane_daty'] = (pierwszy_dzien, dzisiaj)

    if 'wybrane_daty' not in st.session_state:
        # Domyślnie obecny miesiąc
        dzisiaj = datetime.date.today()
        pierwszy = dzisiaj.replace(day=1)
        st.session_state['wybrane_daty'] = (pierwszy, dzisiaj)

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

    with col_f1:
        filtry_kat = st.multiselect("Kategorie", LISTA_KATEGORII)

    with col_f2:
        date_range = st.date_input("Zakres dat", key="wybrane_daty")

    with col_f3:
        st.write("")
        st.write("")
        st.button("📅 Ten miesiąc", on_click=ustaw_obecny_miesiac)

    df_view = df_filtered_bank.copy()

    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            start_date, end_date = date_range
            maska_daty = (df_view['data'].dt.date >= start_date) & (df_view['data'].dt.date <= end_date)
            df_view = df_view[maska_daty]
        elif len(date_range) == 1:
            start_date = date_range[0]
            maska_daty = (df_view['data'].dt.date == start_date)
            df_view = df_view[maska_daty]

    if filtry_kat:
        df_view = df_view[df_view['kategoria'].isin(filtry_kat)]

    df_view = df_view.sort_values(by='data', ascending=False)

    st.markdown("---")
    suma_widoczna = pd.to_numeric(
        df_view.loc[~df_view['kategoria'].isin(["Bez kategorii", "Regularne oszczędzanie",'Nieistotne']), 'kwota'],
        errors='coerce'
    ).fillna(0).sum()
    Wpływy = df_view.loc[df_view['kategoria'].isin(["Wpływy", "Wynagrodzenie", "Wpływy - inne"]), 'kwota'].sum()
    Wydatki = -df_view.loc[~df_view['kategoria'].isin(["Wpływy", "Wynagrodzenie", "Wpływy - inne","Bez kategorii", "Regularne oszczędzanie",'Nieistotne']), 'kwota'].sum()
    c1, c2, c3 = st.columns(3)
    with c1:
        if suma_widoczna >= 0:
            st.metric("💰 Suma wpływów", f"{suma_widoczna:.2f} PLN")
        else:
            st.metric("💸 Suma wydatków", f"{suma_widoczna:.2f} PLN")
    with c2:
        st.metric("🧾 Wpływy", f"{Wpływy:.2f} PLN")
    with c3:
        st.metric("📊 Wydatki", f"{Wydatki:.2f} PLN")
    st.markdown("---")


    df_edited_result = st.data_editor(
        df_view,
        column_order=["data", "kategoria", "opis", "kwota"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,  
        key="editor_glowny",
        column_config={
            "kwota": st.column_config.NumberColumn("Kwota (PLN)", format="%.2f", step=0.01),
            "data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
            "kategoria": st.column_config.SelectboxColumn("Kategoria", options=LISTA_KATEGORII, required=True)
        }
    )

    if st.button("💾 Zapisz zmiany w chmurze"):
        try:
            # 1. Identyfikujemy wiersze, które były widoczne w edytorze PRZED edycją
            # To są ID, które użytkownik MÓGŁ zmienić lub usunąć.
            ids_in_view_scope = df_view['id'].tolist()
            
            # 2. Tworzymy "Tło" - czyli dane, których użytkownik NIE widział
            # (np. inny bank, inne miesiące, ukryte kategorie). Tych danych NIE WOLNO RUSZAĆ.
            df_background = df_full[~df_full['id'].isin(ids_in_view_scope)]
            
            # 3. Pobieramy to, co użytkownik edytował (wynik z edytora)
            df_changes = df_edited_result.copy()
            
            # 4. Obsługa nowych ID dla nowych wierszy
            max_id = df_full['id'].max() if not df_full.empty else 0
            if pd.isna(max_id): max_id = 0
            
            df_changes = df_changes.reset_index(drop=True)
            for idx, row in df_changes.iterrows():
                curr_id = row['id']
                if pd.isna(curr_id) or curr_id == 0:
                    max_id += 1
                    df_changes.at[idx, 'id'] = int(max_id)
            
            # 5. ŁĄCZENIE: Tło (nienaruszone) + Zmiany (edytowane/nowe)
            # Jeśli użytkownik usunął wiersz w edytorze, nie ma go w df_changes, 
            # a skoro był w ids_in_view_scope, to nie ma go też w df_background.
            # Więc zostanie poprawnie usunięty z całości.
            df_final = pd.concat([df_background, df_changes], ignore_index=True)
            
            # Sortowanie dla porządku
            df_final = df_final.sort_values(by='data', ascending=False)
            
            # Zapisz CAŁOŚĆ
            zapisz_calosc(df_final)
            
            st.success("✅ Zapisano bezpiecznie! (Ukryte dane innych banków/dat zostały zachowane)")
            st.rerun()
            
        except Exception as e:
            st.error(f"Błąd zapisu: {e}")
            st.write(traceback.format_exc())
        

# ------------------------------------------------------------------
# STRONA 2: STATYSTYKI
# ------------------------------------------------------------------

elif strona == "Wydatki w czasie":
    st.title("📊 Analiza wydatków w czasie")

    
    def ustaw_obecny_rok():
        dzis = datetime.date.today()
        pierwszy = dzis - relativedelta(years=1)
        st.session_state['wybrane_daty'] = (pierwszy, dzis)

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

    with col_f1:
        filtry_kat = st.multiselect("Kategorie", LISTA_KATEGORII)

    with col_f2:
        date_range = st.date_input("Zakres dat", key="wybrane_daty")

    with col_f3:
        st.write("")
        st.write("")
        st.button("📅 Ten rok", on_click=ustaw_obecny_rok)

    if 'wybrane_daty' not in st.session_state:
        dzis=datetime.date.today()
        pierwszy_month=dzis.replace(month=1,day=1)
        st.session_state['wybrane_daty']=(pierwszy_month,dzis)


    
    if df_full.empty:
        st.info("Brak danych do wykresu.")
    else:
   
        df_stats = df_full.copy()
        df_stats= df_stats[~df_stats['kategoria'].isin(['Nieistotne','Bez kategorii','Regularne oszczędzanie'])]
        if isinstance(date_range, tuple):
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_stats = df_stats[(df_stats['data'].dt.date >= start_date) & (df_stats['data'].dt.date <= end_date)]
            elif len(date_range) == 1:
                start_date = date_range[0]
                df_stats = df_stats[df_stats['data'].dt.date == start_date]

        if filtry_kat:
            df_stats = df_stats[df_stats['kategoria'].isin(filtry_kat)]

 
        df_stats['miesiac'] = df_stats['data'].dt.to_period('M').astype(str)
        wydatki_kat = df_stats.groupby(['miesiac'])['kwota'].sum()
        df_plot = wydatki_kat.reset_index().rename(columns={'kwota': 'kwota', 'miesiac': 'miesiac'})

        klikniecie = alt.selection_point(fields=['miesiac'], name="klik")

        chart = alt.Chart(df_plot).mark_bar().encode(
            x=alt.X('miesiac:N', title='Miesiąc'),
            y=alt.Y('kwota:Q', title='Suma (PLN)'),
            tooltip=[alt.Tooltip('miesiac:N', title='Miesiąc'), alt.Tooltip('kwota:Q', title='Kwota', format='.2f')]
        ).properties(
            title='Wydatki wg miesiąca'
        ).add_params(
            klikniecie 
        ).properties(
            title='Kliknij na słupek, aby zobaczyć szczegóły',
            width=800
        )

        labels = alt.Chart(df_plot).mark_text(dy=5, color='white').encode(
            x='miesiac:N',
            y='kwota:Q',
            text=alt.Text('kwota:Q', format='.2f')
        )

        # # ustawienie stałego koloru słupków (np. granatowy)
        # chart = chart.mark_bar(color="#720094")
        # st.altair_chart(chart + labels, use_container_width=True)

        event = st.altair_chart(
            chart,
            use_container_width=True,
            on_select="rerun"
        )

        # --- 5. ODCZYT DANYCH ---
        wybrany_przedzial = None

        # Sprawdzamy czy w zwróconym obiekcie 'selection' istnieje nasz nazwany selektor "klik"
        if event.selection and "klik" in event.selection:
            # event.selection["klik"] to lista słowników, np. [{'kategoria': 'Jedzenie'}]
            dane_wyboru = event.selection["klik"]
            if dane_wyboru:
                wybrany_przedzial = dane_wyboru[0]["miesiac"]

            # --- 6. TABELA SZCZEGÓŁÓW ---
            if wybrany_przedzial:
                st.divider()
                st.markdown(f"### 🔍 Szczegóły: **{wybrany_przedzial}**")
                
                szczegoly = df_stats[df_stats['miesiac'] == wybrany_przedzial].copy()
                szczegoly = szczegoly.sort_values(by='data', ascending=False)
                
                sum_kat = szczegoly['kwota'].sum()
                st.caption(f"Łączna suma w tym widoku: {-sum_kat:.2f} PLN")

                df_edited_result = st.data_editor(
                szczegoly,
                column_order=["data", "kategoria", "opis", "kwota"],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,  
                key="editor_glowny",
                column_config={
                    "kwota": st.column_config.NumberColumn("Kwota (PLN)", format="%.2f", step=0.01),
                    "data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
                    "kategoria": st.column_config.SelectboxColumn("Kategoria", options=LISTA_KATEGORII, required=True)
                }
            )

                if st.button("💾 Zapisz zmiany w chmurze"):
                    try:
                        ids_przed_edycja = set(szczegoly['id'].tolist())
                        
                        ids_po_edycji = set(df_edited_result['id'].dropna().tolist()) # dropna bo nowe wiersze nie mają ID
                        ids_usuniete = ids_przed_edycja - ids_po_edycji
                        df_po_usunieciu = df_full[~df_full['id'].isin(ids_usuniete)]
                        
                        # B. LOGIKA AKTUALIZACJI I DODAWANIA
                        # Teraz musimy zaktualizować wiersze, które zostały w edytorze (mogły być zmienione)
                        # oraz dodać nowe.
                        
                        # 1. Oddzielamy wiersze, które edytor nam zwrócił
                        df_to_update = df_edited_result.copy()
                        ids_do_aktualizacji = df_to_update['id'].dropna().tolist()
                        df_baza_bez_edytowanych = df_po_usunieciu[~df_po_usunieciu['id'].isin(ids_do_aktualizacji)]
                        
                        max_id = df_full['id'].max()
                        if pd.isna(max_id): max_id = 0
                        
                        # Reset index do iteracji
                        df_to_update = df_to_update.reset_index(drop=True)
                        
                        for idx, row in df_to_update.iterrows():
                            curr_id = row['id']
                            # Jeśli ID jest puste (NaN) lub 0 -> to nowy wiersz
                            if pd.isna(curr_id) or curr_id == 0:
                                max_id += 1
                                df_to_update.at[idx, 'id'] = int(max_id)
                        
                        df_final = pd.concat([df_baza_bez_edytowanych, df_to_update], ignore_index=True)
                        
                        df_final = df_final.sort_values(by='data', ascending=False)
                        
                        zapisz_calosc(df_final)
                        
                        st.success("✅ Zapisano! (Uwzględniono edycję, dodawanie i usuwanie)")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Błąd zapisu: {e}")
                        # Pokaż szczegóły błędu do debugowania
# ------------------------------------------------------------------
# STRONA 3
# ------------------------------------------------------------------
elif strona == "Wydatki według kategorii":
    st.title("📊 Analiza wydatków według kategorii")

    def ustaw_obecny_m():
        dzisiaj=datetime.date.today()
        pierwyszy_dzine=dzisiaj.replace(day=1)
        st.session_state['wybrane_daty'] = (pierwyszy_dzine, dzisiaj)
    
    

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        filtry_kat = st.multiselect("Kategorie", LISTA_KATEGORII)
    with col_f2:
        date_range = st.date_input("Zakres dat", key="wybrane_daty")
    with col_f3:
        st.write("")
        st.write("")
        st.button("📅 Ten miesiąc", on_click=ustaw_obecny_m)

    if 'wybrane_daty' not in st.session_state:
        dzis=datetime.date.today()
        pierwszy_month=dzis.replace(month=1,day=1)
        st.session_state['wybrane_daty']=(pierwszy_month,dzis)


    if df_full.empty:
        st.info("Brak danych do wykresu.")
    else:
        df_stats = df_full.copy()
        
        # Filtrowanie kategorii technicznych
        df_stats = df_stats[~df_stats['kategoria'].isin([
            'Nieistotne', 'Bez kategorii', 'Regularne oszczędzanie',
            'Wpływy', 'Wpływy - inne', 'Wynagrodzenie'
        ])]

        # Filtry dat i multiselect
        if isinstance(date_range, tuple):
            if len(date_range) == 2:
                s, e = date_range
                df_stats = df_stats[(df_stats['data'].dt.date >= s) & (df_stats['data'].dt.date <= e)]
            elif len(date_range) == 1:
                df_stats = df_stats[df_stats['data'].dt.date == date_range[0]]

        if filtry_kat:
            df_stats = df_stats[df_stats['kategoria'].isin(filtry_kat)]

        # Agregacja i SORTOWANIE
        wydatki_kat = -df_stats.groupby(['kategoria'])['kwota'].sum()
        df_plot = wydatki_kat.reset_index().rename(columns={'kwota': 'kwota', 'kategoria': 'kategoria'})
        df_plot = df_plot.sort_values('kwota', ascending=False)

        klikniecie = alt.selection_point(fields=['kategoria'], name="klik")

        chart = alt.Chart(df_plot).mark_bar(color="#720094").encode(
            x=alt.X('kwota:Q', title='Suma (PLN)'),
            y=alt.Y('kategoria:N',
                sort=alt.EncodingSortField(field='kwota', order='descending'),
                title='Kategoria',
                axis=alt.Axis(labelLimit=400)
            ),
            # Sprawiamy, że nieaktywne słupki będą szare (wizualne potwierdzenie kliknięcia)
            opacity=alt.condition(klikniecie, alt.value(1), alt.value(0.3)),
            tooltip=[
                alt.Tooltip('kategoria:N', title='Kategoria'),
                alt.Tooltip('kwota:Q', title='Kwota', format='.2f')
            ]
        ).add_params(
            klikniecie 
        ).properties(
            title='Kliknij na słupek, aby zobaczyć szczegóły',
            width=800
        )

        # --- 4. WYŚWIETLANIE ---
        # Nadal używamy on_select="rerun", żeby odświeżyć stronę po kliknięciu
        event = st.altair_chart(
            chart,
            use_container_width=True,
            on_select="rerun" 
        )

        # --- 5. ODCZYT DANYCH ---
        wybrany_przedzial = None

        # Sprawdzamy czy w zwróconym obiekcie 'selection' istnieje nasz nazwany selektor "klik"
        if event.selection and "klik" in event.selection:
            # event.selection["klik"] to lista słowników, np. [{'kategoria': 'Jedzenie'}]
            dane_wyboru = event.selection["klik"]
            if dane_wyboru:
                wybrany_przedzial = dane_wyboru[0]["kategoria"]

            # --- 6. TABELA SZCZEGÓŁÓW ---
            if wybrany_przedzial:
                st.divider()
                st.markdown(f"### 🔍 Szczegóły: **{wybrany_przedzial}**")
                
                szczegoly = df_stats[df_stats['kategoria'] == wybrany_przedzial].copy()
                szczegoly = szczegoly.sort_values(by='data', ascending=False)
                
                sum_kat = szczegoly['kwota'].sum()
                st.caption(f"Łączna suma w tym widoku: {-sum_kat:.2f} PLN")

                df_edited_result = st.data_editor(
                szczegoly,
                column_order=["data", "kategoria", "opis", "kwota"],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,  
                key="editor_glowny",
                column_config={
                    "kwota": st.column_config.NumberColumn("Kwota (PLN)", format="%.2f", step=0.01),
                    "data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
                    "kategoria": st.column_config.SelectboxColumn("Kategoria", options=LISTA_KATEGORII, required=True)
                }
            )

                if st.button("💾 Zapisz zmiany w chmurze"):
                    try:
                        ids_przed_edycja = set(szczegoly['id'].tolist())
                        
                        ids_po_edycji = set(df_edited_result['id'].dropna().tolist()) # dropna bo nowe wiersze nie mają ID
                        ids_usuniete = ids_przed_edycja - ids_po_edycji
                        df_po_usunieciu = df_full[~df_full['id'].isin(ids_usuniete)]
                        
                        # B. LOGIKA AKTUALIZACJI I DODAWANIA
                        # Teraz musimy zaktualizować wiersze, które zostały w edytorze (mogły być zmienione)
                        # oraz dodać nowe.
                        
                        # 1. Oddzielamy wiersze, które edytor nam zwrócił
                        df_to_update = df_edited_result.copy()
                        ids_do_aktualizacji = df_to_update['id'].dropna().tolist()
                        df_baza_bez_edytowanych = df_po_usunieciu[~df_po_usunieciu['id'].isin(ids_do_aktualizacji)]
                        
                        max_id = df_full['id'].max()
                        if pd.isna(max_id): max_id = 0
                        
                        # Reset index do iteracji
                        df_to_update = df_to_update.reset_index(drop=True)
                        
                        for idx, row in df_to_update.iterrows():
                            curr_id = row['id']
                            # Jeśli ID jest puste (NaN) lub 0 -> to nowy wiersz
                            if pd.isna(curr_id) or curr_id == 0:
                                max_id += 1
                                df_to_update.at[idx, 'id'] = int(max_id)
                        
                        df_final = pd.concat([df_baza_bez_edytowanych, df_to_update], ignore_index=True)
                        
                        df_final = df_final.sort_values(by='data', ascending=False)
                        
                        zapisz_calosc(df_final)
                        
                        st.success("✅ Zapisano! (Uwzględniono edycję, dodawanie i usuwanie)")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Błąd zapisu: {e}")
                        # Pokaż szczegóły błędu do debugowania

# ------------------------------------------------------------------
# STRONA 4: PANEL ADMINA (DEBUG)
# ------------------------------------------------------------------
elif strona == "🔧 Panel Admina":
    st.title("🔧 Panel Administracyjny")
    st.warning("⚠️ Tutaj operujesz na żywych danych. Każda zmiana jest zapisywana w Google Sheets!")

    # 1. Statystyki bazy
    st.subheader("1. Status bazy danych")
    col1, col2, col3 = st.columns(3)
    col1.metric("Liczba wierszy", len(df_full))
    col2.metric("Najwyższe ID", df_full['id'].max() if not df_full.empty else 0)
    col3.metric("Ostatnia data", str(df_full['data'].max().date()) if not df_full.empty else "-")

    # 2. Pełny podgląd
    st.subheader("2. Pełny podgląd danych (Raw Data)")
    st.dataframe(df_full, use_container_width=True)

    st.divider()

    # 3. Usuwanie po ID
    st.subheader("3. Usuwanie wiersza po ID")
    col_del1, col_del2 = st.columns([1, 2])
    with col_del1:
        id_do_usuniecia = st.number_input("Podaj ID do usunięcia", step=1, value=0)
    
    with col_del2:
        st.write("")
        st.write("")
        if st.button("🗑️ Usuń ten wiersz trwale"):
            if id_do_usuniecia in df_full['id'].values:
                # Filtrujemy, usuwając to ID
                df_po_usunieciu = df_full[df_full['id'] != id_do_usuniecia]
                zapisz_calosc(df_po_usunieciu)
                st.success(f"Usunięto wiersz o ID: {id_do_usuniecia}")
                st.rerun()
            else:
                st.error("Nie znaleziono takiego ID.")

    st.divider()

    # 4. Naprawa struktury (To naprawi Twój problem z ID i datami)
    st.subheader("4. 🛠️ Naprawa ID i Kolejności")
    st.info("Ta funkcja posortuje wszystkie transakcje od najstarszej do najnowszej i nada im nowe ID po kolei (1, 2, 3...). Użyj tego, jeśli masz bałagan w numeracji.")
    
    if st.button("♻️ Przeindeksuj całą bazę"):
        try:
            df_fix = df_full.copy()
            # Sortujemy chronologicznie
            df_fix = df_fix.sort_values(by='data', ascending=True)
            # Nadajemy nowe ID od 1 do N
            df_fix['id'] = range(1, len(df_fix) + 1)
            # Sortujemy z powrotem od najnowszej (żeby w tabeli było wygodnie)
            df_fix = df_fix.sort_values(by='data', ascending=False)
            
            zapisz_calosc(df_fix)
            st.success("Baza naprawiona! ID są teraz po kolei wg dat.")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd: {e}")