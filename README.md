# pdf-ocr

Pieni Python-työkalu PDF-tiedostojen tekstintunnistukseen (OCR). Käytä sitä
aina, kun PDF:n teksti on kuvana (skannattu paperi, sähköpostista kuvattu
sivu, kuvana tallennettu dokumentti), jolloin tekstiä ei voi kopioida tai
hakea.

Työkalu toimii mille tahansa PDF:lle ja kielelle. Oletuskieli on suomi,
mutta sen voi vaihtaa (esim. `--lang eng`).

## Mitä se tekee

Työkalu käy PDF:n sivut läpi yksi kerrallaan ja valitsee jokaiselle sivulle
sopivan tavan:

| Sivun tyyppi | Käsittely |
|---|---|
| Tavallinen digitaalinen PDF (oma tekstikerros, ei kuvia) | Teksti poimitaan suoraan. Nopea ja täsmällinen, ei OCR-virheitä. |
| Kuvasivu (skannaus, kuvakaappaus) | Sivu renderöidään kuvaksi, esikäsitellään ja ajetaan Tesseract OCR:n läpi. |
| Sekasivu (kuvia tai paljon piirtoelementtejä, esim. sähköpostista tulostettu sivu, jonka päälle on kirjoitettu tekstiä) | OCR ajetaan, ja sivun oma tekstikerros liitetään mukaan. OCR:n ohi jääneet rivit tulevat loppuun täsmällisinä. Tulosteessa merkintä "OCR + tekstikerros". |
| Tyhjä sivu | Merkitään tyhjäksi, OCR:ää ei ajeta. |

Tulos tallennetaan valitussa muodossa (yksi tai useampi samalla ajolla):

- **DOCX** — teksti Word-dokumenttina, sivuittain otsikoituna.
- **Hakukelpoinen PDF** — alkuperäinen ulkoasu säilyy, ja kuvasivujen päälle
  lisätään näkymätön tekstikerros. Tekstin voi kopioida ja hakea (Ctrl+F).
- **Pelkkä teksti PDF** — teksti aseteltu uudelleen tavallisina riveinä
  uuteen, kevyeen PDF:ään. Ei alkuperäistä ulkoasua, mutta selkeä ja pieni.

## Asennus (Windows)

### 1. Python ja kirjastot

Tarvitset Pythonin (3.10 tai uudempi). Asenna kirjastot työkalun kansiossa:

```bash
python -m pip install -r requirements.txt
```

### 2. Tesseract OCR (pakollinen, erillinen ohjelma)

Tesseract on erillinen ohjelma, jota `pip` **ei** asenna. Se pitää asentaa
**jokaiselle koneelle erikseen**, jolla työkalua käytetään.

1. Lataa asennusohjelma: https://github.com/UB-Mannheim/tesseract/wiki
2. Aja asennus. Valitse komponenttinäkymässä **Additional language data**
   ja rastita tarvitsemasi kielet (esim. **Finnish**, English, Swedish).
3. Asennuspolku voi olla joko `C:\Program Files\Tesseract-OCR` (kaikille
   käyttäjille) tai `%LOCALAPPDATA%\Tesseract-OCR` (vain omalle käyttäjälle).
   Skripti löytää molemmat automaattisesti. Jos asensit muualle, käytä
   `--tesseract-cmd`-parametria tai lisää kansio PATH-muuttujaan.
4. Tarkista asennus (käytä oman asennuksesi polkua):

   ```bash
   "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
   ```

   Listassa pitää näkyä tarvitsemasi kielet (esim. `fin`, `eng`).

### 3. Tarkempi suomen kielimalli `fin_best` (suositeltu)

Oletuskieli on `fin_best`, tarkempi ja hitaampi malli kuin asennuksen mukana
tuleva `fin`. Jos `fin_best`iä ei löydy, työkalu käyttää automaattisesti
mallia `fin` ja ilmoittaa siitä.

1. Lataa `fin.traineddata` osoitteesta
   https://github.com/tesseract-ocr/tessdata_best (kansio juuressa).
2. Nimeä ladattu tiedosto `fin_best.traineddata`, jotta se ei korvaa vanhaa
   `fin`-mallia.
3. Kopioi se Tesseractin `tessdata`-kansioon, esim.
   `C:\Program Files\Tesseract-OCR\tessdata\` tai
   `%LOCALAPPDATA%\Tesseract-OCR\tessdata\`.

Muille kielille saman voi tehdä samasta repositoriosta, ja kielen valitaan
`--lang`-parametrilla (esim. `--lang eng`).

## Käyttö

### Helpoin tapa: `ocr_pdf.bat`

- **Vedä ja pudota:** vedä PDF hiirellä `ocr_pdf.bat`-tiedoston päälle.
- **Tuplaklikkaus:** avaa `ocr_pdf.bat` ja vedä PDF ikkunaan tai kirjoita polku.
- Bat kysyy ensin moottorin numerolla (**1** = Tesseract, **2** = RapidOCR, **3** = moondream, **4** = qwen2.5vl; Enter = 1), sitten tarkkuuden (dpi, oletus 400) ja sivunjakotilan (psm, oletus 3).
  Enter hyväksyy oletuksen. Sen jälkeen skripti kysyy tulostemuodon valikosta.
- Ikkuna jää auki ajon jälkeen, jotta näet tulostiedostojen polut.

### Komentoriviltä

Perusajo (kysyy tulostemuodon valikosta):

```bash
python ocr_pdf.py "C:\polku\asiakirja.pdf"
```

Tulostemuoto suoraan parametrilla (ei kysymyksiä):

```bash
python ocr_pdf.py asiakirja.pdf --output docx
python ocr_pdf.py asiakirja.pdf --output docx pdf-searchable
python ocr_pdf.py asiakirja.pdf --output docx pdf-searchable pdf-text
```

Tulostiedostot tallennetaan oletuksena lähde-PDF:n kansioon nimillä
`<nimi> (teksti, <moottori>).docx`, `<nimi> (hakukelpoinen, <moottori>).pdf` ja
`<nimi> (pelkkä teksti, <moottori>).pdf` — moottorin nimi (`tesseract`,
`rapidocr`, `moondream`, `qwen2.5vl`) tulee mukaan, jotta samasta PDF:stä eri
moottoreilla tehdyt tulokset voi erottaa toisistaan. Jos samanniminen tiedosto
on jo olemassa (esim. edellinen ajo, tai tiedosto on auki toisessa ohjelmassa),
perään lisätään juokseva numero `(2)`, `(3)` jne. — vanhaa tiedostoa ei
ylikirjoiteta eikä ajo keskeydy virheeseen.

### Kaikki valinnat

| Valinta | Selitys |
|---|---|
| `--output docx pdf-searchable pdf-text` | Tulostemuoto(t). Jos jätetään pois, kysytään valikosta. |
| `--engine tesseract` | OCR-moottori: `tesseract` (oletus), `rapidocr`, `moondream` tai `qwen2.5vl` (ks. alla). |
| `--lang fin_best` | OCR-kieli. Oletus `fin_best`. Useita: `--lang fin+eng`. |
| `--dpi 400` | Sivun renderöintitarkkuus OCR:ää varten. Oletus 400. Isompi (esim. 600) voi auttaa pienellä tekstillä, mutta hidastaa. |
| `--psm 3` | Sivunjakotila. `3` automaattinen (oletus), `4` yksi sarake, `6` yksi yhtenäinen lohko (lomakkeet, taulukot), `11`/`12` hajanainen teksti. |
| `--no-preprocess` | Ohita kuvan esikäsittely (ks. alla). |
| `--remove-lines` | Poista lomakkeiden alaviivat ja pisteviivat ennen OCR:ää (ks. alla). |
| `--outdir "C:\kansio"` | Tulostekansio. Oletus: lähde-PDF:n kansio. |
| `--tesseract-cmd "polku\tesseract.exe"` | Tesseractin polku, jos sitä ei löydy automaattisesti. |

### OCR-moottorit (`--engine`)

| Moottori | Vahvuudet | Heikkoudet |
|---|---|---|
| `tesseract` (oletus) | Nopea (1–2 s/sivu), tukee suomen ä/ö-merkkejä, toimii ilman näytönohjainta | Täytetyt lomakkeet, joissa numerot ovat viivojen päällä, vaativat usein esikäsittelyä (`--remove-lines`, `--psm 6`) |
| `rapidocr` | Syväoppimiseen perustuva (PaddleOCR:n mallit). Lukee täytettyjen lomakkeiden numerot usein hyvin ilman esikäsittelyä | Ei tunnista ä/ö-merkkejä (kirjoittaa esim. "tyot", "lisa"). Hitaampi (n. 7–9 s/sivu). `--lang`, `--psm` ja `--remove-lines` eivät vaikuta |
| `moondream` | Pieni paikallinen näkö-kielimalli (Ollama). Nopein VLM-vaihtoehto, hyvä nopeaan kokeiluun | Tarkkuus vaatimattomampi tiheässä/muodollisessa tekstissä kuin qwen2.5vl:llä. Ei sanojen sijaintitietoa: hakukelpoisessa PDF:ssä koko sivu peitetään yhdellä tekstilohkolla, ei sanakohtaisesti |
| `qwen2.5vl` | Paikallinen näkö-kielimalli (Ollama, `qwen2.5vl:3b`). Ymmärtää kuvaa kokonaisuutena — voi pärjätä Tesseractia/RapidOCR:ää paremmin monikerroksisissa dokumenteissa (esim. sähköpostista tulostettu sivu, jonka päälle on vielä kirjoitettu käsin) ja erikoismerkeissä (€, €/jm) | Hitain vaihtoehto CPU:lla (ilman näytönohjainta useita kymmeniä sekunteja/sivu). Sama sijaintitietorajoitus kuin moondreamilla. Voi hallusinoida epäselvässä kohdassa — tarkista tärkeät numerot aina käsin |

RapidOCR ja Ollama-moottorit ovat valinnaisia. Asenna tarvitsemasi erikseen:

```bash
python -m pip install -r requirements-rapidocr.txt
python -m pip install -r requirements-ollama.txt
```

`moondream`/`qwen2.5vl` vaativat lisäksi [Ollaman](https://ollama.com) asennuksen koneelle, ja
että Ollama on käynnissä (asennuksen jälkeen se yleensä käynnistyy automaattisesti taustalle).
Lataa käytettävä malli kertaalleen ennen ensimmäistä ajoa:

```bash
ollama pull moondream
ollama pull qwen2.5vl:3b
```

```bash
python ocr_pdf.py lomake.pdf --engine rapidocr
python ocr_pdf.py kirje.pdf --engine moondream
python ocr_pdf.py kirje.pdf --engine qwen2.5vl
```

Kokeilu kahdella sivulla (skannattu täytetty lomake ja sähköpostista kuvattu
sivu) antoi seuraavaa: kaikki testatut syväoppimismoottorit (RapidOCR,
EasyOCR) lukivat täytetyn lomakkeen numerot oikein ilman esikäsittelyä, kun
Tesseract tarvitsi siihen viivanpoiston. Otos on pieni, joten kokeile omalla
aineistollasi. Eri moottorit voivat erehtyä eri kohdissa, joten tärkeät
numerot kannattaa tarkistaa käsin.

### Tarkkuutta parantavat toiminnot

Nämä koskevat Tesseract-moottoria.


- **Esikäsittely (päällä oletuksena):** sivu muutetaan harmaasävyiseksi,
  vinous korjataan automaattisesti (±5°), kohina poistetaan, kontrastia
  nostetaan ja kuvaa terävöitetään. Hakukelpoisessa PDF:ssä OCR-sivujen
  kuva on tällöin suoristettu ja harmaasävyinen. `--no-preprocess`
  säilyttää alkuperäisen värillisen kuvan.
- **`--psm`-valinta:** jos taulukot tai lomakeasettelu tulevat sekaisin,
  kokeile `--psm 6` tai `--psm 4`.
- **`--remove-lines`:** sopii täytetyille lomakkeille, joissa numerot tai
  teksti ovat viivan tai pisteviivan päällä. Kokeile yhdessä `--psm 6`:n
  kanssa. Haittapuoli: ä/ö-pisteet ja pienet merkit voivat rouhiutua.
  Käytä vain tarvittaessa ja tarkista tulos.
- **Kielimalli:** `fin_best` on tarkempi kuin `fin`, mutta ero on usein
  pieni. Esikäsittely, `--psm` ja `--remove-lines` vaikuttavat yleensä
  enemmän.

## Rajoitukset ja huomioita

- **OCR ei ole virheetöntä.** Tarkkuus riippuu skannin laadusta. Huonolaatuisessa,
  vinossa tai pienessä tekstissä on virheitä. Tarkista aina tärkeät kohdat
  (numerot, hinnat, päivämäärät, nimet) alkuperäisestä, ennen kuin luotat
  tulokseen.
- **Rakenne ei säily.** Taulukot ja monisarakkeiset asettelut eivät säily
  rakenteena DOCX- ja "pelkkä teksti PDF" -tulosteissa, koska teksti poimitaan
  vasemmalta oikealle ja ylhäältä alas. Hakukelpoinen PDF säilyttää alkuperäisen
  ulkoasun.
- **Käsinkirjoitus** ei tunnistu luotettavasti. Tesseract on tarkoitettu
  painetulle tekstille.
- **Tietoturva:** kaikki käsittely tapahtuu paikallisesti koneellasi, eikä
  mitään lähetetä ulkopuolisille palveluille. Työkalu sopii siis myös
  luottamukselliselle aineistolle.
- **Säädettävät vakiot** löytyvät `ocr_pdf.py`-tiedoston alusta:
  `MIN_TEXT_CHARS` (kuinka paljon tekstiä sivulla pitää olla, jotta se
  luetaan suoraan), sekä `DRAWINGS_THRESHOLD` ja
  `SUSPICIOUSLY_SHORT_NATIVE_TEXT` (sivu tulkitaan sekasivuksi kun
  piirtoelementtejä on enemmän kuin `DRAWINGS_THRESHOLD` JA sivun oma
  tekstikerros on lyhyempi kuin `SUSPICIOUSLY_SHORT_NATIVE_TEXT` merkkiä —
  esim. sähköpostista tulostettu sivu, jonka runko-osa on kirjoitettu
  vektoripolkuina eikä tekstinä).
- Kun tulosteesta kopioi tekstiä, väliviiva voi kopioitua "pehmeänä tavuviivana" (näkymätön merkki U+00AD). Se ei näy PDF:ssä, mutta voi vaikuttaa haussa.
- Tulosteiden PDF-teksti käyttää Windowsin Arial-fonttia, jotta €-merkki ja
  ä/ö säilyvät. Jos sitä ei löydy, € korvataan tekstillä "EUR".

## Tiedostot

- `ocr_pdf.py` — itse skripti
- `ocr_pdf.bat` — vedä ja pudota -käynnistin Windowsille
- `requirements.txt` — Python-riippuvuudet
- `requirements-rapidocr.txt` — valinnainen: RapidOCR-moottori
- `requirements-ollama.txt` — valinnainen: moondream/qwen2.5vl-moottorit (vaatii lisäksi Ollaman asennuksen)
- `.gitignore` — pitää pois tulosteet, PDF-aineiston, kielimallit ja välimuistit
- `README.md` — tämä tiedosto
