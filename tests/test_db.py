"""Unit tests for the database layer (no network, no MySQL)."""
import json
import logging

import pymysql
import pytest
from db import Database, DatabaseUnavailable, SecretsManagerCredentials, Settings


class FakeSecrets:
    def __init__(self, password="pw-1"):
        self.password = password
        self.calls = 0

    def get_secret_value(self, SecretId):
        self.calls += 1
        return {"SecretString": json.dumps({"username": "appadmin", "password": self.password})}


def settings(**overrides):
    base = dict(host="db.example", name="appdb", secret_arn="arn:aws:secretsmanager:x:1:secret:s",
                ssl_disabled=True)
    base.update(overrides)
    return Settings(**base)


def test_settings_from_env_defaults_and_overrides():
    s = Settings.from_env({"DB_HOST": "h", "DB_NAME": "n", "DB_SECRET_ARN": "a", "DB_PORT": "3307",
                           "AWS_REGION": "eu-west-1"})
    assert (s.host, s.port, s.region, s.configured) == ("h", 3307, "eu-west-1", True)
    assert Settings.from_env({}).configured is False
    assert Settings.from_env({}).ssl_disabled is False  # TLS verification is the default


def test_credentials_are_cached_until_ttl_or_forced():
    now = [0.0]
    client = FakeSecrets()
    creds = SecretsManagerCredentials("arn", "us-east-1", ttl_seconds=100, client=client, clock=lambda: now[0])
    assert creds.get() == ("appadmin", "pw-1")
    creds.get()
    assert client.calls == 1
    now[0] = 101
    creds.get()
    assert client.calls == 2
    creds.get(force_refresh=True)
    assert client.calls == 3


def test_secret_failure_is_wrapped_and_does_not_leak(caplog):
    class Broken:
        def get_secret_value(self, SecretId):
            raise RuntimeError("AccessDenied for arn:aws:secretsmanager:...:SUPERSECRET")

    creds = SecretsManagerCredentials("arn", "us-east-1", client=Broken())
    with caplog.at_level(logging.ERROR), pytest.raises(DatabaseUnavailable) as info:
        creds.get()
    assert "SUPERSECRET" not in str(info.value) and "SUPERSECRET" not in caplog.text


def test_unconfigured_database_is_unavailable():
    with pytest.raises(DatabaseUnavailable):
        Database(Settings(), credentials=SecretsManagerCredentials("x", "r", client=FakeSecrets()))._open()


def test_tls_is_verified_by_default(tmp_path):
    bundle = tmp_path / "bundle.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    db = Database(settings(ssl_disabled=False, ssl_ca=str(bundle)), credentials=SecretsManagerCredentials(
        "x", "r", client=FakeSecrets()))
    kwargs = db._connect_kwargs("u", "p")
    assert kwargs["ssl_ca"] == str(bundle)
    assert kwargs["ssl_verify_cert"] is True and kwargs["ssl_verify_identity"] is True


def test_missing_ca_bundle_refuses_to_connect():
    db = Database(settings(ssl_disabled=False, ssl_ca="/nonexistent/bundle.pem"),
                  credentials=SecretsManagerCredentials("x", "r", client=FakeSecrets()))
    with pytest.raises(DatabaseUnavailable):
        db._connect_kwargs("u", "p")


def test_access_denied_triggers_one_secret_refresh_then_succeeds():
    secrets = FakeSecrets("old")
    attempts = []

    def connect(**kwargs):
        attempts.append(kwargs["password"])
        if kwargs["password"] == "old":
            raise pymysql.err.OperationalError(1045, "Access denied")
        return object()

    creds = SecretsManagerCredentials("x", "r", client=secrets)
    db = Database(settings(), credentials=creds, connect=connect)
    creds.get()  # cache the soon-to-be-rotated password
    secrets.password = "rotated"
    assert db._open() is not None
    assert attempts == ["old", "rotated"]


def test_persistent_access_denied_is_bounded_and_generic():
    calls = []

    def connect(**kwargs):
        calls.append(1)
        raise pymysql.err.OperationalError(1045, "Access denied for user 'appadmin'")

    db = Database(settings(), credentials=SecretsManagerCredentials("x", "r", client=FakeSecrets()), connect=connect)
    with pytest.raises(DatabaseUnavailable) as info:
        db._open()
    assert len(calls) == 2  # original attempt + exactly one retry
    assert "appadmin" not in str(info.value)


def test_connection_error_is_wrapped():
    def connect(**kwargs):
        raise pymysql.err.OperationalError(2003, "Can't connect")

    db = Database(settings(), credentials=SecretsManagerCredentials("x", "r", client=FakeSecrets()), connect=connect)
    with pytest.raises(DatabaseUnavailable):
        db._open()
