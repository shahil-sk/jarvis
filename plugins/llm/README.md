# LLM Plugin

Fallback plugin — if no other plugin matches, this sends the conversation to an LLM.

## Supported Backends

| Backend | base_url |
|---|---|
| OpenAI | `https://api.openai.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |

## Config (config.yaml)

```yaml
jarvis:
  llm:
    base_url: https://api.groq.com/openai/v1
    api_key: your_key_here   # or set JARVIS_LLM_API_KEY env var
    model: llama-3.3-70b-versatile
    max_tokens: 512
    temperature: 0.7
    system_prompt: "You are Jarvis, a concise AI assistant."
```

## Env Vars (override config)
```bash
export JARVIS_LLM_URL=http://localhost:11434/v1
export JARVIS_LLM_API_KEY=ollama
export JARVIS_LLM_MODEL=mistral
```
