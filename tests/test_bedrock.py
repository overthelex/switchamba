"""Tests for the Bedrock client — correct_text method."""

import asyncio
import io
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from switchamba.bedrock.client import BedrockDisambiguator, CORRECTION_PROMPT


@dataclass
class FakeBedrockConfig:
    aws_access_key_id: str = "fake-key"
    aws_secret_access_key: str = "fake-secret"
    aws_region: str = "eu-central-1"
    model_quick: str = "anthropic.claude-3-haiku-20240307-v1:0"
    model_standard: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    model_deep: str = ""
    timeout_ms: int = 2000
    cache_size: int = 256


def _make_bedrock_response(text: str) -> dict:
    """Create a mock Bedrock API response."""
    body_bytes = json.dumps({
        "content": [{"type": "text", "text": text}],
    }).encode()
    return {"body": io.BytesIO(body_bytes)}


class TestCorrectText:
    def setup_method(self):
        with patch("boto3.client"):
            self.config = FakeBedrockConfig()
            self.client = BedrockDisambiguator(self.config)

    @pytest.mark.asyncio
    async def test_correct_text_returns_corrected(self):
        """Should return corrected text from Bedrock Sonnet."""
        self.client._client.invoke_model = MagicMock(
            return_value=_make_bedrock_response("привет мир")
        )
        result = await self.client.correct_text("привет мпр")
        assert result == "привет мир"

    @pytest.mark.asyncio
    async def test_correct_text_uses_model_standard(self):
        """Should use model_standard, not model_quick."""
        self.client._client.invoke_model = MagicMock(
            return_value=_make_bedrock_response("hello")
        )
        await self.client.correct_text("helo")
        call_args = self.client._client.invoke_model.call_args
        assert call_args.kwargs["modelId"] == self.config.model_standard

    @pytest.mark.asyncio
    async def test_correct_text_empty_input(self):
        """Empty or whitespace-only text should return None."""
        result = await self.client.correct_text("")
        assert result is None
        result = await self.client.correct_text("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_text_no_model_standard(self):
        """Should return None if model_standard not configured."""
        self.config.model_standard = ""
        result = await self.client.correct_text("hello world")
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_text_api_error(self):
        """Should return None on API error."""
        self.client._client.invoke_model = MagicMock(
            side_effect=Exception("API error")
        )
        result = await self.client.correct_text("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_text_timeout(self):
        """Should return None on timeout."""
        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(100)

        # Make invoke_model block forever; wait_for should timeout
        self.client._client.invoke_model = MagicMock(
            side_effect=lambda **kw: (_ for _ in ()).throw(TimeoutError("timeout"))
        )
        result = await self.client.correct_text("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_text_prompt_format(self):
        """Should format the correction prompt correctly."""
        self.client._client.invoke_model = MagicMock(
            return_value=_make_bedrock_response("fixed text")
        )
        await self.client.correct_text("broken text")
        call_args = self.client._client.invoke_model.call_args
        body = json.loads(call_args.kwargs["body"])
        prompt_text = body["messages"][0]["content"]
        assert "broken text" in prompt_text
        assert body["temperature"] == 0

    @pytest.mark.asyncio
    async def test_correct_text_max_tokens_scales(self):
        """max_tokens should scale with input length, minimum 200."""
        self.client._client.invoke_model = MagicMock(
            return_value=_make_bedrock_response("ok")
        )
        # Short text — should use 200 minimum
        await self.client.correct_text("hi")
        body = json.loads(self.client._client.invoke_model.call_args.kwargs["body"])
        assert body["max_tokens"] == 200

        # Long text — should scale
        long_text = "a" * 300
        await self.client.correct_text(long_text)
        body = json.loads(self.client._client.invoke_model.call_args.kwargs["body"])
        assert body["max_tokens"] == 600

    @pytest.mark.asyncio
    async def test_correct_text_strips_response(self):
        """Should strip whitespace from Bedrock response."""
        self.client._client.invoke_model = MagicMock(
            return_value=_make_bedrock_response("  corrected  \n")
        )
        result = await self.client.correct_text("input")
        assert result == "corrected"
