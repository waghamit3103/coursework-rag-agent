import pytest

from app.agent.claude_client import build_default_client


class TestBuildDefaultClient:
    def test_raises_clear_error_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            build_default_client()

    def test_constructs_client_when_key_present(self, monkeypatch):
        # Constructing anthropic.Anthropic(api_key=...) is pure object
        # setup — no network call is made until a request method is
        # actually invoked — so this is safe to test with a fake key.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key-for-testing")

        client = build_default_client()

        assert client is not None
        assert hasattr(client, "messages")
