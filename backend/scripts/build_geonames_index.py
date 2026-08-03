"""Build a slim GeoNames cities index for Samara place resolution.

Downloads GeoNames cities15000 + admin1 names (CC-BY), writes a compact
pickle consumed by place_resolve.py.

Usage (from backend/):
  python scripts/build_geonames_index.py
"""

from __future__ import annotations

import io
import pickle
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "geonames"
OUT_FILE = OUT_DIR / "cities15000_slim.pkl"

CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

# ISO2 → English display name (common set; unknown codes fall back to code).
COUNTRY_NAMES: dict[str, str] = {
    "IN": "India",
    "PK": "Pakistan",
    "BD": "Bangladesh",
    "NP": "Nepal",
    "LK": "Sri Lanka",
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "SG": "Singapore",
    "MY": "Malaysia",
    "NP": "Nepal",
    "BT": "Bhutan",
    "MM": "Myanmar",
    "TH": "Thailand",
    "ID": "Indonesia",
    "PH": "Philippines",
    "CN": "China",
    "JP": "Japan",
    "KR": "South Korea",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
    "IE": "Ireland",
    "NZ": "New Zealand",
    "ZA": "South Africa",
    "NG": "Nigeria",
    "KE": "Kenya",
    "EG": "Egypt",
    "TR": "Turkey",
    "RU": "Russia",
    "BR": "Brazil",
    "MX": "Mexico",
    "AR": "Argentina",
    "QA": "Qatar",
    "KW": "Kuwait",
    "OM": "Oman",
    "BH": "Bahrain",
}


def _download(url: str) -> bytes:
    print(f"Downloading {url} ...")
    with urlopen(url, timeout=120) as resp:
        return resp.read()


def _load_admin1(raw: bytes) -> dict[str, str]:
    """Map 'IN.24' → 'Rajasthan'."""
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        out[parts[0]] = parts[1]
    return out


def _parse_cities(txt: bytes, admin1: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for line in txt.decode("utf-8", errors="replace").splitlines():
        if not line:
            continue
        p = line.split("\t")
        if len(p) < 15:
            continue
        name = p[1].strip()
        ascii_name = (p[2] or name).strip()
        alts_raw = (p[3] or "").strip()
        try:
            lat = float(p[4])
            lon = float(p[5])
            pop = int(p[14] or 0)
        except ValueError:
            continue
        cc = (p[8] or "").strip().upper()
        a1_code = (p[10] or "").strip()
        admin1_name = admin1.get(f"{cc}.{a1_code}", a1_code) if a1_code else ""
        country = COUNTRY_NAMES.get(cc, cc)
        # Keep a few alternate names (cap to limit size)
        alts = []
        for a in alts_raw.split(","):
            a = a.strip()
            if a and a.lower() not in {name.lower(), ascii_name.lower()}:
                alts.append(a)
            if len(alts) >= 8:
                break
        display_parts = [name]
        if admin1_name and admin1_name.lower() != name.lower():
            display_parts.append(admin1_name)
        if country:
            display_parts.append(country)
        rows.append(
            {
                "name": name,
                "ascii": ascii_name,
                "alts": alts,
                "lat": lat,
                "lon": lon,
                "cc": cc,
                "admin1": admin1_name,
                "country": country,
                "pop": pop,
                "display": ", ".join(display_parts),
            }
        )
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    admin1 = _load_admin1(_download(ADMIN1_URL))
    zdata = _download(CITIES_URL)
    with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        if not names:
            raise SystemExit("cities15000.zip had no .txt")
        city_txt = zf.read(names[0])
    rows = _parse_cities(city_txt, admin1)
    rows.sort(key=lambda r: -int(r.get("pop") or 0))
    OUT_FILE.write_bytes(pickle.dumps(rows, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"Wrote {len(rows)} cities -> {OUT_FILE} ({OUT_FILE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
