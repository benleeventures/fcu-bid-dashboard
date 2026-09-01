"""
FCU Bid Scanner — geographic + agency-type classification.

Single source of truth for the spec's two gating filters:

  §1  Geographic — hard boundary. In scope: Los Angeles, Orange, Ventura,
      San Diego counties only. Everything else (other CA counties, other
      states, federal work outside the four counties) does not appear.

  §2  Agency type — tag each bid so the tracker can prioritise the agencies
      that bid year-round and hold K-12 (dormant until February) separately.

Design notes
------------
Every scanner source already hard-filters to California before we get here
(BidNet location=43, SAM place-of-performance CA, the rest are CA-only
portals), so the real question is *which* California county — not CA vs.
non-CA. `classify_location` returns one of:

    "in"       place of performance is in one of the four counties
    "out"      place of performance is elsewhere in CA / another state —
               drop it, it must not appear
    "unknown"  the listing names no city we recognise — keep it, flag it,
               let Robert confirm the county during qualification

The primary signal is the `agency` string, which is almost always
"City of X", "X Unified School District", "County of X",
"X Community College District", etc. Titles are a weaker secondary signal.
"""

import re

FOUR_COUNTIES = ("Los Angeles", "Orange", "Ventura", "San Diego")

# ---------------------------------------------------------------------------
# Incorporated cities of the four in-scope counties
# ---------------------------------------------------------------------------

_LA_CITIES = {
    "agoura hills", "alhambra", "arcadia", "artesia", "avalon", "azusa",
    "baldwin park", "bell", "bell gardens", "bellflower", "beverly hills",
    "bradbury", "burbank", "calabasas", "carson", "cerritos", "claremont",
    "commerce", "compton", "covina", "cudahy", "culver city", "diamond bar",
    "downey", "duarte", "el monte", "el segundo", "gardena", "glendale",
    "glendora", "hawaiian gardens", "hawthorne", "hermosa beach",
    "hidden hills", "huntington park", "industry", "city of industry",
    "inglewood", "irwindale", "la canada flintridge", "la cañada flintridge",
    "la habra heights", "la mirada", "la puente", "la verne", "lakewood",
    "lancaster", "lawndale", "lomita", "long beach", "los angeles", "lynwood",
    "malibu", "manhattan beach", "maywood", "monrovia", "montebello",
    "monterey park", "norwalk", "palmdale", "palos verdes estates",
    "paramount", "pasadena", "pico rivera", "pomona", "rancho palos verdes",
    "redondo beach", "rolling hills", "rolling hills estates", "rosemead",
    "san dimas", "san fernando", "san gabriel", "san marino", "santa clarita",
    "santa fe springs", "santa monica", "sierra madre", "signal hill",
    "south el monte", "south gate", "south pasadena", "temple city",
    "torrance", "vernon", "walnut", "west covina", "west hollywood",
    "westlake village", "whittier",
}

_OC_CITIES = {
    "aliso viejo", "anaheim", "brea", "buena park", "costa mesa", "cypress",
    "dana point", "fountain valley", "fullerton", "garden grove",
    "huntington beach", "irvine", "la habra", "la palma", "laguna beach",
    "laguna hills", "laguna niguel", "laguna woods", "lake forest",
    "los alamitos", "mission viejo", "newport beach", "orange", "placentia",
    "rancho santa margarita", "san clemente", "san juan capistrano",
    "santa ana", "seal beach", "stanton", "tustin", "villa park",
    "westminster", "yorba linda",
}

_VENTURA_CITIES = {
    "camarillo", "fillmore", "moorpark", "ojai", "oxnard", "port hueneme",
    "santa paula", "simi valley", "thousand oaks", "ventura",
    "san buenaventura",
}

_SD_CITIES = {
    "carlsbad", "chula vista", "coronado", "del mar", "el cajon", "encinitas",
    "escondido", "imperial beach", "la mesa", "lemon grove", "national city",
    "oceanside", "poway", "san diego", "san marcos", "santee", "solana beach",
    "vista",
}

COUNTY_CITIES = {
    "Los Angeles": _LA_CITIES,
    "Orange": _OC_CITIES,
    "Ventura": _VENTURA_CITIES,
    "San Diego": _SD_CITIES,
}

# City names that are also common English words / brand names / share a name
# with a bigger city elsewhere. Only count these when the agency string makes
# the municipal context explicit ("City of Orange", "Town of Vista").
_AMBIGUOUS_CITIES = {
    "orange", "vista", "bell", "commerce", "industry", "vernon", "avalon",
    "paramount", "ventura", "san marcos", "la verne", "signal hill",
    "del mar", "lake forest", "santee", "brea", "ojai", "stanton",
}

# Well-known school-district abbreviations -> county. Only unambiguous ones;
# abbreviations shared across counties (PUSD, CUSD, OUSD, SUSD, VUSD…) are
# deliberately omitted so they fall through to "unknown" for Robert to check.
_DISTRICT_ABBR = {
    "lausd": "Los Angeles",   # Los Angeles Unified
    "lbusd": "Los Angeles",   # Long Beach Unified
    "sdusd": "San Diego",     # San Diego Unified
    "sduhsd": "San Diego",    # San Dieguito Union High
    "iusd": "Orange",         # Irvine Unified
    "sausd": "Orange",        # Santa Ana Unified
    "ggusd": "Orange",        # Garden Grove Unified
    "nmusd": "Orange",        # Newport-Mesa Unified
    "ouhsd": "Ventura",       # Oxnard Union High
}

# Reverse index: city -> county
_CITY_TO_COUNTY = {}
for _county, _cities in COUNTY_CITIES.items():
    for _c in _cities:
        _CITY_TO_COUNTY[_c] = _county

# ---------------------------------------------------------------------------
# Out-of-scope markers — other CA counties + their principal cities
# ---------------------------------------------------------------------------

_OUT_OF_SCOPE_MARKERS = {
    # Bay Area
    "san francisco", "oakland", "san jose", "fremont", "hayward", "berkeley",
    "sunnyvale", "santa clara", "mountain view", "palo alto", "cupertino",
    "milpitas", "san mateo", "redwood city", "daly city", "san leandro",
    "livermore", "pleasanton", "dublin", "alameda county", "alameda",
    "contra costa", "walnut creek", "concord", "richmond", "san rafael",
    "novato", "marin county", "sonoma county", "santa rosa", "petaluma",
    "napa", "solano county", "fairfield", "vacaville", "vallejo",
    # Sacramento / Central Valley
    "sacramento", "elk grove", "roseville", "rocklin", "folsom",
    "citrus heights", "rancho cordova", "davis", "woodland", "yuba city",
    "stockton", "modesto", "turlock", "tracy", "manteca", "lodi", "merced",
    "fresno", "clovis", "visalia", "tulare", "hanford", "madera",
    "bakersfield", "kern county", "delano",
    # Central Coast (outside 4)
    "santa barbara", "santa maria", "lompoc", "san luis obispo",
    "paso robles", "monterey", "salinas", "seaside", "santa cruz",
    "watsonville", "gilroy", "morgan hill", "hollister",
    # Inland Empire
    "riverside", "moreno valley", "corona", "temecula", "murrieta",
    "menifee", "hemet", "perris", "eastvale", "jurupa valley",
    "lake elsinore", "palm springs", "palm desert", "cathedral city",
    "indio", "coachella", "banning", "beaumont", "riverside county",
    "san bernardino", "fontana", "rancho cucamonga", "ontario", "rialto",
    "victorville", "hesperia", "chino", "chino hills", "upland", "redlands",
    "colton", "yucaipa", "montclair", "highland", "apple valley",
    "san bernardino county", "adelanto", "barstow",
    # Imperial (D11 with SD, but out of scope)
    "el centro", "calexico", "brawley", "imperial county",
    # Far north
    "redding", "chico", "eureka", "shasta county",
}

# Any "<name> County" that isn't one of the four is out of scope.
_IN_SCOPE_COUNTY_PHRASES = {
    "los angeles county", "la county", "orange county", "ventura county",
    "san diego county",
}
_COUNTY_PHRASE_RE = re.compile(r"\b([a-z][a-z .'-]+?) county\b")

# ---------------------------------------------------------------------------
# Out-of-state markers — a place string that names a US state other than
# California is out, full stop. Federal sources (SAM.gov) and BidNet
# occasionally leak non-CA work past their own place-of-performance filters
# (e.g. a USCG base in Honolulu). "unknown" is for *ambiguous* CA listings —
# a clearly out-of-state one should be dropped, not flagged.
# ---------------------------------------------------------------------------

_US_STATE_NAMES_OUT = {
    "alabama", "alaska", "arizona", "arkansas", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana",
    "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico", "guam", "american samoa",
    "northern mariana islands", "u.s. virgin islands", "virgin islands",
}

# USPS codes for the same. Only matched in a "City, XX" / "City, XX 12345"
# context so we don't trip on words like "or", "in", "hi", "me".
_US_STATE_CODES_OUT = {
    "al", "ak", "az", "ar", "co", "ct", "de", "fl", "ga", "hi", "id", "il",
    "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo",
    "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or",
    "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi",
    "wy", "dc", "pr", "gu", "vi",
}

# Unambiguous non-CA place names that show up in federal solicitations with no
# accompanying state string (military bases especially). Kept deliberately
# short and free of names that collide with CA cities or common words.
_OUT_OF_STATE_PLACES = {
    "honolulu", "pearl harbor", "hickam", "schofield barracks", "kaneohe",
    "wahiawa", "ewa beach", "kapolei", "waipahu", "mililani", "hilo", "oahu",
    "maui", "kauai", "molokai", "guam", "tinian", "saipan",
    "las vegas", "north las vegas", "anchorage", "fairbanks", "juneau",
}

_STATE_COMMA_RE = re.compile(r",\s*([a-z][a-z. ]*[a-z]|[a-z]{2})\b")
_STATE_OF_RE = re.compile(
    r"\b(?:state|commonwealth|territory) of ([a-z][a-z ]+?)\b")


def _is_out_of_state(blob: str) -> bool:
    """blob is an already-lowercased 'agency place_text — title' string."""
    for m in _STATE_COMMA_RE.finditer(blob):
        cand = m.group(1).strip().rstrip(".")
        if cand in _US_STATE_NAMES_OUT or cand in _US_STATE_CODES_OUT:
            return True
    m = _STATE_OF_RE.search(blob)
    if m and m.group(1).strip() in _US_STATE_NAMES_OUT:
        return True
    return any(re.search(rf"\b{re.escape(p)}\b", blob) for p in _OUT_OF_STATE_PLACES)

# ---------------------------------------------------------------------------
# Agency-type rules — first match wins
# ---------------------------------------------------------------------------

_AGENCY_TYPE_RULES = [
    ("k12", re.compile(
        r"unified school district|\bschool district\b|joint union|"
        r"\bhigh school district\b|\belementary school district\b|"
        r"county office of education|"
        r"\b[a-z]{1,6}u[hr]?sd\b|\busd\b", re.I)),  # LAUSD / SDUSD / IUSD / SDUHSD
    ("ccd", re.compile(r"community college|\bcity college\b", re.I)),
    ("transit", re.compile(
        r"\bmetro\b|\bMTA\b|\bOCTA\b|\bMTS\b|metrolink|\bVCTC\b|\bLACMTA\b|"
        r"transportation authority|transit district|transit authority|"
        r"metropolitan transportation", re.I)),
    ("housing", re.compile(
        r"housing authority|housing commission|development authority|\bHACLA\b|"
        r"\bLACDA\b|community development commission", re.I)),
    ("airport", re.compile(
        r"\bairport\b|world airports|\bLAWA\b|\bLAX\b|john wayne", re.I)),
    ("port", re.compile(r"\bport of\b|harbor department", re.I)),
    ("special_district", re.compile(
        r"water district|water authority|municipal water|sanitation district|"
        r"utility district|public utilit|\bDWP\b|irrigation district|"
        r"flood control|parks district|recreation.{0,3}park district|"
        r"library district|cemetery district|resource conservation", re.I)),
    ("county", re.compile(
        r"county of |\bLA County\b|los angeles county|orange county|"
        r"ventura county|san diego county|county sanitation|county public works",
        re.I)),
    ("state", re.compile(
        r"department of |\bcaltrans\b|\bCHP\b|\bDMV\b|\bDGS\b|\bDVBE\b|"
        r"state of california|\bCSU\b|cal state|california state university|"
        r"university of california|state parks|\bdirector of general services\b",
        re.I)),
    ("city", re.compile(r"\bcity of |\btown of |\bcity\b|\bmunicipal\b", re.I)),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _extract_place(agency_l: str) -> str | None:
    """Pull the municipality/place name out of a formatted agency string."""
    for pat in (
        r"city of ([a-z .'-]+)",
        r"town of ([a-z .'-]+)",
        r"county of ([a-z .'-]+)",
        r"^([a-z .'-]+?) unified school district",
        r"^([a-z .'-]+?) school district",
        r"^([a-z .'-]+?) community college district",
        r"^([a-z .'-]+?) (?:municipal |county )?water district",
        r"^([a-z .'-]+?) housing authority",
    ):
        m = re.search(pat, agency_l)
        if m:
            return m.group(1).strip(" .'-")
    return None


def _county_for_city(name: str, explicit_municipal: bool) -> str | None:
    """Return the in-scope county for a city name, or None."""
    if not name:
        return None
    name = name.strip()
    if name not in _CITY_TO_COUNTY:
        return None
    if name in _AMBIGUOUS_CITIES and not explicit_municipal:
        return None
    return _CITY_TO_COUNTY[name]


def classify_location(title: str, agency: str, state: str | None = None,
                      known_county: str | None = None,
                      place_text: str = "") -> dict:
    """
    Classify a bid's place of performance.

    place_text — optional extra location string (e.g. a "Place of Performance"
    line scraped from SAM.gov). Weighted the same as the agency string.

    Returns {"county": <one of FOUR_COUNTIES or None>,
             "geo_status": "in" | "out" | "unknown"}.
    """
    if known_county in FOUR_COUNTIES:
        return {"county": known_county, "geo_status": "in"}

    if state and _norm(state) not in ("", "california", "ca"):
        return {"county": None, "geo_status": "out"}

    agency_l = _norm(f"{agency} {place_text}")
    title_l = _norm(title)
    blob = f"{agency_l} — {title_l}"

    # 0. Known school-district abbreviation
    for abbr, county in _DISTRICT_ABBR.items():
        if re.search(rf"\b{abbr}\b", agency_l):
            return {"county": county, "geo_status": "in"}

    # 1. Explicit county phrase anywhere
    for phrase in _IN_SCOPE_COUNTY_PHRASES:
        if phrase in blob:
            county = "Los Angeles" if phrase in ("los angeles county", "la county") else \
                     "Orange" if phrase == "orange county" else \
                     "Ventura" if phrase == "ventura county" else "San Diego"
            return {"county": county, "geo_status": "in"}

    # 1b. Names a US state / territory other than California, or a well-known
    #     out-of-state place -> out. Checked after the in-scope positives above
    #     so an in-district school named "Washington" isn't caught here.
    if _is_out_of_state(blob):
        return {"county": None, "geo_status": "out"}

    # 2. Any other "<x> County" phrase -> out
    for m in _COUNTY_PHRASE_RE.finditer(blob):
        if f"{m.group(1).strip()} county" not in _IN_SCOPE_COUNTY_PHRASES:
            return {"county": None, "geo_status": "out"}

    # 3. Place name extracted from the agency string (strongest signal)
    place = _extract_place(agency_l)
    if place:
        county = _county_for_city(place, explicit_municipal=True)
        if county:
            return {"county": county, "geo_status": "in"}
        # extracted a real place that isn't in our four counties
        if place in _OUT_OF_SCOPE_MARKERS:
            return {"county": None, "geo_status": "out"}

    # 4. In-scope city name appearing in the agency string
    for city, county in _CITY_TO_COUNTY.items():
        if city in _AMBIGUOUS_CITIES:
            continue
        if re.search(rf"\b{re.escape(city)}\b", agency_l):
            return {"county": county, "geo_status": "in"}

    # 5. Out-of-scope marker anywhere
    for marker in _OUT_OF_SCOPE_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", blob):
            return {"county": None, "geo_status": "out"}

    # 6. In-scope city name in the title (weaker, but better than nothing)
    for city, county in _CITY_TO_COUNTY.items():
        if city in _AMBIGUOUS_CITIES:
            continue
        if re.search(rf"\b{re.escape(city)}\b", title_l):
            return {"county": county, "geo_status": "in"}

    return {"county": None, "geo_status": "unknown"}


def classify_agency(agency: str, source: str = "") -> dict:
    """Return {"agency_type": str, "is_k12": bool}."""
    text = agency or ""
    for kind, pat in _AGENCY_TYPE_RULES:
        if pat.search(text):
            return {"agency_type": kind, "is_k12": kind == "k12"}
    return {"agency_type": "unknown", "is_k12": False}


# ---------------------------------------------------------------------------
# Portal -> county overrides for portals whose label isn't a plain city name
# ---------------------------------------------------------------------------

PORTAL_COUNTY = {
    "la community college district": "Los Angeles",
    "laccd": "Los Angeles",
    "port of long beach": "Los Angeles",
    "cal state la": "Los Angeles",
    "la county office of education": "Los Angeles",
    "norwalk / montebello": "Los Angeles",
    "coast ccd": "Orange",
    "coast community college district": "Orange",
    "south orange county ccd": "Orange",
    "rancho santiago ccd": "Orange",
    "ventura county ccd": "Ventura",
    "san diego ccd": "San Diego",
    "grossmont-cuyamaca ccd": "San Diego",
    "miracosta ccd": "San Diego",
    "palomar ccd": "San Diego",
    "la county public works": "Los Angeles",
    "county of orange": "Orange",
    "county of ventura": "Ventura",
    "county of san diego": "San Diego",
}


def portal_county(bid: dict) -> str | None:
    """
    For portal-based sources (PlanetBids, OpenGov) the agency label maps
    directly to a known city/county. Returns the in-scope county or None.
    """
    if bid.get("source") not in ("PlanetBids", "OpenGov"):
        return None
    agency_l = _norm(bid.get("agency"))
    if not agency_l:
        return None
    if agency_l in PORTAL_COUNTY:
        return PORTAL_COUNTY[agency_l]
    # plain city name
    county = _county_for_city(agency_l, explicit_municipal=True)
    if county:
        return county
    # "city of x" style label
    place = _extract_place(agency_l)
    if place:
        return _county_for_city(place, explicit_municipal=True)
    return None


def enrich(bid: dict) -> dict:
    """Add county / geo_status / agency_type / is_k12 to a bid dict in place."""
    # A county already stamped by the source (e.g. PlanetBids portal config)
    # wins; otherwise fall back to the portal map, then to text classification.
    known = bid.get("county") if bid.get("county") in FOUR_COUNTIES else portal_county(bid)
    bid.update(classify_location(
        bid.get("title", ""), bid.get("agency", ""), bid.get("state"), known,
        place_text=bid.get("pop_raw", "")))
    bid.update(classify_agency(bid.get("agency", ""), bid.get("source", "")))
    return bid
