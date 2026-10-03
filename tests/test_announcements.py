from pathlib import Path

from cse_screening.downloaders.announcements import CSEDividendClient, dividend_type


def test_dividend_feed_filters_and_resolves_requested_company(tmp_path: Path, monkeypatch):
    client = CSEDividendClient(tmp_path)
    calls = []

    def fake_post(endpoint, data=None):
        calls.append((endpoint, data))
        if endpoint == "approvedAnnouncement":
            return {
                "approvedAnnouncements": [
                    {
                        "announcementCategory": "CASH DIVIDEND",
                        "company": "ACL CABLES PLC",
                        "announcementId": 10,
                        "id": 20,
                    },
                    {
                        "announcementCategory": "RESIGNATION OF DIRECTORS",
                        "company": "ACL CABLES PLC",
                        "announcementId": 11,
                    },
                ]
            }
        return {"reqBaseAnnouncement": {"id": 10}, "reqAnnouncementDocs": []}

    monkeypatch.setattr(client, "_post", fake_post)
    result = client.latest_for_companies([{"ticker": "ACL.N0000", "name": "ACL CABLES PLC"}])
    assert result["ACL.N0000"][0]["reqBaseAnnouncement"]["id"] == 10
    assert calls == [
        ("approvedAnnouncement", None),
        ("getAnnouncementById", {"announcementId": 10}),
    ]


def test_dividend_type_is_explicit():
    assert dividend_type({"typeSecondInt": True}) == "second interim"
