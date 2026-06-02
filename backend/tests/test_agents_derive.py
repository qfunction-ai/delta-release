"""Tests for agents route helpers — provider type derivation."""

from app.agents.routes import _derive_provider_type


class TestDeriveProviderType:
    """Tests for _derive_provider_type."""

    def test_anthropic(self):
        assert _derive_provider_type("anthropic/claude-3") == "anthropic"

    def test_google_ai(self):
        assert _derive_provider_type("google_ai/gemini-pro") == "google_ai"

    def test_google_vertex(self):
        assert _derive_provider_type("google_vertex/gemini-pro") == "google_vertex"

    def test_azure(self):
        assert _derive_provider_type("azure/gpt-4") == "azure"

    def test_groq(self):
        assert _derive_provider_type("groq/llama3") == "groq"

    def test_xai(self):
        assert _derive_provider_type("xai/grok") == "xai"

    def test_ollama_maps_to_ollama(self):
        """Ollama returns its own provider type (needed for OllamaModelSettings with strict=false)."""
        assert _derive_provider_type("ollama/gemma4:latest") == "ollama"

    def test_letta_maps_to_openai(self):
        assert _derive_provider_type("letta/letta-free") == "openai"

    def test_openai_maps_to_openai(self):
        assert _derive_provider_type("openai/gpt-4") == "openai"

    def test_unknown_maps_to_openai(self):
        assert _derive_provider_type("unknown/model") == "openai"

    def test_case_insensitive(self):
        assert _derive_provider_type("Anthropic/Claude-3") == "anthropic"
