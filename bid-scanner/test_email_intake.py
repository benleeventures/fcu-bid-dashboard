"""Offline tests for email_intake.py — no Gmail, Claude or Airtable calls."""

import os
from pathlib import Path

import email_intake as ei

FIX = Path(__file__).parent / "data" / "email_fixtures"
os.environ["AIRTABLE_OWNER_NORTH_EMAIL"] = "north@example.com"
os.environ["AIRTABLE_OWNER_SOUTH_EMAIL"] = "south@example.com"


def _msg(name):
    return ei.parse_mime((FIX / name).read_bytes(), f"file-{name}")


def test_parse_html_invite_keeps_links_and_names_attachment_only():
    m = _msg("01_gc_invite.eml")
    assert m["from_addr"] == "druiz@pinnerconstruction.example"
    assert "Arroyo High School" in m["text"]
    assert any("buildingconnected" in l for l in m["links"])
    assert m["attachments"] == ["ITB_Arroyo.pdf"]
    assert "JVBER" not in m["text"]          # attachment bytes never read into text


def test_plain_text_links_extracted():
    m = _msg("04_ucla_suite.eml")
    assert m["links"] == ["https://mzn.sharefile.example/d-s8f7a6"]


def test_blocklist_catches_ben_phishing_and_own_mail():
    bl = ei.load_blocklist()
    assert ei.blocked_reason(_msg("03_eft_phish.eml"), bl)
    for subject in ("Lynda Pomo pay application", "Stacy Hoss updated COI",
                    "Mail Account Security Update"):
        assert ei.blocked_reason({"from_addr": "x@y.com", "from_name": "", "subject": subject}, bl)
    assert ei.blocked_reason({"from_addr": "bids@floorcoveringunlimited.com",
                              "from_name": "FCU Bid Agent", "subject": "Daily bids"}, bl)
    # A real invitation must pass, and so must a colleague forwarding one.
    assert ei.blocked_reason(_msg("01_gc_invite.eml"), bl) is None
    assert ei.blocked_reason({"from_addr": "joanne@floorcoveringunlimited.com",
                              "from_name": "Joanne Lee", "subject": "FW: ITB Duarte"}, bl) is None


def _extraction(**kw):
    x = {k: None for k in ei._SCHEMA["required"]}
    x.update(kind="bid_invitation", flooring_scope="yes")
    x.update(kw)
    return x


def test_build_record_region_owner_and_fields():
    m = _msg("01_gc_invite.eml")
    f = ei.build_record(m, _extraction(
        sender_company="Pinner Construction", project_name="Arroyo HS Building C Modernization",
        agency_or_owner="El Monte Union High School District", general_contractor="Pinner Construction",
        due_date="2026-10-23", job_walk_date="2026-10-16", job_walk_mandatory=True,
        plans_url="https://pinner.buildingconnected.example/projects/arroyo-hs",
        city="El Monte", county="Los Angeles"))
    assert f["Bid ID"] == "EMAIL-file-01_gc_invite.eml"
    assert f["Region"] == "North" and f["Owner"] == {"email": "north@example.com"}
    assert f["Bid Due Date"] == "2026-10-23" and f["Job Walk Date"] == "2026-10-16"
    assert f["Job Walk Mandatory"] is True
    assert f["Source Platform"] == "Email" and f["Sender Company"] == "Pinner Construction"
    assert "ITB_Arroyo.pdf" in f["Notes"] and "NOT opened" in f["Notes"]
    assert "Email Link" not in f                 # .eml fixtures have no Gmail id


def test_build_record_south_by_city_and_blank_when_unknown():
    m = _msg("05_shared_plans_unknown.eml")
    f = ei.build_record(m, _extraction(city="Anaheim", due_date="next friday"))
    assert f["Region"] == "South" and f["Owner"] == {"email": "south@example.com"}
    assert "Bid Due Date" not in f               # unparseable date left blank, not guessed
    g = ei.build_record(m, _extraction(flooring_scope="unclear"))
    assert "Region" not in g and "Owner" not in g
    assert "Needs region" in g["Notes"] and "Flooring scope: unclear" in g["Notes"]
    assert g["Project Name"] == "Bid request - tenant improvement"   # subject fallback


def test_out_of_area_noted():
    f = ei.build_record(_msg("05_shared_plans_unknown.eml"), _extraction(county="Sacramento"))
    assert "Region" not in f and f["_out_of_area"] is True


def test_duplicate_by_url_name_and_id():
    index = ({"EMAIL-1"}, {"https://a.example/plans"},
             {ei._norm_name("Arroyo High School Modernization")})
    base = {"Bid ID": "EMAIL-2", "Project Name": "Something else entirely"}
    assert not ei.is_duplicate(base, index)
    assert ei.is_duplicate({**base, "Bid ID": "EMAIL-1"}, index)
    assert ei.is_duplicate({**base, "Listing URL": "https://A.example/plans/"}, index)
    assert ei.is_duplicate({**base, "Project Name": "The Arroyo High School Modernization Project"}, index)
    assert not ei.is_duplicate({**base, "Project Name": "Bid"}, ({""}, set(), {ei._norm_name("Bid")}))
    ucla = ({""}, set(), {ei._norm_name("UCLA Wilshire Center Suite 650 Renovation")})
    assert ei.is_duplicate({**base, "Project Name": "UCLA Wilshire Center Suite 650"}, ucla)
    assert not ei.is_duplicate({**base, "Project Name": "UCLA Wilshire Center Suite 410"}, ucla)


def test_blocklist_october_noise():
    bl = ei.load_blocklist()
    for addr, subj in [("bids@send.recenterlife.com", "[FCU Bid Agent] 3 new relevant bids found"),
                       ("bids@vendorline.com", "VendorLine Today Oct 1"),
                       ("noreply@bidnet.com", "Statewide Bid Opportunities - 10/09/2026"),
                       ("noreply@laschools.org", "Your one-time sign-in code"),
                       ("quickbooks_payroll_service@intuit.com", "Accepted Tax Payment")]:
        assert ei.blocked_reason({"from_addr": addr, "from_name": "", "subject": subj}, bl), subj
    for addr, subj in [("team@buildingconnected.com", "Bid Invite: 1527 Lincoln Project"),
                       ("customercare@planetbids.com", "Opportunity Alert: BERNIECE BENNETT PARK"),
                       ("noreply@bidnet.com", "Award(s) Published for 27-013")]:
        assert ei.blocked_reason({"from_addr": addr, "from_name": "", "subject": subj}, bl) is None, subj


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("✓ email intake tests pass")
