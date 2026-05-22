# VF-TeS (Títulos e Subtítulos)

Esta é uma ferramenta desenvolvida para validar a estrutura de cabeçalhos (H1, H2, H3, etc.) em páginas web.
[![](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)]() [![](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)]() [![](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)]() [![](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)]() [![](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)]() [![](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwindcss&logoColor=white)]() [![](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)]() [![](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)]()

## Funcionalidades Principais

- **Validação de Página Única**: Análise da estrutura de cabeçalhos de um URL específico.
- **Validação de Sitemap**: Extração e análise de múltiplas páginas a partir do URL de um sitemap.xml.
- **Validação via Crawler**: Exploração e verificação automática de um website.
- **Validação Multi-URL**: Análise de uma lista de URLs.
- **Validação Visual**: Interface que permite identificar a hierarquia dos cabeçalhos na página.

## Arquitetura do Projeto

A aplicação está dividida em dois componentes principais:

- **Frontend (/client)**: Next.js com Tailwind CSS.
- **Backend (/server)**: API desenvolvida em Python (FastAPI) e Playwright, responsável pela execução dos processos de extração (crawling) e análise assíncrona.

## Instruções de Utilização

### Pré-requisitos

- Docker.

### Iniciar a Aplicação

1. Execute o seguinte comando para iniciar os serviços:
   ```bash
   docker-compose up --build -d
   ```
2. Aguarde até ao arranque.
3. Abra e aceda à ferramenta através do endereço: **http://localhost:3002**
4. A API do backend ficará disponível em **http://localhost:3004**

## Como Utilizar a Interface

1. Selecione o método pretendido no menu (Página Única, Sitemap, Crawler ou Multi-URL).
2. Insira o URL alvo ou a lista de URLs no campo de texto indicado.
3. Clique no botão de submissão e aguarde pelos resultados.

Em caso de dúvidas na utilização da ferramenta ou para reportar anomalias, por favor contacte a equipa de desenvolvimento.
