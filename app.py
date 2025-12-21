import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime

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
    'Odzież i obuwie', 'Podróże i wyjazdy', 'ZaMieszkanie', 'Zdrowie i uroda',
    'Regularne oszczędzanie', 'Serwis i części', 'Multimedia, książki i prasa',
    'Wypłata gotówki', 'Opłaty i odsetki', 'Auto i transport - inne',
    'Czynsz i wynajem', 'Paliwo', 'Akcesoria i wyposażenie ',
    'Jedzenie poza domem', 'Prezenty i wsparcie', 'Bez kategorii'
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

# --- TWOJA FUNKCJA CSV (Lekko dostosowana do nazw kolumn) ---
def przetworz_csv(uploaded_file):
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

        dane['data'] = pd.to_datetime(dane['data'], dayfirst=True, errors='coerce')
        
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

        dane['data'] = pd.to_datetime(dane['data'], dayfirst=True, errors='coerce')
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
strona = st.sidebar.radio("Idź do:", ["Tabela danych", "Statystyki", "Dodaj ręcznie"])

df_full = pobierz_dane()

# ------------------------------------------------------------------
# STRONA 1: TABELA DANYCH (View, Import, Edit)
# ------------------------------------------------------------------
if strona == "Tabela danych":
    
    # --- SEKCJA IMPORTU CSV ---
    with st.expander("📥 Wgraj wyciąg z banku (CSV)"):
        uploaded_file = st.file_uploader("Wybierz plik CSV (mBank / ING)", type="csv")
        
        if uploaded_file is not None:
            st.write("Przetwarzanie...")
            df_new = przetworz_csv(uploaded_file)
            
            if not df_new.empty:
                st.write("Podgląd:")
                st.dataframe(df_new.head(3))
                
                if st.button("🔥 Dodaj te transakcje do chmury"):
                    # 1. Obliczamy ID (brak autoincrement w Sheets)
                    max_id = df_full['id'].max() if not df_full.empty else 0
                    if pd.isna(max_id): max_id = 0
                    
                    df_new['id'] = range(int(max_id) + 1, int(max_id) + 1 + len(df_new))
                    
                    # 2. Łączymy stare dane z nowymi
                    df_updated = pd.concat([df_full, df_new], ignore_index=True)
                    
                    # 3. Zapisujemy całość
                    zapisz_calosc(df_updated)
                    
                    st.success(f"Dodano {len(df_new)} transakcji!")
                    st.rerun()
            else:
                st.error("Błąd odczytu pliku lub plik pusty.")

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
        filtry_kat = st.multiselect("Kategorie", LISTA_KATEGORII, default=LISTA_KATEGORII)

    with col_f2:
        date_range = st.date_input("Zakres dat", key="wybrane_daty")

    with col_f3:
        st.write("")
        st.write("")
        st.button("📅 Ten miesiąc", on_click=ustaw_obecny_miesiac)

    # --- APLIKOWANIE FILTRÓW ---
    df_view = df_full.copy()

    # Filtr daty
    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            start_date, end_date = date_range
            maska_daty = (df_view['data'].dt.date >= start_date) & (df_view['data'].dt.date <= end_date)
            df_view = df_view[maska_daty]
        elif len(date_range) == 1:
            start_date = date_range[0]
            maska_daty = (df_view['data'].dt.date == start_date)
            df_view = df_view[maska_daty]

    # Filtr kategorii
    if filtry_kat:
        df_view = df_view[df_view['kategoria'].isin(filtry_kat)]

    df_view = df_view.sort_values(by='data', ascending=False)

    # --- PODSUMOWANIE ---
    st.markdown("---")
    suma_widoczna = pd.to_numeric(
        df_view.loc[~df_view['kategoria'].isin(["Bez kategorii", "Regularne oszczędzanie",'Nieistotne']), 'kwota'],
        errors='coerce'
    ).fillna(0).sum()
    liczba_transakcji = len(df_view)

    c1, c2, c3 = st.columns(3)
    with c1:
        if suma_widoczna >= 0:
            st.metric("💰 Suma wpływów", f"{suma_widoczna:.2f} PLN")
        else:
            st.metric("💸 Suma wydatków", f"{suma_widoczna:.2f} PLN")
    with c2:
        st.metric("🧾 Liczba transakcji", f"{liczba_transakcji}")
    with c3:
        srednia = suma_widoczna / liczba_transakcji if liczba_transakcji > 0 else 0
        st.metric("📉 Średni wydatek", f"{srednia:.2f} PLN")
    st.markdown("---")

    # --- EDYTOR TABELI STREAMLIT ---
    # Dodajemy hide_index=True, żeby usunąć tę dziwną pierwszą kolumnę
    df_edited_result = st.data_editor(
        df_view,
        column_order=["data", "kategoria", "opis", "kwota"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,  # <--- TO USUWA "DZIWNĄ KOLUMNĘ"
        key="editor_glowny",
        column_config={
            "kwota": st.column_config.NumberColumn("Kwota (PLN)", format="%.2f", step=0.01),
            "data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
            "kategoria": st.column_config.SelectboxColumn("Kategoria", options=LISTA_KATEGORII, required=True)
        }
    )

    # --- ZAPIS EDYCJI DO GOOGLE SHEETS (POPRAWIONY - OBSŁUGUJE USUWANIE) ---
    if st.button("💾 Zapisz zmiany w chmurze"):
        try:
            # A. LOGIKA USUWANIA
            # Musimy sprawdzić, co zniknęło z widoku (df_view), a nie z całej bazy.
            
            # 1. ID, które były widoczne PRZED edycją (wczytane do edytora)
            ids_przed_edycja = set(df_view['id'].tolist())
            
            # 2. ID, które zostały PO edycji (to co oddał edytor)
            ids_po_edycji = set(df_edited_result['id'].dropna().tolist()) # dropna bo nowe wiersze nie mają ID
            
            # 3. Różnica = to co Użytkownik usunął klawiszem Delete
            ids_usuniete = ids_przed_edycja - ids_po_edycji
            
            # 4. Usuwamy te ID z głównej bazy (df_full)
            # Zostawiamy wiersze, których ID NIE JEST w zbiorze usuniętych
            df_po_usunieciu = df_full[~df_full['id'].isin(ids_usuniete)]
            
            # B. LOGIKA AKTUALIZACJI I DODAWANIA
            # Teraz musimy zaktualizować wiersze, które zostały w edytorze (mogły być zmienione)
            # oraz dodać nowe.
            
            # 1. Oddzielamy wiersze, które edytor nam zwrócił
            df_to_update = df_edited_result.copy()
            
            # 2. Usuwamy z bazy (df_po_usunieciu) stare wersje wierszy, które teraz nadpiszemy
            # (czyli te, które są w df_to_update i mają ID)
            ids_do_aktualizacji = df_to_update['id'].dropna().tolist()
            df_baza_bez_edytowanych = df_po_usunieciu[~df_po_usunieciu['id'].isin(ids_do_aktualizacji)]
            
            # 3. Nadawanie ID dla NOWYCH wierszy (dodanych plusem)
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
            
            # 4. SKLEJAMY: (Reszta bazy) + (To co wyszło z edytora)
            df_final = pd.concat([df_baza_bez_edytowanych, df_to_update], ignore_index=True)
            
            # Sortowanie i wysyłka
            df_final = df_final.sort_values(by='data', ascending=False)
            
            zapisz_calosc(df_final)
            
            st.success("✅ Zapisano! (Uwzględniono edycję, dodawanie i usuwanie)")
            st.rerun()
            
        except Exception as e:
            st.error(f"Błąd zapisu: {e}")
            # Pokaż szczegóły błędu do debugowania
            import traceback
            st.text(traceback.format_exc())

# ------------------------------------------------------------------
# STRONA 2: STATYSTYKI
# ------------------------------------------------------------------
elif strona == "Statystyki":
    st.title("📊 Analiza wydatków")
    
    if df_full.empty:
        st.info("Brak danych do wykresu.")
    else:
        # Grupowanie
        wydatki_kat = df_full.groupby("kategoria")["kwota"].sum().sort_values()
        st.bar_chart(wydatki_kat)

# ------------------------------------------------------------------
# STRONA 3: DODAJ RĘCZNIE
# ------------------------------------------------------------------
elif strona == "Dodaj ręcznie":
    st.title("➕ Dodaj nowy wydatek")
    
    with st.form("nowy_wydatek"):
        data_in = st.date_input("Data")
        kat_in = st.selectbox("Kategoria", LISTA_KATEGORII)
        opis_in = st.text_input("Opis", "Zakupy")
        kwota_in = st.number_input("Kwota", step=0.01)
        
        submit = st.form_submit_button("Zapisz w chmurze")
        
        if submit:
            # 1. Obliczamy ID
            max_id = df_full['id'].max() if not df_full.empty else 0
            if pd.isna(max_id): max_id = 0
            new_id = int(max_id) + 1
            
            # 2. Tworzymy słownik z danymi
            nowy_wiersz = {
                'id': new_id,
                'data': data_in, # datetime object
                'kategoria': kat_in,
                'opis': opis_in,
                'kwota': kwota_in
            }
            
            # 3. Wysyłamy do Sheets (append_row jest szybkie)
            dodaj_wiersz(nowy_wiersz)
            
            st.success("Dodano wydatek!")
            st.rerun()