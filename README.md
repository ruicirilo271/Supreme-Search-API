# Supreme Search API

API de pesquisa normalizada para a app Android TV. Expõe:

- `GET /health`
- `GET /search?q=ubuntu&sources=1337x,piratebay&limit=12`

Resposta:

```json
[
  {
    "title": "...",
    "source": "1337x",
    "size": "1.4 GB",
    "seeders": 120,
    "leechers": 8,
    "magnet": "magnet:?xt=urn:btih:...",
    "date": "...",
    "category": "..."
  }
]
```

## Render

1. Cria um repositório GitHub só com o conteúdo desta pasta `backend`.
2. No Render, cria um **Web Service** a partir desse repositório.
3. Escolhe **Docker**. O `Dockerfile` já instala Chromium/Playwright.
4. Depois do deploy, testa `https://TEU-SERVICO.onrender.com/health`.
5. Guarda a URL base na app Android TV, sem `/search` no fim.

### Variáveis opcionais

- `X1337_BASE_URL` — mirror usado pelo provider 1337x.
- `TPB_BASE_URL` — mirror/base URL alternativo para o wrapper Pirate Bay.
- `CACHE_TTL_SECONDS` — cache em segundos (default 300).

> Usa apenas fontes e torrents que tenhas autorização para consultar e descarregar. Os sites e wrappers de terceiros podem mudar ou deixar de funcionar; a app foi feita para falhar de forma segura quando um provider está indisponível.
