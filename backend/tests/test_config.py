from app.config import Settings


def test_google_client_ids_parsed_as_list():
    s = Settings(google_client_ids="web.apps.googleusercontent.com, mobile.apps.googleusercontent.com")
    assert s.google_client_id_list == [
        "web.apps.googleusercontent.com",
        "mobile.apps.googleusercontent.com",
    ]


def test_bootstrap_admins_lowercased_set():
    s = Settings(bootstrap_admin_emails="Boss@Example.com")
    assert s.bootstrap_admin_set == {"boss@example.com"}
