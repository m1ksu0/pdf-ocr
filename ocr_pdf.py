"""
ocr_pdf.py -- PDF-tiedostojen tekstintunnistus (OCR) kuvamuotoisille sivuille.

Käyttötarkoitus:
    Osa PDF-tiedostoista (esim. skannatut tai kuvana toimitetut tarjoukset)
    ei sisällä poimittavaa tekstikerrosta. Tämä skripti käy PDF:n sivu
    kerrallaan läpi:
      - jos sivulla on jo tekstikerros, teksti poimitaan suoraan (nopea,
        täysin tarkka, ei OCR-virheitä)
      - jos sivu on pelkkä kuva, sivu renderöidään ja ajetaan Tesseract-OCR:n
        läpi suomenkielisellä kielimallilla

    Tulos voidaan tallentaa käyttäjän valinnan mukaan yhtenä tai useampana
    seuraavista:
      1) DOCX  -- poimittu/OCR:attu teksti Word-dokumenttina
      2) Hakukelpoinen PDF -- alkuperäinen ulkoasu (kuvat) säilyy,
         näkymätön tekstikerros lisätään päälle (voi kopioida/hakea tekstiä)
      3) Pelkkä teksti PDF-muodossa -- teksti uudelleenaseteltuna uuteen,
         kevyeen PDF:ään (ei alkuperäistä ulkoasua, mutta pieni ja selkeä)

Moottorit (--engine):
    tesseract  -- oletus; nopea, tukee suomen ä/ö-merkkejä, vaatii Tesseract-asennuksen
    rapidocr   -- syväoppimispohjainen (PaddleOCR-mallit); lukee täytettyjen lomakkeiden
                  numerot usein paremmin ilman esikäsittelyä, mutta ei tunnista ä/ö-merkkejä
                  (asennus: pip install -r requirements-rapidocr.txt)

Edellytykset:
    - Tesseract OCR asennettuna koneelle, katso README.md
    - Suomenkielinen kielidata (fin.traineddata) Tesseractin tessdata-kansiossa
    - Python-riippuvuudet: pip install -r requirements.txt

Käyttö:
    python ocr_pdf.py <tiedosto.pdf> [--output docx pdf-searchable pdf-text]
                       [--engine tesseract|rapidocr] [--lang fin_best] [--dpi 400] [--outdir .]
                       [--tesseract-cmd "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"]

    Jos --output jätetään pois, skripti kysyy interaktiivisesti valikosta.

Esimerkkejä:
    python ocr_pdf.py asiakirja.pdf
    python ocr_pdf.py asiakirja.pdf --output docx pdf-searchable
    python ocr_pdf.py asiakirja.pdf --output pdf-text --dpi 400
"""

from __future__ import annotations

import argparse
import io
import os
import re
from collections import defaultdict
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter, ImageOps
from docx import Document
from docx.shared import Pt

# Kynnysarvo: jos sivun oma tekstikerros sisältää vähemmän kuin tämän verran
# merkkejä, sivu tulkitaan kuvasivuksi ja ajetaan OCR:n läpi.
MIN_TEXT_CHARS = 20

# Jos sivulla on kuvia tai paljon piirtoelementtejä (esim. sähköpostista tulostetun
# sivun kirjaimet ovat vektoripolkuja, ei tekstiä), sivun oma tekstikerros ei
# välttämättä kata kaikkea näkyvää sisältöä, ja sivu ajetaan OCR:n läpi.
DRAWINGS_THRESHOLD = 100

VALID_OUTPUTS = {"docx", "pdf-searchable", "pdf-text"}
VALID_ENGINES = ("tesseract", "rapidocr")


def configure_tesseract(tesseract_cmd: str | None) -> None:
    """Asettaa Tesseractin polun, jos se on annettu tai löytyy oletussijainnista."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        return
    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tesseract.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def page_has_text(page: pymupdf.Page) -> str:
    """Palauttaa sivun oman tekstikerroksen (tyhjä merkkijono jos ei ole)."""
    return page.get_text().strip()


def render_page_to_image(page: pymupdf.Page, dpi: int) -> Image.Image:
    """Renderöi PDF-sivun PIL-kuvaksi annetulla resoluutiolla."""
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def estimate_skew_angle(gray: Image.Image, max_angle: float = 5.0, step: float = 0.25) -> float:
    """
    Arvioi sivun vinouden asteina projektioprofiilimenetelmällä: kokeillaan
    pieniä kiertokulmia pienennetylle mustavalkokuvalle ja valitaan se kulma,
    jolla tekstirivit erottuvat terävimmin (vaakasuuntaisten rivisummien
    varianssi on suurin).
    """
    small = gray.copy()
    small.thumbnail((1000, 1000))
    binary = np.array(small.point(lambda v: 0 if v > 160 else 1))  # teksti = 1
    best_angle, best_score = 0.0, -1.0
    angle = -max_angle
    while angle <= max_angle + 1e-9:
        rotated = np.array(Image.fromarray((binary * 255).astype("uint8")).rotate(
            angle, resample=Image.BILINEAR, fillcolor=0))
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = angle, score
        angle += step
    return best_angle


def preprocess_image(image: Image.Image) -> Image.Image:
    """
    OCR-esikäsittely: harmaasävy -> vinouden korjaus -> kohinan poisto ->
    kontrastin nosto -> terävöitys. Parantaa tarkkuutta erityisesti
    huonolaatuisilla skannauksilla.
    """
    gray = ImageOps.grayscale(image)
    angle = estimate_skew_angle(gray)
    if abs(angle) >= 0.25:
        gray = gray.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    return gray


def remove_form_lines(gray: Image.Image, dpi: int) -> Image.Image:
    """
    Poistaa lomakkeiden alaviivat ja pisteviivat (esim. "..........") ennen OCR:ää,
    koska täytetyt numerot jäävät helposti viivan päälle ja OCR lukee ne väärin.
    Palauttaa binarisoidun (mustavalkoisen) kuvan. Huom: ä/ö-pisteet ja pienet
    merkit voivat rouhiutua, joten käytä vain lomakkeille ja tarkista tulos.
    """
    g = np.array(gray)
    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, int(dpi / 6) | 1, 12)
    # 1) yhtenäiset pitkät vaakaviivat
    solid = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (int(dpi * 0.4), 1)))
    solid = cv2.dilate(solid, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))
    # 2) pisteviivat: pieniä pisteitä, joita on monta samalla rivillä
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(bw, connectivity=8)
    dmax = int(dpi * 0.04)
    rows = defaultdict(list)
    for i in range(1, n):
        _, _, w, h, area = stats[i]
        if 2 <= w <= dmax and 2 <= h <= dmax and area <= dmax * dmax:
            rows[int(round(centroids[i][1] / 3))].append(i)
    dots = np.zeros_like(bw)
    for key, ids in rows.items():
        if len(ids + rows.get(key - 1, []) + rows.get(key + 1, [])) >= 8:
            for i in ids:
                dots[labels == i] = 255
    cleaned = cv2.bitwise_and(bw, cv2.bitwise_not(cv2.bitwise_or(solid, dots)))
    return Image.fromarray(255 - cleaned)


_RAPIDOCR = None


def get_rapidocr():
    """Lataa RapidOCR-moottorin vasta tarvittaessa (valinnainen riippuvuus)."""
    global _RAPIDOCR
    if _RAPIDOCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            sys.exit("RapidOCR ei ole asennettu. Asenna: python -m pip install -r requirements-rapidocr.txt")
        _RAPIDOCR = RapidOCR()
    return _RAPIDOCR


def rapidocr_recognize(image: Image.Image) -> list[tuple[list, str]]:
    """Ajaa RapidOCR:n kuvalle ja palauttaa listan (nelikulmio, teksti)."""
    result, _ = get_rapidocr()(np.array(image.convert("RGB")))
    return [(box, text) for box, text, _score in (result or [])]


def boxes_to_text(boxes: list[tuple[list, str]]) -> str:
    """
    Kokoaa RapidOCR:n tekstilaatikot riveiksi: laatikot ryhmitellään samalle
    riville pystysuuntaisen sijainnin perusteella ja järjestetään vasemmalta
    oikealle, jolloin esim. lomakkeen selite ja sen viereen kirjoitettu arvo
    päätyvät samalle riville.
    """
    items = []
    for box, text in boxes:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        items.append({"x": min(xs), "yc": sum(ys) / len(ys), "h": max(ys) - min(ys), "text": text})
    if not items:
        return ""
    heights = sorted(it["h"] for it in items)
    tolerance = 0.6 * heights[len(heights) // 2]
    items.sort(key=lambda it: it["yc"])
    lines: list[list[dict]] = []
    for it in items:
        if lines and abs(it["yc"] - sum(x["yc"] for x in lines[-1]) / len(lines[-1])) <= tolerance:
            lines[-1].append(it)
        else:
            lines.append([it])
    return "\n".join("  ".join(x["text"] for x in sorted(line, key=lambda x: x["x"])) for line in lines)


def tesseract_config(psm: int) -> str:
    """Tesseractin komentoriviasetukset: sivunjakotila (psm) ja säilytetyt välilyönnit."""
    return f"--psm {psm} -c preserve_interword_spaces=1"


def merge_ocr_and_native(ocr_text: str, native_text: str) -> str:
    """
    Yhdistää OCR-tekstin ja sivun oman tekstikerroksen. OCR-teksti kattaa kaiken
    näkyvän (myös kuvana tai vektoripolkuina olevan tekstin); sivun oma
    tekstikerros on täsmällistä (esim. käsin lisätyt numerot), joten ne rivit,
    joita ei löydy OCR-tekstistä, liitetään loppuun.
    """
    if not native_text.strip():
        return ocr_text
    norm = lambda t: re.sub(r"\s+", "", t).lower()
    ocr_norm = norm(ocr_text)
    extras = [l.strip() for l in native_text.splitlines() if l.strip() and norm(l) not in ocr_norm]
    if not extras:
        return ocr_text
    marker = "[Sivun omasta tekstikerroksesta (täsmällinen, OCR ei tunnistanut sellaisenaan):]"
    return ocr_text + "\n\n" + marker + "\n" + "\n".join(extras)


def extract_pages(pdf_path: Path, lang: str, dpi: int, psm: int = 3, preprocess: bool = True,
                  remove_lines: bool = False, engine: str = "tesseract") -> list[dict]:
    """
    Käy PDF:n sivut läpi ja palauttaa listan sanakirjoja:
        {"index": int, "text": str, "source": "native"|"ocr", "image": PIL.Image|None}

    "image" on läsnä vain OCR-sivuilla (tarvitaan hakukelpoisen PDF:n koontiin).
    RapidOCR-moottorilla sivun sanakirjassa on lisäksi "boxes" (tekstilaatikot) ja "dpi".
    Jos preprocess on True (vain Tesseract), kuva esikäsitellään (vinouden korjaus, kohinan poisto,
    kontrasti, terävöitys) ennen OCR:ää.
    """
    doc = pymupdf.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        native_text = page_has_text(page)
        has_visual = len(page.get_images(full=True)) > 0 or len(page.get_drawings()) > DRAWINGS_THRESHOLD
        if not has_visual and len(native_text) >= MIN_TEXT_CHARS:
            pages.append({"index": i, "text": native_text, "source": "native", "image": None})
            print(f"  Sivu {i + 1}: oma tekstikerros ({len(native_text)} merkkiä)")
        elif not has_visual and not native_text:
            pages.append({"index": i, "text": "", "source": "native", "image": None})
            print(f"  Sivu {i + 1}: tyhjä sivu")
        else:
            image = render_page_to_image(page, dpi)
            boxes = None
            if engine == "rapidocr":
                # RapidOCR toimii parhaiten alkuperäisellä kuvalla, esikäsittelyä ei käytetä
                boxes = rapidocr_recognize(image)
                ocr_text = boxes_to_text(boxes).strip()
            else:
                if preprocess:
                    image = preprocess_image(image)
                if remove_lines:
                    image = remove_form_lines(ImageOps.grayscale(image), dpi)
                ocr_text = pytesseract.image_to_string(image, lang=lang, config=tesseract_config(psm)).strip()
            ocr_text = ocr_text.replace("\u00ad", "-")  # pehmeä tavuviiva -> tavallinen viiva
            text = merge_ocr_and_native(ocr_text, native_text)
            source = "hybrid" if native_text else "ocr"
            pages.append({"index": i, "text": text, "source": source, "image": image,
                          "boxes": boxes, "dpi": dpi})
            extra = f", omaa tekstikerrosta {len(native_text)} merkkiä" if native_text else ""
            print(f"  Sivu {i + 1}: OCR ({len(ocr_text)} merkkiä tunnistettu{extra})")
    doc.close()
    return pages


def save_docx(pages: list[dict], pdf_path: Path, outdir: Path, lang: str) -> Path:
    """Tallentaa poimitun/OCR:atun tekstin Word-dokumenttina."""
    out_path = outdir / f"{pdf_path.stem} (teksti).docx"
    document = Document()
    document.add_heading(pdf_path.stem, level=1)

    for p in pages:
        heading = document.add_heading(f"Sivu {p['index'] + 1}", level=2)
        run = heading.runs[0] if heading.runs else heading.add_run()
        run.font.size = Pt(12)
        note = {"ocr": "(OCR)", "hybrid": "(OCR + sivun oma tekstikerros)"}.get(p["source"], "(alkuperäinen tekstikerros)")
        document.add_paragraph(note).italic = True
        for paragraph in (p["text"].split("\n\n") if p["text"] else ["(ei tekstiä)"]):
            document.add_paragraph(paragraph.strip())

    document.save(out_path)
    return out_path


def add_rapidocr_page(result: pymupdf.Document, p: dict) -> None:
    """Lisää sivun kuvana ja asettaa RapidOCR:n tunnistaman tekstin näkymättömänä sen päälle."""
    image, boxes, dpi = p["image"], p["boxes"], p["dpi"]
    scale = 72.0 / dpi
    page = result.new_page(width=image.width * scale, height=image.height * scale)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    page.insert_image(page.rect, stream=buffer.getvalue())
    font_path = find_unicode_font()
    for box, text in boxes:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        height = (max(ys) - min(ys)) * scale
        fontsize = max(4.0, height * 0.8)
        origin = (min(xs) * scale, max(ys) * scale - height * 0.15)
        page.insert_text(origin, text, fontsize=fontsize, fontname="unifont" if font_path else "helv",
                         fontfile=str(font_path) if font_path else None, render_mode=3)


def save_searchable_pdf(pdf_path: Path, pages: list[dict], outdir: Path, lang: str, psm: int = 3) -> Path:
    """
    Kokoaa hakukelpoisen PDF:n: sivut, joilla oli jo tekstikerros, kopioidaan
    sellaisenaan; OCR-sivut korvataan pytesseractin tuottamalla
    kuva+piilotekstikerros-PDF-sivulla (image_to_pdf_or_hocr).
    Huom: esikäsittely on päällä, joten OCR-sivujen kuva on suoristettu ja
    harmaasävyinen (--no-preprocess säilyttää alkuperäisen värillisen kuvan).
    """
    out_path = outdir / f"{pdf_path.stem} (hakukelpoinen).pdf"
    src = pymupdf.open(pdf_path)
    result = pymupdf.open()

    for p in pages:
        if p["source"] == "native":
            result.insert_pdf(src, from_page=p["index"], to_page=p["index"])
        elif p.get("boxes") is not None:
            add_rapidocr_page(result, p)
        else:
            # image_to_pdf_or_hocr palauttaa yhden sivun PDF:n, jossa kuva ja
            # sen päällä näkymätön (render_mode invisible) tekstikerros.
            page_pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                p["image"], lang=lang, extension="pdf", config=tesseract_config(psm)
            )
            ocr_page_doc = pymupdf.open("pdf", page_pdf_bytes)
            result.insert_pdf(ocr_page_doc)
            ocr_page_doc.close()

    result.save(out_path)
    result.close()
    src.close()
    return out_path


def find_unicode_font() -> Path | None:
    """Etsii koneelta Unicode-fontin (tukee €, ½, ä, ö jne.). Palauttaa None jos ei löydy."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in ("arial.ttf", "segoeui.ttf", "calibri.ttf", "tahoma.ttf"):
        if (windir / name).exists():
            return windir / name
    return None


def wrap_text(text: str, max_width: float, width_fn) -> list[str]:
    """
    Katkaisee tekstin riveiksi, jotka mahtuvat annettuun leveyteen. Pitkät
    katkeamattomat jonot (esim. pisteviivat) katkaistaan merkeittäin, jotta
    mikään rivi ei jää leveämmäksi kuin sivu.
    """
    width = width_fn

    lines: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            lines.append("")
            continue
        current = ""
        for word in raw.split(" "):
            candidate = word if not current else current + " " + word
            if width(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            # sana yksinään liian pitkä -> katkaistaan merkeittäin
            while width(word) > max_width:
                cut = len(word)
                while cut > 1 and width(word[:cut]) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def save_text_pdf(pages: list[dict], pdf_path: Path, outdir: Path) -> Path:
    """
    Kokoaa uuden, kevyen PDF:n, jossa teksti on aseteltu uudelleen tavallisina
    riveinä (ei alkuperäistä ulkoasua/kuvia, mutta pieni koko ja selkeä
    hakukelpoinen teksti). Rivit katkaistaan ja jaetaan tarvittaessa usealle
    sivulle, joten mitään ei jää pois vaikka teksti olisi pitkä.
    """
    out_path = outdir / f"{pdf_path.stem} (pelkkä teksti).pdf"
    doc = pymupdf.open()
    page_rect = pymupdf.paper_rect("a4")
    margin = 50
    fontsize = 11
    font_path = find_unicode_font()
    if font_path:
        font = pymupdf.Font(fontfile=str(font_path))
        fontname, fontfile = "unifont", str(font_path)
        width_fn = lambda t: font.text_length(t, fontsize=fontsize)
    else:
        # varafontti: perusfontti ei sisällä €-merkkiä, joten se korvataan tekstillä
        fontname, fontfile = "helv", None
        width_fn = lambda t: pymupdf.get_text_length(t, fontname="helv", fontsize=fontsize)
    line_height = fontsize * 1.35
    max_width = page_rect.width - 2 * margin
    lines_per_page = int((page_rect.height - 2 * margin) // line_height)

    for p in pages:
        header = f"Sivu {p['index'] + 1}" + {"ocr": " (OCR)", "hybrid": " (OCR + tekstikerros)"}.get(p["source"], "")
        body = p["text"] or "(ei tekstiä)"
        if not font_path:
            body = body.replace("€", "EUR")
        lines = [header, ""] + wrap_text(body, max_width, width_fn)
        for start in range(0, len(lines), lines_per_page):
            page = doc.new_page(width=page_rect.width, height=page_rect.height)
            y = margin + fontsize
            for line in lines[start:start + lines_per_page]:
                if line:
                    page.insert_text((margin, y), line, fontsize=fontsize, fontname=fontname,
                                     fontfile=fontfile)
                y += line_height

    doc.save(out_path)
    doc.close()
    return out_path


def ask_output_formats() -> list[str]:
    """Interaktiivinen valikko, jos --output ei ole annettu komentorivillä."""
    print("\nValitse lopputulosmuoto(t):")
    print("  1) DOCX (Word-tiedosto)")
    print("  2) Hakukelpoinen PDF (alkuperäinen ulkoasu + piilotettu tekstikerros)")
    print("  3) Pelkkä teksti PDF-muodossa (uudelleenaseteltu, kevyt)")
    print("  4) Kaikki edelliset")
    choice = input("Valinta (esim. '1' tai '1,3' tai '4'): ").strip()

    mapping = {"1": "docx", "2": "pdf-searchable", "3": "pdf-text"}
    if choice == "4":
        return ["docx", "pdf-searchable", "pdf-text"]
    selected = [mapping[c.strip()] for c in choice.split(",") if c.strip() in mapping]
    if not selected:
        print("Ei kelvollista valintaa, käytetään oletuksena DOCX.")
        return ["docx"]
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF-tiedoston OCR ja muunnos DOCX/PDF-muotoon.")
    parser.add_argument("pdf", type=Path, help="Käsiteltävä PDF-tiedosto")
    parser.add_argument(
        "--output", nargs="+", choices=sorted(VALID_OUTPUTS),
        help="Lopputulosmuoto(t). Jos jätetään pois, kysytään interaktiivisesti.",
    )
    parser.add_argument("--engine", choices=VALID_ENGINES, default="tesseract",
                        help="OCR-moottori: tesseract (oletus) tai rapidocr (syväoppiminen; ei tunnista ä/ö-merkkejä)")
    parser.add_argument("--lang", default="fin_best",
                        help="Tesseract-kielikoodi (oletus: fin_best, tarkempi suomen malli; jos sitä ei ole asennettuna, käytetään fin)")
    parser.add_argument("--dpi", type=int, default=400, help="Renderöintitarkkuus OCR-sivuille (oletus: 400)")
    parser.add_argument(
        "--psm", type=int, default=3, choices=[3, 4, 6, 11, 12],
        help="Tesseractin sivunjakotila: 3=automaattinen (oletus), 4=yksi sarake vaihtelevan kokoista tekstiä, "
             "6=yksi yhtenäinen tekstilohko (hyvä taulukoille/lomakkeille), 11/12=hajanainen teksti",
    )
    parser.add_argument("--no-preprocess", action="store_true",
                        help="Ohita kuvan esikäsittely (vinouden korjaus, kohinanpoisto, kontrasti, terävöitys)")
    parser.add_argument("--remove-lines", action="store_true",
                        help="Poista lomakkeiden alaviivat/pisteviivat ennen OCR:ää (täytetyt lomakkeet; kokeile yhdessä --psm 6 kanssa)")
    parser.add_argument("--outdir", type=Path, default=None, help="Tulostekansio (oletus: samassa kansiossa kuin PDF)")
    parser.add_argument("--tesseract-cmd", default=None, help="Polku tesseract.exe:hen, jos ei löydy PATH:ista")
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"Tiedostoa ei löydy: {args.pdf}")

    configure_tesseract(args.tesseract_cmd)

    if args.engine == "rapidocr":
        ignored = [name for name, on in (("--remove-lines", args.remove_lines),
                                         ("--psm", args.psm != 3), ("--lang", args.lang != "fin_best")) if on]
        if ignored:
            print("Huom: " + ", ".join(ignored) + " ei vaikuta RapidOCR-moottoriin.")
        print("OCR-moottori: rapidocr (ei tunnista ä/ö-merkkejä)")
    elif args.lang == "fin_best":
        try:
            installed = pytesseract.get_languages()
        except Exception:
            installed = []
        if installed and "fin_best" not in installed:
            print("Huom: fin_best-mallia ei löydy, käytetään perusmallia 'fin' (ks. README).")
            args.lang = "fin"
    if args.engine == "tesseract":
        print(f"OCR-moottori: tesseract, kieli: {args.lang}")

    outdir = args.outdir or args.pdf.parent
    outdir.mkdir(parents=True, exist_ok=True)

    outputs = args.output or ask_output_formats()

    print(f"\nKäsitellään: {args.pdf.name}")
    pages = extract_pages(args.pdf, args.lang, args.dpi, args.psm, not args.no_preprocess, args.remove_lines, args.engine)

    print("\nTallennetaan:")
    if "docx" in outputs:
        path = save_docx(pages, args.pdf, outdir, args.lang)
        print(f"  DOCX: {path}")
    if "pdf-searchable" in outputs:
        path = save_searchable_pdf(args.pdf, pages, outdir, args.lang, args.psm)
        print(f"  Hakukelpoinen PDF: {path}")
    if "pdf-text" in outputs:
        path = save_text_pdf(pages, args.pdf, outdir)
        print(f"  Pelkkä teksti PDF: {path}")

    print("\nValmis.")


if __name__ == "__main__":
    main()
