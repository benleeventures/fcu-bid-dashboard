"""
FCU Bid Scanner — geographic + agency-type classification.

Single source of truth for the spec's two gating filters:

  §1  Geographic — hard boundary. In scope (Phase 2, Ben 2026-10-21: "San
      Diego to Bakersfield, Inland Empire included"): Los Angeles, Ventura,
      Kern (North) and Orange, Riverside, San Bernardino, San Diego (South).
      Everything else (other CA counties, other states) does not appear.
      Every in-scope bid also gets a region — North routes to Melvin, South
      to Robert.

  §2  Agency type — tag each bid so the tracker can prioritise the agencies
      that bid year-round and hold K-12 (dormant until February) separately.

Design notes
------------
Every scanner source already hard-filters to California before we get here
(BidNet location=43, SAM place-of-performance CA, the rest are CA-only
portals), so the real question is *which* California county — not CA vs.
non-CA. `classify_location` returns one of:

    "in"       place of performance is in one of the in-scope counties
    "out"      place of performance is elsewhere in CA / another state —
               drop it, it must not appear
    "unknown"  the listing names no city we recognise — keep it, flag it,
               let Robert confirm the county during qualification

The primary signal is the `agency` string, which is almost always
"City of X", "X Unified School District", "County of X",
"X Community College District", etc. Titles are a weaker secondary signal.
"""

import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


# Name is legacy (used to be exactly four) — now seven counties. Left unrenamed
# since other modules import it by this name.
FOUR_COUNTIES = ("Los Angeles", "Orange", "Ventura", "Kern", "Riverside",
                  "San Bernardino", "San Diego")

# Region routing (Phase 2): North -> Melvin, South -> Robert.
COUNTY_REGION = {
    "Los Angeles": "North", "Ventura": "North", "Kern": "North",
    "Orange": "South", "Riverside": "South", "San Bernardino": "South",
    "San Diego": "South",
}


def region_for(county: str | None) -> str | None:
    """'North' | 'South' for an in-scope county, else None."""
    return COUNTY_REGION.get(county or "")

# ---------------------------------------------------------------------------
# Incorporated cities of the in-scope counties
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

_KERN_CITIES = {
    "bakersfield", "delano", "shafter", "wasco", "arvin", "mcfarland",
    "tehachapi", "taft", "ridgecrest", "california city", "maricopa",
}

_RIVERSIDE_CITIES = {
    "riverside", "moreno valley", "corona", "temecula", "murrieta",
    "menifee", "hemet", "perris", "eastvale", "jurupa valley",
    "lake elsinore", "palm springs", "palm desert", "cathedral city",
    "indio", "coachella", "banning", "beaumont", "indian wells", "la quinta",
    "rancho mirage", "desert hot springs", "norco", "wildomar", "calimesa",
    "canyon lake",
}

_SAN_BERNARDINO_CITIES = {
    "san bernardino", "fontana", "rancho cucamonga", "ontario", "rialto",
    "victorville", "hesperia", "chino", "chino hills", "upland", "redlands",
    "colton", "yucaipa", "montclair", "highland", "apple valley", "adelanto",
    "barstow", "big bear lake", "loma linda", "needles", "twentynine palms",
    "yucca valley", "grand terrace",
}

COUNTY_CITIES = {
    "Los Angeles": _LA_CITIES,
    "Orange": _OC_CITIES,
    "Ventura": _VENTURA_CITIES,
    "Kern": _KERN_CITIES,
    "Riverside": _RIVERSIDE_CITIES,
    "San Bernardino": _SAN_BERNARDINO_CITIES,
    "San Diego": _SD_CITIES,
}

# City names that are also common English words / brand names / share a name
# with a bigger city elsewhere. Only count these when the agency string makes
# the municipal context explicit ("City of Orange", "Town of Vista").
_AMBIGUOUS_CITIES = {
    "orange", "vista", "bell", "commerce", "industry", "vernon", "avalon",
    "paramount", "ventura", "san marcos", "la verne", "signal hill",
    "del mar", "lake forest", "santee", "brea", "ojai", "stanton",
    "riverside", "highland", "norco",
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

# Neighborhoods / unincorporated communities that show up as a bid's location
# but aren't incorporated cities (mostly City of LA neighborhoods). Only names
# that don't collide with a place elsewhere in CA.
_PLACE_COUNTY = {
    **dict.fromkeys((
        "northridge", "chatsworth", "van nuys", "north hollywood", "sherman oaks",
        "encino", "tarzana", "woodland hills", "canoga park", "reseda", "sylmar",
        "pacoima", "granada hills", "porter ranch", "studio city", "panorama city",
        "san pedro", "wilmington", "harbor city", "valencia", "newhall", "saugus",
        "canyon country", "stevenson ranch", "altadena", "hacienda heights",
        "rowland heights", "east los angeles", "boyle heights", "watts",
    ), "Los Angeles"),
    **dict.fromkeys(("newbury park", "oak park"), "Ventura"),
    **dict.fromkeys(("rosamond", "lamont", "oildale", "mojave", "frazier park",
                     "boron"), "Kern"),
    **dict.fromkeys(("ladera ranch", "coto de caza", "rossmoor", "midway city"),
                    "Orange"),
}

# Community college districts / colleges, CSU and UC campuses in scope. Matched
# as substrings of the agency (then title) — these institutions post on the
# statewide feeds (BidNet, VendorLine, Cal eProcure) with no city in the name.
_INSTITUTION_COUNTY = {
    **dict.fromkeys((
        "los angeles community college", "laccd", "pasadena city college",
        "pasadena area community college", "glendale community college",
        "long beach city college", "long beach community college",
        "el camino college", "el camino community college", "compton college",
        "compton community college", "santa monica college",
        "santa monica community college", "college of the canyons",
        "santa clarita community college", "rio hondo college",
        "rio hondo community college", "cerritos college",
        "cerritos community college", "citrus college", "citrus community college",
        "mt. san antonio", "mt san antonio", "mount san antonio",
        "antelope valley college", "antelope valley community college",
        "northridge", "csun", "cal state la", "cal state los angeles",
        "california state university, los angeles", "csulb", "long beach state",
        "california state university, long beach", "dominguez hills",
        "cal poly pomona", "ucla", "university of california, los angeles",
    ), "Los Angeles"),
    **dict.fromkeys((
        "ventura county community college", "moorpark college", "oxnard college",
        "ventura college", "channel islands",
    ), "Ventura"),
    **dict.fromkeys((
        "kern community college", "bakersfield college", "cerro coso",
        "csu bakersfield", "cal state bakersfield",
        "california state university, bakersfield",
    ), "Kern"),
    **dict.fromkeys((
        "coast community college", "golden west college", "orange coast college",
        "north orange county community college", "fullerton college",
        "cypress college", "rancho santiago", "santa ana college",
        "santiago canyon college", "south orange county community college",
        "saddleback college", "irvine valley college", "cal state fullerton",
        "csuf", "california state university, fullerton", "uc irvine",
        "university of california, irvine",
    ), "Orange"),
    **dict.fromkeys((
        "riverside community college", "norco college", "moreno valley college",
        "mt. san jacinto", "mt san jacinto", "mount san jacinto",
        "desert community college", "college of the desert", "uc riverside",
        "university of california, riverside",
    ), "Riverside"),
    **dict.fromkeys((
        "san bernardino community college", "san bernardino valley college",
        "crafton hills", "chaffey", "victor valley college",
        "victor valley community college", "barstow community college",
        "copper mountain college", "cal state san bernardino", "csusb",
        "california state university, san bernardino",
    ), "San Bernardino"),
    **dict.fromkeys((
        "san diego community college", "miramar college", "san diego mesa college",
        "san diego city college", "grossmont", "cuyamaca", "miracosta",
        "palomar college", "palomar community college", "southwestern college",
        "southwestern community college", "san diego state", "sdsu",
        "cal state san marcos", "csusm", "uc san diego", "ucsd",
        "university of california, san diego",
    ), "San Diego"),
}
_INSTITUTION_RE = [(re.compile(rf"\b{re.escape(k)}\b"), c)
                   for k, c in _INSTITUTION_COUNTY.items()]

# ---------------------------------------------------------------------------
# K-12 school district -> county, for every CA district (CDE directory via
# gis.data.ca.gov "California School District Offices 2025-26", refresh with
# data/refresh_school_districts.py). Resolves districts in AND out of scope:
# "Sulphur Springs Union School District" -> Los Angeles, "Kern High School
# District" -> Kern, "Sacramento City Unified" -> out.
# ---------------------------------------------------------------------------

_DISTRICT_TYPE_WORDS_RE = re.compile(
    r"\b(?:school district|unified|union|joint|elementary|high|district|"
    r"school|schools|usd|uhsd|esd|jusd|juhsd|sd)\b")
_DISTRICT_MARKER_RE = re.compile(
    r"\b(?:unified|school district|usd|uhsd|esd|jusd|juhsd)\b")


def _district_core(name: str) -> str:
    n = _norm(name).replace("-", " ")
    n = _DISTRICT_TYPE_WORDS_RE.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip(" .,'")


def _load_school_districts() -> dict[str, str | None]:
    """district core name -> county (None when the core is shared across counties)."""
    import csv
    import os
    path = os.path.join(os.path.dirname(__file__), "data", "ca_school_districts.csv")
    index: dict[str, set] = {}
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if row["district_type"] not in ("Unified", "Elementary", "High"):
                    continue
                core = _district_core(row["district_name"])
                if core:
                    index.setdefault(core, set()).add(row["county"])
    except OSError:
        return {}
    return {core: (next(iter(c)) if len(c) == 1 else None) for core, c in index.items()}


_SCHOOL_DISTRICT_COUNTY = _load_school_districts()


def school_district_county(text: str) -> str | None:
    """
    Find a school district named in `text` and return its county (any CA
    county, in scope or not). Looks at up to six words before each district
    marker ("Unified", "School District", "USD"…), longest match first.
    """
    text_l = _norm(text).replace("-", " ")
    for m in _DISTRICT_MARKER_RE.finditer(text_l):
        words = re.sub(r"[^a-z0-9 .']", " ", text_l[:m.start()]).split()[-6:]
        for j in range(len(words), 0, -1):
            core = _district_core(" ".join(words[-j:]))
            if core in _SCHOOL_DISTRICT_COUNTY:
                county = _SCHOOL_DISTRICT_COUNTY[core]
                if county:
                    return county
                break
    return None

# ---------------------------------------------------------------------------
# Drive-time bands from the FCU shop (9601 Cozycroft Ave, Chatsworth 91311).
# Used by scoring.py — geography is not a gate, it just lowers the score for
# farther jobs. Band A ≈ ≤45 min, B ≈ ≤75 min, C ≈ ≤110 min, D ≈ >110 min.
# Includes San Fernando Valley neighborhood names (not incorporated cities) since
# the parser's project_city is often a neighborhood.
# ---------------------------------------------------------------------------

_BAND_A_CITIES = frozenset({
    # SFV + immediate foothills / Santa Clarita / east Ventura county
    "chatsworth", "canoga park", "winnetka", "woodland hills", "west hills",
    "reseda", "northridge", "porter ranch", "granada hills", "mission hills",
    "north hills", "sylmar", "pacoima", "sun valley", "panorama city",
    "van nuys", "sepulveda", "north hollywood", "valley village", "valley glen",
    "sherman oaks", "studio city", "encino", "tarzana", "lake balboa",
    "arleta", "shadow hills", "tujunga", "sunland",
    "san fernando", "burbank", "glendale", "la crescenta", "montrose",
    "la canada flintridge", "la cañada flintridge",
    "santa clarita", "valencia", "newhall", "saugus", "canyon country", "stevenson ranch",
    "agoura hills", "agoura", "calabasas", "hidden hills", "westlake village", "oak park",
    "simi valley", "moorpark", "thousand oaks", "newbury park",
})

_BAND_B_CITIES = frozenset({
    # Central LA basin + rest of Ventura county
    "los angeles", "hollywood", "west hollywood", "beverly hills", "century city",
    "brentwood", "west los angeles", "mar vista", "palms", "culver city",
    "santa monica", "pacific palisades", "playa vista", "playa del rey", "venice",
    "marina del rey", "westchester", "el segundo",
    "pasadena", "south pasadena", "altadena", "san marino", "alhambra",
    "monterey park", "montebello", "rosemead", "san gabriel", "temple city",
    "arcadia", "monrovia", "duarte", "bradbury", "sierra madre",
    "el monte", "south el monte", "baldwin park", "irwindale", "azusa",
    "glendora", "covina", "west covina", "la verne", "san dimas", "claremont",
    "pomona", "diamond bar", "walnut", "eagle rock", "highland park",
    "inglewood", "hawthorne", "lawndale", "gardena", "hermosa beach",
    "manhattan beach", "lennox", "view park", "windsor hills", "ladera heights",
    "oxnard", "ventura", "san buenaventura", "camarillo", "port hueneme",
    "santa paula", "fillmore", "ojai",
})

_BAND_C_CITIES = frozenset({
    # South Bay, SE LA county, Gateway cities, north Orange County, Antelope Valley
    "torrance", "carson", "redondo beach", "palos verdes estates",
    "rancho palos verdes", "rolling hills", "rolling hills estates", "lomita",
    "san pedro", "wilmington", "harbor city", "long beach", "signal hill",
    "compton", "lynwood", "south gate", "huntington park", "bell", "bell gardens",
    "cudahy", "maywood", "vernon", "commerce", "pico rivera", "whittier",
    "santa fe springs", "norwalk", "downey", "bellflower", "paramount",
    "lakewood", "cerritos", "artesia", "hawaiian gardens", "la mirada",
    "la habra heights", "industry", "city of industry", "hacienda heights",
    "rowland heights", "la puente", "avocado heights", "walnut park",
    "palmdale", "lancaster",
    "la habra", "brea", "fullerton", "buena park", "la palma", "cypress",
    "anaheim", "placentia", "yorba linda", "stanton", "garden grove", "orange",
    "villa park", "santa ana", "westminster", "fountain valley", "los alamitos",
    "seal beach", "midway city",
    # Western Inland Empire — closest Riverside/San Bernardino county cities
    "ontario", "rancho cucamonga", "fontana", "chino", "chino hills",
    "upland", "montclair", "rialto", "colton", "san bernardino", "redlands",
    "highland", "loma linda", "grand terrace", "riverside", "corona", "norco",
})

# Deep south Orange County — kept explicit so Orange County's default (C) does
# not apply. Every San Diego city falls through to the county default (D).
_BAND_D_CITIES = frozenset({
    "irvine", "tustin", "costa mesa", "newport beach", "newport coast",
    "lake forest", "laguna hills", "laguna woods", "laguna beach",
    "laguna niguel", "aliso viejo", "mission viejo", "rancho santa margarita",
    "coto de caza", "ladera ranch", "san juan capistrano", "san clemente",
    "dana point", "trabuco canyon", "foothill ranch",
})

_COUNTY_DEFAULT_BAND = {
    "Ventura": "B",
    "Kern": "D",
    "Los Angeles": "C",
    "Orange": "C",
    "Riverside": "D",
    "San Bernardino": "D",
    "San Diego": "D",
}


def drive_band(city: str | None, county: str | None) -> str | None:
    """Drive-time band ('A'|'B'|'C'|'D') from the Chatsworth shop, resolved from
    the job-site city when known, else the county default. None when neither is
    usable (caller treats that as 'location unknown')."""
    c = _norm(city).strip(" .,'-") if city else ""
    if c:
        if c in _BAND_A_CITIES:
            return "A"
        if c in _BAND_B_CITIES:
            return "B"
        if c in _BAND_C_CITIES:
            return "C"
        if c in _BAND_D_CITIES:
            return "D"
        # a city we don't recognise — fall through to the county default
    if county in _COUNTY_DEFAULT_BAND:
        return _COUNTY_DEFAULT_BAND[county]
    return None

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
    "porterville", "lemoore",
    # Central Coast (outside scope)
    "santa barbara", "santa maria", "lompoc", "san luis obispo",
    "paso robles", "monterey", "salinas", "seaside", "santa cruz",
    "watsonville", "gilroy", "morgan hill", "hollister",
    # Imperial (D11 with SD, but out of scope)
    "el centro", "calexico", "brawley", "imperial county",
    # Far north
    "redding", "chico", "eureka", "shasta county",
}

# Any "<name> County" that isn't in scope is out of scope.
_COUNTY_PHRASE_TO_COUNTY = {
    "los angeles county": "Los Angeles",
    "la county": "Los Angeles",
    "orange county": "Orange",
    "ventura county": "Ventura",
    "kern county": "Kern",
    "riverside county": "Riverside",
    "san bernardino county": "San Bernardino",
    "san diego county": "San Diego",
}
_IN_SCOPE_COUNTY_PHRASES = set(_COUNTY_PHRASE_TO_COUNTY)
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
        r"ventura county|kern county|riverside county|san bernardino county|"
        r"san diego county|county sanitation|county public works",
        re.I)),
    ("state", re.compile(
        r"department of |\bcaltrans\b|\bCHP\b|\bDMV\b|\bDGS\b|\bDVBE\b|"
        r"state of california|\bCSU\b|cal state|california state university|"
        r"university of california|\bUC\s?(?:LA|I|SD|SB|R|D|SC|SF|M)\b|"
        r"regents of the university|state parks|\bdirector of general services\b",
        re.I)),
    ("city", re.compile(r"\bcity of |\btown of |\bcity\b|\bmunicipal\b", re.I)),
]


# ---------------------------------------------------------------------------
# Federal work (Phase 2 scope, Ben 2026-10-21): VA, military bases and other
# federal agencies are cut from the daily feed. SAM.gov is the source of record
# for federal contract opportunities and now runs weekly (scanner.run_scan);
# federal rows that other aggregators (BidNet especially) mirror are dropped.
# Deliberately avoids generic "Department of X" — California has its own
# Departments of Transportation, Justice, General Services, etc.
# ---------------------------------------------------------------------------

_FEDERAL_TEXT_RE = re.compile(
    r"\bveterans affairs\b|\bvamc\b|\bvahcs\b|\bvaglahs\b|"
    r"\bva\b.{0,40}\b(?:medical|health ?care|hospital|clinic|campus)\b|"
    r"\b(?:army|navy|air force|defense|homeland security|veterans affairs),"
    r" department of\b|"
    r"\bdept\.? of (?:the )?(?:army|navy|air force|defense|homeland security)\b|"
    r"\bdepartment of (?:the )?(?:army|navy|air force|defense|homeland security)\b|"
    r"\bu\.?s\.? (?:army|navy|air force|coast guard|marine corps|forest service|"
    r"postal service|department of)\b|"
    r"\bunited states (?:army|navy|air force|coast guard|marine corps)\b|"
    r"\bair force base\b|\bafb\b|\bspace force\b|\bnaval\b|\bnavfac\b|"
    r"\bmarine corps\b|\bmcas\b|\bcoast guard\b|\buscg\b|\barmy corps\b|\busace\b|"
    r"\bnational guard\b|\bgeneral services administration\b|\bgsa\b|"
    r"\bfederal (?:building|bureau|aviation|courthouse|correctional)\b|"
    r"\bvandenberg\b|\bmcclellan\b|\bcamp pendleton\b|\bfort irwin\b|"
    r"\bedwards air\b|\bchina lake\b|\bpoint mugu\b|\bnbvc\b|\bnaval base\b|"
    r"\bmarch air reserve\b",   # not bare "miramar" — Miramar College is SD CCD
    re.I)

# Federal solicitation-number shapes (title or bid ID). VA "36C26327Q0019",
# DoD "W912HQ26PA083" / "N4008526R0435" / "FA309926D0004" / "SP4701…",
# USCG "70Z03326P…", GSA "47PD5527Q0010", USDA "1232SA26P0751", and the
# PSC-prefixed VA project titles BidNet mirrors ("Z2DA--612A4-27-018").
_FEDERAL_SOLICITATION_RE = re.compile(
    r"\b36C\d{5}[A-Z]\d{4}\b|"
    r"\b(?:W9\d{2}[A-Z0-9]{2}|N\d{5}|FA\d{4}|SP\d{4}|HQ\d{4}|M\d{5})\d{2}[A-Z][A-Z0-9]{4}\b|"
    r"\b70Z0\d{3}\d{2}[A-Z]|\b47P[A-Z0-9]{3}\d{2}[A-Z]\d{4}\b|"
    r"\b12\d{2}[A-Z0-9]{2}\d{2}[A-Z]\d{4}\b|"
    r"\b[A-Z]\d[A-Z]{2}--|\b\d{3}[A-Z]\d-\d{2}-\d{3}\b")


def is_federal(title: str, agency: str = "", bid_id: str = "") -> bool:
    """True when a bid is federal work (VA, military, other federal agency)."""
    text = f"{agency or ''} — {title or ''}"
    if _FEDERAL_TEXT_RE.search(text):
        return True
    return bool(_FEDERAL_SOLICITATION_RE.search(f"{title or ''} {bid_id or ''}"))


# In-area federal installations whose SAM.gov place-of-performance city isn't an
# incorporated city in COUNTY_CITIES. Lets the weekly SAM.gov check keep in-area
# federal work (it's dropped as "unknown" otherwise).
_FEDERAL_PLACE_COUNTY = {
    "camp pendleton": "San Diego", "marine corps base camp pendleton": "San Diego",
    "miramar": "San Diego", "mcas miramar": "San Diego", "point loma": "San Diego",
    "naval base san diego": "San Diego", "north island": "San Diego",
    "point mugu": "Ventura", "naval base ventura county": "Ventura",
    "fort irwin": "San Bernardino", "march air reserve base": "Riverside",
    "march arb": "Riverside", "los angeles air force base": "Los Angeles",
    "west los angeles": "Los Angeles",
}


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

    # 0b. K-12 district named in the agency -> its county, in scope or not
    county = school_district_county(agency_l)
    if county:
        return _in_or_out(county)

    # 0c. In-scope college / university campus named in the agency
    county = _institution_county(agency_l)
    if county:
        return {"county": county, "geo_status": "in"}

    # 1. Explicit county phrase anywhere
    for phrase, county in _COUNTY_PHRASE_TO_COUNTY.items():
        if phrase in blob:
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
        # extracted a real place that isn't in our in-scope counties
        if place in _OUT_OF_SCOPE_MARKERS:
            return {"county": None, "geo_status": "out"}

    # 4. In-scope city name appearing in the agency string
    for city, county in _CITY_TO_COUNTY.items():
        if city in _AMBIGUOUS_CITIES:
            continue
        if re.search(rf"\b{re.escape(city)}\b", agency_l):
            return {"county": county, "geo_status": "in"}

    # 4a. In-scope neighborhood / unincorporated community in the agency string
    county = _place_county(agency_l)
    if county:
        return {"county": county, "geo_status": "in"}

    # 4b. In-area federal installation named in the agency / place string
    for place_name, county in _FEDERAL_PLACE_COUNTY.items():
        if re.search(rf"\b{re.escape(place_name)}\b", agency_l):
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

    # 7. Same lookups against the title — BidNet rows carry no agency at all
    county = school_district_county(title_l)
    if county:
        return _in_or_out(county)
    county = _institution_county(title_l) or _place_county(title_l)
    if county:
        return {"county": county, "geo_status": "in"}

    return {"county": None, "geo_status": "unknown"}


def _in_or_out(county: str) -> dict:
    if county in FOUR_COUNTIES:
        return {"county": county, "geo_status": "in"}
    return {"county": None, "geo_status": "out"}


def _institution_county(text_l: str) -> str | None:
    for pat, county in _INSTITUTION_RE:
        if pat.search(text_l):
            return county
    return None


def _place_county(text_l: str) -> str | None:
    for place, county in _PLACE_COUNTY.items():
        if re.search(rf"\b{re.escape(place)}\b", text_l):
            return county
    return None


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
    "county of riverside": "Riverside",
    "county of san bernardino": "San Bernardino",
    "county of san diego": "San Diego",
    "county of kern": "Kern",
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
    bid["region"] = region_for(bid.get("county")) if bid.get("geo_status") == "in" else None
    return bid
