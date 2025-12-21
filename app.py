import streamlit as st
import pandas as pd
import sqlite3
import datetime

st.set_page_config(page_title="Budżet", layout="wide")

# --- KROK 1: Stwórz Menu ---
st.sidebar.title("Nawigacja")

strona = st.sidebar.radio("Idź do:", ["Tabela danych", "Statystyki", "Dodaj ręcznie"])


conn = sqlite3.connect('baza1.db')
cursor = conn.cursor()
cursor.execute("""
            CREATE TABLE IF NOT EXISTS dane (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                opis TEXT,
                kategoria TEXT,
                kwota REAL
            )
            """)
conn.commit()

# --- 1. FUNKCJA PRZETWARZAJĄCA CSV (Twoja logika) ---
# --- 1. FUNKCJA PRZETWARZAJĄCA CSV (Z ODCIĘCIEM PUSTYCH WIERSZY) ---
def przetworz_csv(uploaded_file):
    try:
        # PODEJŚCIE 1 (mBank)
        dane = pd.read_csv(uploaded_file, delimiter=';', encoding='utf-8', index_col=False, skiprows=25)
        
        # Czyszczenie nazw kolumn
        dane.columns = dane.columns.str.replace("#", "").str.strip()
        
        # Mapowanie nazw
        dane = dane.rename(columns={
            'Data operacji': 'Data',
            'Opis operacji': 'Opis',
            'Kwota': 'Kwota',
            'Kategoria': 'Kategoria'
        })

        if 'Rachunek' in dane.columns:
            dane = dane.drop('Rachunek', axis=1)

        # --- ✂️ NOWOŚĆ: ODCIĘCIE STOPKI (mBank) ---
        # Często mBank ma puste wiersze lub stopkę na dole.
        # Sprawdzamy, gdzie w kolumnie 'Data' pojawia się pierwsza pusta wartość (NaN).
        if dane['Data'].isna().any():
            pierwszy_pusty_wiersz = dane[dane['Data'].isna()].index[0]
            # Bierzemy tylko wiersze OD góry DO pierwszego pustego
            dane = dane.iloc[:pierwszy_pusty_wiersz]
        # -------------------------------------------

        # Naprawa daty
        dane['Data'] = pd.to_datetime(dane['Data'], dayfirst=True, errors='coerce')
        
        # Naprawa kwoty
        dane['Kwota'] = dane['Kwota'].astype(str).str.replace(" PLN", "")
        dane['Kwota'] = dane['Kwota'].str.replace(",", ".")
        dane['Kwota'] = dane['Kwota'].str.replace(" ", "").astype(float)
        
        # Uzupełnienie kategorii
        if 'Kategoria' not in dane.columns:
            dane['Kategoria'] = "Bez kategorii" 
        else:
            dane['Kategoria'] = dane['Kategoria'].fillna("Bez kategorii")
        
        # Na wszelki wypadek usuwamy wiersze, gdzie data nadal jest pusta (NaT)
        dane = dane.dropna(subset=['Data'])

        return dane[['Data', 'Kategoria', 'Opis', 'Kwota']]

    except Exception:
        # PODEJŚCIE 2 (ING)
        uploaded_file.seek(0)
        dane = pd.read_csv(uploaded_file, encoding='cp1250', delimiter=';', index_col=False, skiprows=19)
        dane.columns = dane.columns.str.replace("#", "").str.strip()
        
        dane = dane.rename(columns={
            'Data transakcji': 'Data', 
            'Dane kontrahenta': 'Opis',
            'Kwota transakcji (waluta rachunku)': 'Kwota'
        })

        # --- ✂️ ODCIĘCIE STOPKI (ING) ---
        if dane['Data'].isna().any():
            pierwszy_pusty_wiersz = dane[dane['Data'].isna()].index[0]
            dane = dane.iloc[:pierwszy_pusty_wiersz]
        # -------------------------------

        dane['Data'] = pd.to_datetime(dane['Data'], dayfirst=True, errors='coerce')
        dane = dane.dropna(subset=['Data']) # Usuwamy błędne daty

        dane['Kategoria'] = "Bez kategorii"
        dane["Opis"] = "ING " + dane["Opis"].fillna("")

        dane['Kwota'] = dane['Kwota'].astype(str).str.replace(" PLN", "")
        dane['Kwota'] = dane['Kwota'].str.replace(",", ".")
        dane['Kwota'] = dane['Kwota'].str.replace(" ", "").astype(float)
        
        dane['Kwota'] = dane['Kwota'] / 2

        return dane[["Data", "Kategoria", "Opis", "Kwota"]]


# --- 2. KARTA WGRYWANIA (Umieść to pod tytułem strony) ---
with st.expander("📥 Wgraj wyciąg z banku (CSV)"):
    uploaded_file = st.file_uploader("Wybierz plik CSV (mBank / ING)", type="csv")
    
    if uploaded_file is not None:
        try:
            # 1. Przetwarzamy
            df_new = przetworz_csv(uploaded_file)
            
            st.write("Podgląd danych do wgrania:")
            st.dataframe(df_new.head(3))
            
            if st.button("🔥 Dodaj te transakcje do bazy"):
                # --- OBLICZANIE NOWYCH ID ---
                cursor = conn.cursor()
                try:
                    result = cursor.execute("SELECT MAX(id) FROM dane").fetchone()
                    # TU BYŁ BŁĄD. Dodajemy int(), żeby wymusić liczbę całkowitą
                    if result[0] is not None:
                        max_id = int(result[0])
                    else:
                        max_id = 0
                except:
                    max_id = 0
                
                # Teraz max_id jest na pewno intem, więc range zadziała
                nowe_id = range(max_id + 1, max_id + 1 + len(df_new))
                df_new['id'] = list(nowe_id) # Zamieniamy range na listę dla pewności
                # ----------------------------

                # Mapujemy nazwy kolumn na małe litery dla SQL
                df_to_save = df_new.rename(columns={
                    'Data': 'data',
                    'Kategoria': 'kategoria',
                    'Opis': 'opis',
                    'Kwota': 'kwota'
                })
                
                # Zapisujemy
                df_to_save.to_sql('dane', conn, if_exists='append', index=False)
                
                st.success(f"Dodano {len(df_new)} wierszy! (ID od {max_id + 1})")
                st.rerun()
                
        except Exception as e:
            st.error(f"Błąd przetwarzania: {e}")

if strona == "Tabela danych":
    st.subheader("📝 Edycja i Przegląd Wydatków")

    LISTA_KATEGORII = ['Nieistotne', 'Wynagrodzenie', 'Wpływy', 'Elektronika', 'Wyjścia i wydarzenia', 'Żywność i chemia domowa', 'Przejazdy', 'Sport i hobby ', 'Wpływy - inne', 'Odzież i obuwie', 'Podróże i wyjazdy', 'ZaMieszkanie', 'Zdrowie i uroda', 'Regularne oszczędzanie', 'Serwis i części', 'Multimedia, książki i prasa', 'Wypłata gotówki', 'Opłaty i odsetki',  'Auto i transport - inne', 'Czynsz i wynajem', 'Paliwo', 'Akcesoria i wyposażenie ', 'Jedzenie poza domem',  'Prezenty i wsparcie',  'Bez kategorii']

    # 1. Pobieramy dane, wskazując 'id' jako kręgosłup tabeli
    try:
        # index_col='id' sprawia, że Pandas używa Twojego ID do identyfikacji wierszy
        df_full = pd.read_sql("SELECT * FROM dane", conn, index_col='id')
    except Exception as e:
        st.error(f"Problem z bazą (czy masz kolumnę 'id'?): {e}")
        # Tworzymy pusty DataFrame na wypadek błędu
        df_full = pd.DataFrame(columns=['Data', 'Kategoria', 'Opis', 'Kwota'])

    # --- NAPRAWA DANYCH ---
    if not df_full.empty:

        df_full['Data'] = pd.to_datetime(df_full['Data'], dayfirst=True, errors='coerce')
        if df_full['Kwota'].dtype == 'object':
            df_full['Kwota'] = df_full['Kwota'].astype(str).str.replace(',', '.').str.replace(' ', '')
            df_full['Kwota'] = pd.to_numeric(df_full['Kwota'], errors='coerce')

    # ... (Wcześniej kod naprawy danych df_full) ...

    # --- FILTRY Z PRZYCISKIEM "TEN MIESIĄC" ---

    # 1. Funkcja pomocnicza: ustawia daty w pamięci (Session State) na bieżący miesiąc
    def ustaw_obecny_miesiac():
        dzisiaj = datetime.date.today()
        pierwszy_dzien = dzisiaj.replace(day=1) # Zamieniamy dzień na 1
        # Ustawiamy w pamięci Streamlita nową wartość dla kalendarza
        st.session_state['wybrane_daty'] = (pierwszy_dzien, dzisiaj)

    # 2. Inicjalizacja domyślnych dat przy pierwszym uruchomieniu
    # Jeśli w pamięci nic nie ma, ustawiamy zakres na podstawie danych z bazy lub dzisiejszy
    if 'wybrane_daty' not in st.session_state:
        if not df_full.empty:
            min_d = df_full['Data'].min().date()
            max_d = df_full['Data'].max().date()
            st.session_state['wybrane_daty'] = (min_d, max_d)
        else:
            st.session_state['wybrane_daty'] = (datetime.date.today(), datetime.date.today())


    if 'wybrane_daty' not in st.session_state:
        # Zamiast brać wszystko z bazy, bierzemy obecny miesiąc
        dzisiaj = datetime.date.today()
        pierwszy_dzien_miesiaca = dzisiaj.replace(day=1)
        
        # Ustawiamy zakres: od 1. dnia miesiąca do dzisiaj
        st.session_state['wybrane_daty'] = (pierwszy_dzien_miesiaca, dzisiaj)
    # 3. Układ strony: 3 kolumny (Kategorie | Daty | Przycisk)
    # Używamy proporcji [2, 2, 1], żeby przycisk był mniejszy
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

    with col_f1:
        filtry_kat = st.multiselect("Kategorie", LISTA_KATEGORII, default=LISTA_KATEGORII)

    with col_f2:
        # Kluczowe: argument 'key="wybrane_daty"' wiąże ten kalendarz z pamięcią.
        # Jak zmienimy coś w 'session_state', kalendarz sam się zaktualizuje.
        date_range = st.date_input("Zakres dat", key="wybrane_daty")

    with col_f3:
        # Pusty tekst, żeby obniżyć przycisk (wyrównać go w dół do poziomu inputów)
        st.write("") 
        st.write("") 
        # Przycisk wywołuje funkcję 'ustaw_obecny_miesiac' po kliknięciu
        st.button("📅 Ten miesiąc", on_click=ustaw_obecny_miesiac)

    # --- APLIKOWANIE FILTRÓW (Bez zmian) ---
    df_view = df_full.copy()

    # Obsługa przypadku, gdy użytkownik wybierze tylko jedną datę w kalendarzu
    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            start_date, end_date = date_range
            maska_daty = (df_view['Data'].dt.date >= start_date) & (df_view['Data'].dt.date <= end_date)
            df_view = df_view[maska_daty]
        elif len(date_range) == 1:
            # Jeśli kliknąłeś dopiero start, a nie wybrałeś końca - pokaż tylko ten jeden dzień
            start_date = date_range[0]
            maska_daty = (df_view['Data'].dt.date == start_date)
            df_view = df_view[maska_daty]

    if filtry_kat:
        df_view = df_view[df_view['Kategoria'].isin(filtry_kat)]

    df_view = df_view.sort_values(by='Data', ascending=False)

    # ... (Dalej kod podsumowania i tabeli bez zmian) ...

        # ... (tutaj skończyły się if-y od filtrowania daty i kategorii)
        # df_view = df_view.sort_values(...)

    # --- 🆕 NOWY KOD: PODSUMOWANIE ---
    st.markdown("---") # Pozioma kreska dla porządku

    # Obliczamy sumę i liczbę wierszy z tego, co aktualnie widać
    suma_widoczna = df_view['Kwota'].sum()
    liczba_transakcji = len(df_view)

    # Tworzymy 3 kolumny na liczniki
    c1, c2, c3 = st.columns(3)

    with c1:
        if suma_widoczna >= 0:
            st.metric("💰 Suma wpływów", f"{suma_widoczna:.2f} PLN")
        else:
            st.metric("💸 Suma wydatków", f"{suma_widoczna:.2f} PLN")

    with c2:
        st.metric("🧾 Liczba transakcji", f"{liczba_transakcji}")

    with c3:
        # Mały bonus: średnia Kwota wydatku
        srednia = suma_widoczna / liczba_transakcji if liczba_transakcji > 0 else 0
        st.metric("📉 Średni wydatek", f"{srednia:.2f} PLN")

    st.markdown("---")
# ---------------------------------

# ... (tutaj zaczyna się df_edited = st.data_editor...)

    # --- EDYTOR ---
    df_edited = st.data_editor(
        df_view,
        # Nie wymieniamy tu 'id', więc użytkownik go nie zobaczy w środku,
        # ale Pandas pamięta, że on tam jest (jako index)
        column_order=["Data", "Kategoria", "Opis", "Kwota"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor_glowny",
        column_config={
            "Kwota": st.column_config.NumberColumn("Kwota", format="%.2f PLN", step=0.01),
            "Data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
            "Kategoria": st.column_config.SelectboxColumn("Kategoria", options=LISTA_KATEGORII, required=True)
        }
    )

    # --- ZAPIS ZMIAN (Z obsługą ID) ---
    if st.button("💾 Zapisz zmiany"):
        try:
            # KROK A: Oddzielamy stare wiersze (które mają ID) od nowych (które nie mają)
            # Wiersze istniejące mają ID będące liczbami. Nowe wiersze dodane w edytorze
            # zazwyczaj mają indeks tymczasowy (nie pasujący do ID z bazy).
            
            # 1. Usuwamy z głównej bazy (df_full) te wiersze, które były widoczne (zostaną nadpisane)
            #    Używamy indeksów z df_view (czyli ID przefiltrowanych wierszy)
            indeksy_do_usuniecia = df_view.index
            
            # Ale uwaga: jeśli dodałeś NOWY wiersz, jego indeksu nie ma w df_full.
            # intersection zabezpiecza przed błędem "nie znaleziono indeksu"
            istniejace_indeksy = df_full.index.intersection(indeksy_do_usuniecia)
            df_reszta = df_full.drop(istniejace_indeksy)
            
            # 2. Generowanie ID dla NOWYCH wierszy
            # Musimy sprawdzić, czy w df_edited są wiersze, które nie mają poprawnego ID
            
            # Znajdźmy najwyższe ID w bazie, żeby wiedzieć od ilu zacząć numerować nowe
            if not df_full.empty and pd.api.types.is_integer_dtype(df_full.index):
                max_id = df_full.index.max()
            else:
                max_id = 0
                
            # Resetujemy indeks w edytowanych danych, żeby naprawić nowo dodane wiersze
            # Wiersze, które miały stare ID, zachowają je w kolumnie 'id' (po reset_index)
            df_edited_reset = df_edited.reset_index()
            
            # Jeśli kolumna z indeksem nazywała się 'id', to teraz jest normalną kolumną.
            # Jeśli nowy wiersz nie ma ID, trzeba mu je nadać.
            
            nowe_wiersze = []
            gotowe_wiersze = []
            
            for index, row in df_edited_reset.iterrows():
                # Sprawdzamy czy to wiersz z istniejącym ID (z bazy) czy nowy
                # Istniejące ID powinno być liczbą całkowitą
                obecne_id = row.get('id')
                
                # Prosta logika: jeśli ID jest puste lub nie jest liczbą z naszej bazy -> to nowy wiersz
                if pd.isna(obecne_id) or (obecne_id not in df_full.index):
                    max_id += 1
                    row['id'] = max_id
                
                gotowe_wiersze.append(row)
                
            # Składamy z powrotem DataFrame z edytowanych
            df_edited_final = pd.DataFrame(gotowe_wiersze).set_index('id')
            
            # 3. Łączymy: Reszta (ukryte w filtrze) + Edytowane (widoczne)
            df_final = pd.concat([df_reszta, df_edited_final])
            
            # 4. Zapis do bazy
            # index=True oznacza "Zapisz też indeks jako kolumnę w SQL"
            # index_label='id' nazywa tę kolumnę 'id'
            df_final.to_sql('dane', conn, if_exists='replace', index=True, index_label='id')
            
            st.success("Zapisano zmiany! ID zostały zachowane.")
            st.rerun()
            
        except Exception as e:
            st.error(f"Błąd zapisu: {e}")

elif strona == "Statystyki":
    st.title("📊 Analiza wydatków")
    st.write("Tu będą wykresy!")
    
    
    df = pd.read_sql("SELECT * FROM dane", conn)
    if not df.empty:
        
        wydatki_kat = df.groupby("Kategoria")["Kwota"].sum()
        st.bar_chart(wydatki_kat)
    else:
        st.info("Brak danych do wykresu")

elif strona == "Dodaj ręcznie":
    st.title("➕ Dodaj nowy wydatek")
    
    # Prosty formularz
    with st.form("nowy_wydatek"):
        Data = st.date_input("Data")
        kat = st.text_input("Kategoria", "Jedzenie")
        opis = st.text_input("Opis", "Zakupy")
        Kwota = st.number_input("Kwota", step=0.01)
        
        # Przycisk wysyłający formularz
        submit = st.form_submit_button("Zapisz w bazie")
        
        if submit:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO wydatki (Data, kategoria, opis, Kwota) VALUES (?, ?, ?, ?)", 
                           (Data, kat, opis, Kwota))
            conn.commit()
            st.success("Dodano wydatek!")

# --- Na koniec zamykamy połączenie ---
conn.close()