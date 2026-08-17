from fastapi.testclient import TestClient

from app.main import create_application
from app.infrastructure.models import ClassificationSuggestionModel
from tests.conftest import FakeEmailProvider, FakeLanguageModel, make_email


def account_payload():
    return {
        "name": "主邮箱",
        "email_address": "user@example.com",
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "username": "user@example.com",
        "password_env_name": "TEST_EMAIL_PASSWORD",
        "folder": "INBOX",
        "scan_window_days": 7,
    }


def test_account_scan_report_and_mail_endpoints(settings, password_env):
    app = create_application(
        settings,
        FakeEmailProvider({1: [make_email()]}),
        FakeLanguageModel(),
    )
    with TestClient(app) as client:
        create = client.post("/api/accounts", json=account_payload())
        account_id = create.json()["id"]
        accounts = client.get("/api/accounts")
        update = client.patch(
            f"/api/accounts/{account_id}",
            json={"scan_window_days": 14, "is_active": True},
        )
        scan = client.post("/api/scans", json={"window_days": 7})
        report = client.get(f"/api/reports/{scan.json()['report_id']}")
        reports = client.get("/api/reports")
        latest_report = client.get("/api/reports/latest")
        mail_id = next(
            item["email_id"]
            for categories in report.json()["tree"].values()
            for items in categories.values()
            for item in items
        )
        mail = client.get(f"/api/mails/{mail_id}")
        categories = client.get("/api/categories")
        suggestions = client.get("/api/suggestions")
        home = client.get("/")
        report_page = client.get(f"/reports/{scan.json()['report_id']}")
        static_css = client.get("/static/app.css")
        static_js = client.get("/static/app.js")
        page = client.get(f"/mail/{mail_id}")
        mark_read = client.post(f"/api/read-mails/{mail_id}")
        read_list = client.get("/api/read-mails")
        read_page = client.get("/read-mails")
        reports_page = client.get("/reports")
        remove_read = client.delete(f"/api/read-mails/{mail_id}")

    assert create.status_code == 201
    assert accounts.status_code == 200
    assert len(accounts.json()) == 1
    assert update.status_code == 200
    assert update.json()["scan_window_days"] == 14
    assert scan.status_code == 200
    assert report.status_code == 200
    assert reports.status_code == 200
    assert reports.json()[0]["id"] == scan.json()["report_id"]
    assert latest_report.status_code == 200
    assert latest_report.json()["id"] == scan.json()["report_id"]
    assert mail.json()["analysis"]["summary"]
    assert mail.json()["analysis"]["source_name"] == "example.com"
    assert len(categories.json()) == 8
    assert suggestions.status_code == 200
    assert home.status_code == 200
    assert report_page.status_code == 200
    assert static_css.status_code == 200
    assert static_js.status_code == 200
    assert static_js.headers["content-type"].startswith("text/javascript")
    assert page.status_code == 200
    assert "example.com / 通知" in page.text
    assert mark_read.status_code == 201
    assert read_list.status_code == 200
    assert read_list.json()["pagination"]["total_items"] == 1
    assert read_page.status_code == 200
    assert reports_page.status_code == 200
    assert remove_read.status_code == 204


def test_scan_api_exposes_no_progress_polling_route(settings, password_env):
    app = create_application(settings, FakeEmailProvider(), FakeLanguageModel())
    with TestClient(app) as client:
        response = client.get("/api/scans/1")

    assert response.status_code == 404


def test_suggestions_api_only_returns_pending_items(settings, password_env):
    app = create_application(settings, FakeEmailProvider(), FakeLanguageModel())
    with TestClient(app) as client:
        with app.state.database.session_factory() as session:
            session.add_all(
                [
                    ClassificationSuggestionModel(
                        suggestion_type="category",
                        proposed_name="待确认类别",
                        reason="测试",
                        status="pending",
                    ),
                    ClassificationSuggestionModel(
                        suggestion_type="category",
                        proposed_name="已处理类别",
                        reason="测试",
                        status="approved",
                    ),
                ]
            )
            session.commit()

        response = client.get("/api/suggestions")

    assert response.status_code == 200
    assert [item["proposed_name"] for item in response.json()] == ["待确认类别"]

def test_bulk_read_and_clear_endpoints(settings, password_env):
    app = create_application(
        settings,
        FakeEmailProvider(
            {
                1: [
                    make_email(
                        uid="1",
                        subject="Important notice",
                        sender="mentor@trusted.example.com",
                        body="Please submit before Friday.",
                    ),
                    make_email(uid="2", subject="General info", body="Please confirm the schedule."),
                    make_email(
                        uid="3",
                        subject="Promo email",
                        body="This is a promotional newsletter, please unsubscribe.",
                    ),
                ]
            }
        ),
        FakeLanguageModel(),
    )
    with TestClient(app) as client:
        create = client.post("/api/accounts", json=account_payload())
        assert create.status_code == 201
        scan = client.post("/api/scans", json={"window_days": 7})
        report = client.get(f"/api/reports/{scan.json()['report_id']}")
        payload = report.json()
        tree = payload["tree"]
        filtered_ids = [
            item["email_id"]
            for categories in tree.values()
            for items in categories.values()
            for item in items
        ]
        discardable_ids = [item["email_id"] for item in payload["discardable"]]
        all_ids = filtered_ids + discardable_ids
        assert len(filtered_ids) == 2
        assert len(discardable_ids) == 1

        bulk = client.post("/api/read-mails/bulk", json={"email_ids": all_ids})
        assert bulk.status_code == 201
        assert bulk.json()["marked"] == len(all_ids)

        bulk_again = client.post("/api/read-mails/bulk", json={"email_ids": all_ids})
        assert bulk_again.status_code == 201
        assert bulk_again.json()["marked"] == 0

        missing = client.post("/api/read-mails/bulk", json={"email_ids": [999999]})
        assert missing.status_code == 404

        read_list = client.get("/api/read-mails")
        assert read_list.status_code == 200
        assert read_list.json()["pagination"]["total_items"] == len(all_ids)

        report_page = client.get(f"/reports/{scan.json()['report_id']}")
        assert report_page.status_code == 200
        assert "一键已读" in report_page.text
        assert report_page.text.count("data-mark-read-section") == 2
        assert report_page.text.count("已加入本地已读") == len(all_ids)

        read_page = client.get("/read-mails")
        assert read_page.status_code == 200
        assert "一键移出" in read_page.text

        clear = client.delete("/api/read-mails")
        assert clear.status_code == 204
        read_list_after = client.get("/api/read-mails")
        assert read_list_after.json()["pagination"]["total_items"] == 0
def test_duplicate_account_returns_conflict(settings, password_env):
    app = create_application(settings, FakeEmailProvider(), FakeLanguageModel())
    with TestClient(app) as client:
        first = client.post("/api/accounts", json=account_payload())
        duplicate = client.post("/api/accounts", json=account_payload())

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "已经存在" in duplicate.json()["detail"]

def test_important_mail_endpoints(settings, password_env):
    app = create_application(
        settings,
        FakeEmailProvider(
            {
                1: [
                    make_email(
                        uid="1",
                        subject="Important notice",
                        sender="mentor@trusted.example.com",
                        body="Please submit before Friday.",
                    ),
                    make_email(
                        uid="2",
                        subject="General info",
                        body="Please confirm the schedule.",
                    ),
                ]
            }
        ),
        FakeLanguageModel(),
    )
    with TestClient(app) as client:
        create = client.post("/api/accounts", json=account_payload())
        assert create.status_code == 201
        scan = client.post("/api/scans", json={"window_days": 7})
        report = client.get(f"/api/reports/{scan.json()['report_id']}")
        tree = report.json()["tree"]
        filtered_ids = [
            item["email_id"]
            for categories in tree.values()
            for items in categories.values()
            for item in items
        ]
        assert len(filtered_ids) == 2
        first_id = filtered_ids[0]

        mark = client.post(f"/api/important-mails/{first_id}")
        assert mark.status_code == 201
        assert mark.json()["email_id"] == first_id

        mark_again = client.post(f"/api/important-mails/{first_id}")
        assert mark_again.status_code == 201

        missing = client.post("/api/important-mails/999999")
        assert missing.status_code == 404

        listing = client.get("/api/important-mails")
        assert listing.status_code == 200
        assert listing.json()["pagination"]["total_items"] == 1
        assert listing.json()["data"][0]["email_id"] == first_id

        report_page = client.get(f"/reports/{scan.json()['report_id']}")
        assert report_page.status_code == 200
        assert report_page.text.count("data-mark-important") == 1
        assert report_page.text.count("important-badge") == 1

        important_page = client.get("/important-mails")
        assert important_page.status_code == 200
        assert "重要邮件" in important_page.text
        assert "data-remove-important" in important_page.text

        remove = client.delete(f"/api/important-mails/{first_id}")
        assert remove.status_code == 204

        remove_again = client.delete(f"/api/important-mails/{first_id}")
        assert remove_again.status_code == 404

        listing_after = client.get("/api/important-mails")
        assert listing_after.json()["pagination"]["total_items"] == 0
