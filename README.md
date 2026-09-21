# Supreme Search API 1.1

Backend FastAPI preparado para Render.

## Correções desta versão

- conflito `beautifulsoup4` / `thepiratebay-api` resolvido;
- `/` passa a mostrar estado e endpoints em vez de `Not Found`;
- `/health` inclui versão e fontes;
- `/sources` lista as fontes disponíveis;
- pesquisa normaliza a query e valida fontes;
- cache de pesquisas;
- deduplicação por infohash/magnet;
- resultados ordenados por seeders;
- pesquisa 1337x mais leve no Chromium (bloqueia imagens/media/fontes);
- limite por fonte para evitar timeouts no Render Free;
- fallback de mirror para o wrapper PirateBay quando possível;
- Docker instala apenas Chromium, não todos os browsers do Playwright.

## Render

Se este diretório for a raiz do repositório no GitHub, usa `render.yaml` ou cria um Web Service com runtime Docker.

Depois do deploy:

- raiz: `https://TEU-SERVICO.onrender.com/`
- health: `https://TEU-SERVICO.onrender.com/health`
- documentação: `https://TEU-SERVICO.onrender.com/docs`
- teste: `https://TEU-SERVICO.onrender.com/search?q=ubuntu&sources=1337x,piratebay&limit=5`

A aplicação Android TV desta suite já vem configurada para:

`https://supreme-search-api.onrender.com`

Se mudares o nome do serviço Render, podes alterar a URL dentro da própria app.
