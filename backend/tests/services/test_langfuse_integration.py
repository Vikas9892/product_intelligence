"""Unit and integration tests for Langfuse observability integration."""

from unittest.mock import MagicMock, patch

from app.core.langfuse import (
    flush_langfuse,
    get_langfuse_client,
    observe,
    record_trace_score,
    update_active_span,
    update_trace_attributes,
)
from app.core.settings import LangfuseSettings, Settings


class TestLangfuseSettings:
    """Test LangfuseSettings configuration schema and defaults."""

    def test_default_settings(self) -> None:
        settings = LangfuseSettings()
        assert settings.enabled is False
        assert settings.public_key is None
        assert settings.secret_key is None
        assert settings.host == "https://cloud.langfuse.com"
        assert settings.sample_rate == 1.0
        assert settings.debug is False

    def test_settings_mounted_on_root_settings(self) -> None:
        root = Settings()
        assert hasattr(root, "langfuse")
        assert isinstance(root.langfuse, LangfuseSettings)
        assert root.langfuse.enabled is False

    def test_custom_settings(self) -> None:
        settings = LangfuseSettings(
            enabled=True,
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            host="http://localhost:3000",
            sample_rate=0.5,
            debug=True,
        )
        assert settings.enabled is True
        assert settings.public_key is not None
        assert settings.secret_key is not None
        assert settings.public_key.get_secret_value() == "pk-lf-test"
        assert settings.secret_key.get_secret_value() == "sk-lf-test"
        assert settings.host == "http://localhost:3000"
        assert settings.sample_rate == 0.5
        assert settings.debug is True


class TestLangfuseDisabledBehavior:
    """Verify that when Langfuse is disabled, all helpers are complete no-ops."""

    def test_client_is_none_when_disabled(self) -> None:
        with patch("app.core.langfuse.settings.langfuse.enabled", False):
            client = get_langfuse_client()
            assert client is None

    def test_observe_decorator_is_identity_when_disabled(self) -> None:
        with patch("app.core.langfuse.settings.langfuse.enabled", False):

            @observe(name="test_function")
            def sample_add(a: int, b: int) -> int:
                return a + b

            assert sample_add(3, 4) == 7

    def test_async_observe_decorator_when_disabled(self) -> None:
        import asyncio

        with patch("app.core.langfuse.settings.langfuse.enabled", False):

            @observe(name="async_test")
            async def sample_async_func(value: str) -> str:
                return f"processed:{value}"

            result = asyncio.run(sample_async_func("hello"))
            assert result == "processed:hello"

    def test_helpers_no_op_when_disabled(self) -> None:
        with patch("app.core.langfuse.settings.langfuse.enabled", False):
            # None of these should raise or throw exceptions
            with update_trace_attributes(session_id="tenant-1", tags=["test"]):
                pass
            update_active_span(metadata={"test": "val"})
            record_trace_score(name="eval_score", value=0.95)
            flush_langfuse()


class TestLangfuseEnabledBehavior:
    """Verify that when Langfuse is enabled, calls interact with the Langfuse client."""

    def test_record_trace_score_calls_client(self) -> None:
        mock_client = MagicMock()
        with (
            patch("app.core.langfuse.settings.langfuse.enabled", True),
            patch("langfuse.get_client", return_value=mock_client),
        ):
            record_trace_score(name="ndcg@10", value=0.88, comment="high relevance")
            mock_client.score_current_trace.assert_called_once_with(
                name="ndcg@10",
                value=0.88,
                comment="high relevance",
                metadata=None,
            )

    def test_update_active_span_calls_client(self) -> None:
        mock_client = MagicMock()
        with (
            patch("app.core.langfuse.settings.langfuse.enabled", True),
            patch("langfuse.get_client", return_value=mock_client),
        ):
            update_active_span(metadata={"key": "val"}, status_message="OK")
            mock_client.update_current_span.assert_called_once_with(
                name=None,
                input=None,
                output=None,
                metadata={"key": "val"},
                status_message="OK",
            )
