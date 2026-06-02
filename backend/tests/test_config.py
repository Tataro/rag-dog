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


def test_s3_settings_have_expected_fields():
    s = Settings(
        s3_endpoint_url="http://localhost:9000",
        s3_bucket="docs",
        s3_access_key="k",
        s3_secret_key="v",
    )
    assert s.s3_endpoint_url == "http://localhost:9000"
    assert s.s3_bucket == "docs"
    assert s.s3_region == "us-east-1"  # default
