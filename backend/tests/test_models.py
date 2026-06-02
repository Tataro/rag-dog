import pytest

from app.models import AllowedEmail, Chunk, Conversation, Document, Message, User


# Override the autouse DB-cleaning fixture so these pure-metadata tests
# don't need a live Postgres connection.
@pytest.fixture(autouse=True)
def _clean_tables():
    yield


def test_user_model_columns():
    cols = set(User.__table__.columns.keys())
    assert {"id", "email", "name", "picture", "is_admin", "created_at"} <= cols


def test_ownership_columns_present():
    for model in (Document, Chunk, Conversation, Message):
        assert "user_id" in model.__table__.columns, f"{model.__name__} missing user_id"


def test_allowed_email_pk_is_email():
    assert list(AllowedEmail.__table__.primary_key.columns.keys()) == ["email"]
