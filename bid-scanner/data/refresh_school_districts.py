"""
Refresh data/ca_school_districts.csv (K-12 district -> county, used by geo.py)
from the CDE "California School District Offices" layer on gis.data.ca.gov.
Run once a year when CDE publishes the new school year's layer; bump LAYER.

    python data/refresh_school_districts.py
"""

import csv
import json
import os
import urllib.request

LAYER = ("https://services3.arcgis.com/fdvHcZVgB2QSRNkL/arcgis/rest/services/"
         "DistrictSites2526/FeatureServer/0/query")
OUT = os.path.join(os.path.dirname(__file__), "ca_school_districts.csv")


def main() -> None:
    rows, offset = [], 0
    while True:
        url = (f"{LAYER}?where=1%3D1&outFields=DistrictName,DistrictType,CountyName,City"
               f"&returnGeometry=false&orderByFields=OBJECTID&resultOffset={offset}"
               f"&resultRecordCount=1000&f=json")
        page = json.load(urllib.request.urlopen(url, timeout=60))
        rows += [f["attributes"] for f in page["features"]]
        if not page.get("exceededTransferLimit"):
            break
        offset += 1000

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["district_name", "district_type", "county", "city"])
        for r in sorted(rows, key=lambda r: (r["CountyName"], r["DistrictName"])):
            w.writerow([r["DistrictName"].strip(), r["DistrictType"], r["CountyName"],
                        (r["City"] or "").strip()])
    print(f"✓ {len(rows)} districts -> {OUT}")


if __name__ == "__main__":
    main()
