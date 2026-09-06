# Dokumentacja stanu małego projektu

Przewodnik generyczny: co warto trzymać w projekcie prowadzonym przez **jedną
lub dwie osoby przez maksymalnie ok. 3 miesiące**, poza plikiem reguł
(`CLAUDE.md`, `CONTRIBUTING.md` lub odpowiednik) i `README.md`.

Zestaw jest celowo minimalny. Każdy dokument poniżej musi zarabiać na swoje
utrzymanie — jeśli nie jest czytany przy powrocie do pracy po tygodniu przerwy,
nie powinno go być.

## Zasada porządkująca: podział według tempa zmian

To jedyne kryterium podziału dokumentów, które w małej skali się broni.
Dokument mieszający informacje o różnym tempie zmian (reguły + bieżący stan +
historia decyzji) dezaktualizuje się w tempie swojego najszybciej zmiennego
składnika i przestaje być czytany w całości — łącznie z tymi fragmentami, które
wciąż są prawdziwe.

Stąd: jedno źródło prawdy na każdy *typ* informacji, a nie na każdy temat.

## Rdzeń

| Plik | Tempo zmian | Odpowiada na pytanie |
|---|---|---|
| plik reguł (`CLAUDE.md`) | prawie nigdy | Jak się w tym projekcie pracuje: środowisko, komendy, twarde granice |
| `STATUS.md` | co sesję | Gdzie jestem i co dalej |
| `OPEN-QUESTIONS.md` | co sesję | Czego nie wiem i co mnie blokuje |
| `docs/decisions/` | dopisywanie | Dlaczego jest tak, a nie inaczej |
| `docs/reference/` | rzadko | Fakty kosztowne do odtworzenia |
| `README.md` | rzadko | Co to w ogóle jest — dla siebie za pół roku |

### STATUS.md

Najważniejsza nie jest lista „zrobione", tylko **sekcja „Następny krok" na
samej górze**: jedno–dwa zdania o tym, od czego zaczynam po powrocie. To ona
decyduje, czy dokument oszczędza kwadrans na starcie sesji, czy nie.

Sekcję „Zrobione" trzymaj skrótowo i bezlitośnie przycinaj — pełną historię masz
w `git log`. Dokument statusowy, który rośnie w archeologię, przestaje być
czytany.

```markdown
# Status — aktualizacja RRRR-MM-DD

## Następny krok
Jedno zdanie: od czego zaczynam następnym razem.

## W toku
- rzecz zaczęta, ale nieskończona — w jakim stanie zostawiona

## Do zrobienia
- konkrety, nie hasła; jeśli pozycja wisi trzeci tydzień, przenieś ją niżej

## Zrobione (ostatnie ~2 tygodnie)
- skrótowo, tylko to, co zmienia obraz projektu

## Świadomie odłożone
- rzecz + powód, dla którego jej *nie* robimy (żeby nie wracać do tematu
  co dwa tygodnie)
```

Sekcja „Świadomie odłożone" jest niedoceniana: w projekcie na dwie osoby to ona
najczęściej zapobiega powtórnemu rozważaniu tej samej rzeczy.

### OPEN-QUESTIONS.md

Rejestr pytań i niepewności. Każdy wpis zawiera cztery rzeczy:

```markdown
## Pytanie w jednym zdaniu
- **Dlaczego ma znaczenie:** co się zmieni w projekcie zależnie od odpowiedzi
- **Jak rozstrzygnąć:** zmierzyć / sprawdzić w dokumentacji / zapytać X / zdecydować arbitralnie
- **Status:** otwarte | blokuje <co> | rozstrzygnięte RRRR-MM-DD → <link do ADR>
```

Kluczowa dyscyplina: **zamknięte pytanie znika stąd** i pojawia się jako decyzja
w `docs/decisions/` albo jako fakt w `docs/reference/`. Bez tego rejestr staje
się drugim, gorszym archiwum i traci funkcję listy roboczej.

Warto tu wpisywać także niepewności, które nie blokują — „nie wiem, czy to
zachowanie jest zamierzone". W małym projekcie one giną najszybciej.

### docs/decisions/ — decyzje (ADR)

Jeden datowany plik na decyzję: `RRRR-MM-DD-krotki-tytul.md`. Pliki są
dopisywane, nie edytowane; decyzję zmienioną zastępuje się nowym plikiem,
który odwołuje się do starego.

W tej skali ADR ma ~15 linii, nie szablon RFC:

```markdown
# Tytuł decyzji
Data: RRRR-MM-DD

**Kontekst.** Co wymusiło decyzję.
**Decyzja.** Co postanowiono.
**Alternatywy.** Co odrzucono i dlaczego (jedno zdanie na wariant).
**Konsekwencje.** Co teraz jest łatwiejsze, a co trudniejsze.
```

Wartość ADR-ów rośnie z czasem i prawie nie maleje: opisują *zmiany*, więc — w
przeciwieństwie do dokumentu „architektura" — starzeją się poprawnie.

### docs/reference/ — fakty kosztowne do odtworzenia

Najczęściej pomijany element zestawu, a zwykle najbardziej opłacalny. Trafia tu
wszystko, czego ponowne ustalenie wymaga wysiłku, sprzętu, dostępu albo czasu
oczekiwania:

- wartości zmierzone eksperymentalnie zamiast założonych,
- zaobserwowane zachowania systemu zewnętrznego (API, urządzenia, usługi),
  szczególnie te sprzeczne z dokumentacją,
- ustalone nazewnictwo i słownik pojęć, jeśli w projekcie ścierają się dwie
  konwencje (np. nazwy z zewnętrznego systemu i własne),
- pułapki i osobliwości („co się dzieje po restarcie", „kiedy stan się
  rozjeżdża", „ten timeout musi być większy niż X, bo…").

Przy każdym fakcie: **data ustalenia i sposób** (zmierzone / z dokumentacji /
założone i niepotwierdzone). Rozróżnienie „potwierdzone vs. zgadnięte" jest tu
ważniejsze niż sama wartość.

Typowy objaw braku tego pliku: takie fakty siedzą w skryptach pomocniczych,
plikach roboczych i komentarzach — czyli w miejscach, których nikt nie
przeszuka.

## Skalowanie

- **Kilka dni pracy.** Jeden `STATUS.md`, pytania jako sekcja na jego dole.
  Nic więcej.
- **Kilka tygodni.** Dochodzą `OPEN-QUESTIONS.md` i `docs/decisions/`.
  `docs/reference/` zakładaj w momencie, gdy pierwszy raz musisz coś ustalić
  po raz drugi.
- **Górna granica (2 osoby, ~3 miesiące).** Pełen zestaw z tabeli. Dodatkowo
  rozważ `docs/results/` na wyniki analiz i materiał publikacyjny, oraz krótki
  dziennik sesji — ale tylko przy pracy asynchronicznej, gdzie trzeba sobie
  nawzajem przekazywać kontekst.

Przy dwóch osobach jedyna nowa potrzeba względem pracy w pojedynkę to
**rozstrzyganie, kto co trzyma w ręku**. Wystarczy na to kolumna „kto" w sekcji
„W toku" — nie zakładaj z tego powodu narzędzia do zarządzania zadaniami.

## Anty-wzorce

- **Roadmapa na 3 miesiące.** Rozjedzie się w drugim tygodniu i nikt jej nie
  poprawi. Horyzont „Do zrobienia" w `STATUS.md` wystarcza.
- **CHANGELOG duplikujący `git log`.** Sensowny dopiero, gdy ktoś z zewnątrz
  konsumuje wydania.
- **Osobny dokument „architektura".** W tej skali dezaktualizuje się szybciej
  niż kod. Zastępują go ADR-y plus czytelny układ katalogów opisany w pliku
  reguł.
- **Statusy w wielu miejscach.** `TODO` w kodzie dotyczą konkretnej linijki;
  wszystko, co jest zadaniem projektowym, należy do `STATUS.md`. Jeśli to samo
  zadanie jest w obu miejscach, jedno z nich kłamie.
- **Daty względne.** „w zeszłym tygodniu", „ostatnio" — bezużyteczne po
  miesiącu. Zawsze `RRRR-MM-DD`.

## Warunek, żeby to żyło

Dokumentacja stanu utrzymuje się wyłącznie wtedy, gdy jej aktualizacja jest
częścią rytuału kończenia pracy. Wystarczy jedna linijka w pliku reguł, obok
wymogu uruchomienia testów:

> Przed zaproponowaniem commita zaktualizuj `STATUS.md` i `OPEN-QUESTIONS.md`.

Bez tego oba pliki umierają w ciągu tygodnia — i to jest właściwy moment, żeby
je skasować, zamiast utrzymywać dokumenty, którym nikt nie ufa.
