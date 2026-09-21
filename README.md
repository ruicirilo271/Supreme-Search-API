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


## Fix 2.1 — 1337x

A pesquisa 1337x deixou de depender do Playwright. Usa agora `1337x==2.1.1`/`py1337x`, pesquisa por categorias (TV, Movies, Anime, etc.) e tenta vários domínios. O próprio projeto py1337x documenta que a pesquisa genérica sem categoria pode devolver resultados vazios após uma alteração recente no 1337x.

Teste depois do deploy: `/diagnostics/1337x?q=ubuntu`.

## Correções 2.3.0

- corrige o bug visual em que **Nenhum resultado encontrado** e **Não foi possível concluir a pesquisa** apareciam mesmo quando já existiam resultados;
- adiciona uma regra global para respeitar corretamente o atributo HTML `hidden`;
- os cartões de carregamento deixam de parecer espaços vazios e passam a explicar o que está a acontecer;
- o resumo da pesquisa mostra quantos resultados vieram de cada fonte;
- estados de carregamento, vazio e erro passam a ser mutuamente exclusivos;
- mantém a correção 1337x com pesquisa por categorias e fallback de domínios.


## Versão 2.3.0 — até 50 resultados

- limite máximo do backend aumentado de 20 para 50;
- seletor da página agora oferece 8, 12, 20, 30, 40 e 50 resultados;
- 50 resultados ficam selecionados por defeito;
- limite por fonte aumentado para 50;
- timeout da interface aumentado automaticamente para pesquisas grandes no Render;
- concorrência do 1337x ajustada para acelerar a resolução dos magnet links.
