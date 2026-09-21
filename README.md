# Supreme Search WEB 4K — Render

Versão 2.0 do **Supreme Search API**, agora com uma interface web completa feita para abrir diretamente numa Android TV/Google TV ou computador.

## O que muda

- `/` deixa de mostrar JSON e passa a abrir a interface **Supreme Search 4K**;
- design cinematográfico responsivo para 1080p/4K;
- navegação por comando/teclado com setas e tecla OK/Enter;
- pesquisa nas fontes configuradas no backend;
- filtros de fontes e quantidade de resultados;
- ordenação pelo backend por seeders;
- nome, fonte, seeders, leechers, tamanho, categoria e data;
- botão **ABRIR MAGNET** para entregar o link à aplicação de downloads instalada na TV;
- botão **COPIAR** como alternativa;
- histórico de pesquisas guardado apenas no navegador da TV;
- botão de ecrã inteiro;
- estado da API em tempo real;
- skeleton/loading e mensagens de erro pensadas para o plano gratuito do Render;
- `/api`, `/health`, `/sources`, `/search` e `/docs` continuam disponíveis.

## Publicar no Render

Este ZIP pode substituir o conteúdo do repositório atual do backend.

Se o Render está ligado ao GitHub e `Auto Deploy` está ativo, basta fazer commit/push destas alterações. Como o projeto usa Docker, mantém:

- Runtime: Docker
- Health Check Path: `/health`

O `render.yaml` já está incluído.

Depois do deploy, abre simplesmente:

`https://supreme-search-api.onrender.com`

Na TV, guarda essa página nos favoritos. Não é necessário instalar a antiga app Android de pesquisa.

## Endpoints

- Interface TV: `/`
- Informação da API: `/api`
- Estado: `/health`
- Fontes: `/sources`
- Pesquisa JSON: `/search?q=ubuntu&sources=1337x,piratebay&limit=12`
- Swagger: `/docs`

## Nota

Usa apenas torrents e conteúdos que tenhas autorização para obter.
