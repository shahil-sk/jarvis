# LLM Plugin

Fallback brain. Catches any input no other plugin handles.
Uses `stdlib urllib` only — zero extra dependencies.

## Switch Backend

Edit `config.yaml`:
```yaml
jarvis:
  llm_mode: lmstudio   # openai | groq | lmstudio | ollama | openrouter
```

Or use an env var (overrides config):
```bash
export JARVIS_LLM_MODE=ollama
```

## Backend Quick-Start

### LM Studio (local)
1. Download [LM Studio](https://lmstudio.ai)
2. Load any GGUF model
3. Start the local server (default port 1234)
4. Set `llm_mode: lmstudio` in config.yaml
5. Set `model:` to whatever name LM Studio shows

### Ollama (local)
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
# set llm_mode: ollama, model: mistral
```

### Groq (cloud, fast free tier)
```bash
export JARVIS_LLM_API_KEY=your_groq_key
# set llm_mode: groq in config.yaml
```

## Backend Comparison

| Backend | Local | Free | Speed | Privacy |
|---|---|---|---|---|
| LM Studio | ✅ | ✅ | medium | full |
| Ollama | ✅ | ✅ | medium | full |
| Groq | ❌ | free tier | ⚡ fast | cloud |
| OpenAI | ❌ | paid | fast | cloud |
| OpenRouter | ❌ | some free | varies | cloud |
