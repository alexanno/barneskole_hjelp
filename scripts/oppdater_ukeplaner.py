"""
Henter direktelenker til nyeste ukeplan (PDF) for konfigurerte trinn fra minskole.no
og skriver dem til data/ukeplaner.json, som ukeplaner.html leser (samme domene,
ingen CORS-problem).

Kjør med:
    uv run scripts/oppdater_ukeplaner.py

Kjøres normalt automatisk av .github/workflows/oppdater_ukeplaner.yml.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "lxml",
# ]
# ///

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from lxml import html

BASE_URL = "https://www.minskole.no"

# Trinn som skal vises på siden. Legg til/fjern linjer her for å endre hvilke
# trinn som er konfigurert - ukeplaner.html leser samme nøkler fra JSON-fila.
TRINN: dict[str, str] = {
    "2. trinn": "https://www.minskole.no/lovisenlund/seksjon/21656",
    "6. trinn": "https://www.minskole.no/lovisenlund/seksjon/21660",
}

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "ukeplaner.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# XPath som finner første lenke under 'Ukeplan'-seksjonen som peker til et dokument
XPATH_UKEPLAN = (
    "(//*[contains(text(), 'Ukeplan')]/following::a[contains(@href, 'Documents')])[1]"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ukeplan")


def hent_nyeste_ukeplan(url: str) -> str | None:
    """Henter full URL til den øverste ukeplanen på oppgitt minskole-side."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        tree = html.fromstring(response.content)
        elementer = tree.xpath(XPATH_UKEPLAN)

        if elementer:
            relativ_url = elementer[0].get("href")
            return urljoin(BASE_URL, relativ_url)
    except Exception as e:
        log.error("Feil ved henting fra %s: %s", url, e)

    return None


def les_eksisterende(sti: Path) -> dict:
    if sti.exists():
        try:
            return json.loads(sti.read_text(encoding="utf-8")).get("trinn", {})
        except Exception:
            return {}
    return {}


def main() -> None:
    naa = datetime.now(timezone.utc).isoformat(timespec="seconds")
    eksisterende = les_eksisterende(OUTPUT_FILE)
    resultat: dict[str, dict] = {}

    for trinn, side_url in TRINN.items():
        forrige = eksisterende.get(trinn, {})
        lenke = hent_nyeste_ukeplan(side_url)

        if lenke:
            uendret = lenke == forrige.get("pdf_url")
            resultat[trinn] = {
                "pdf_url": lenke,
                "kilde_side": side_url,
                "sist_sjekket": naa,
                "sist_funnet": forrige.get("sist_funnet", naa) if uendret else naa,
                "status": "ok",
            }
            log.info("%s: %s", trinn, lenke)
        else:
            # Behold forrige kjente lenke hvis henting feiler nå, slik at siden
            # ikke mister en fungerende lenke pga. en forbigående feil.
            resultat[trinn] = {
                **forrige,
                "kilde_side": side_url,
                "sist_sjekket": naa,
                "status": "feilet_beholder_forrige" if forrige.get("pdf_url") else "ingen_funnet",
            }
            log.warning("%s: fant ingen ukeplan-lenke", trinn)

    data = {"generert": naa, "trinn": resultat}
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("Skrev %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
