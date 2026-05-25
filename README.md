<div align="center">
   <h1>VTeS (Validador de Títulos e Subtítulos)</h1>
   <p>
   <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
   <img src="https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white" />

<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />

<img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" />
<img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" />
<img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwindcss&logoColor=white" />

<img src="https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" />

<img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" /> 
   </p>
</div>
Esta é uma ferramenta desenvolvida para validar a estrutura de cabeçalhos em páginas web.

---

### Iniciar a Aplicação

Execute o comando:

```bash
docker-compose up --build -d
```

Abra a ferramenta através do endereço: **http://localhost:3002**

---

## Utilização

A plataforma tem quatro modos. Abaixo, está como utilizar o modo de **Página Única**.

### Página Única

Este modo permite inserir um URL e retorna possíveis problemas com a hierarquia de títulos e subtítulos.

<div align="center">
  <img src="./docs/screenshots/pagina_unica.png" alt="Modo Página Única" style="max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0px 4px 15px rgba(0,0,0,0.1);" />
</div>

O sistema irá processar a página e devolver o resultado com duas áreas:

**Relatório de Hierarquia**: Uma extração que apresenta se a árvore de H1, H2 e H3 está consistente.
**Visualização da Página**: A página é renderizada com as secções em destaque, permitindo visualizar o posicionamento de cada cabeçalho.

<div align="center">
  <img src="./docs/screenshots/resultado_iframe.png" alt="Exemplo da Auditoria de Página com renderização no iframe" style="max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0px 4px 15px rgba(0,0,0,0.1);" />
</div>

### Outros Modos Disponíveis

- **Sitemap**: Extração e análise de múltiplas páginas a partir do URL de um sitemap.xml.

- **Crawler**: Exploração e verificação automática de um website.

- **Validação Multi-URL**: Análise de uma lista de URLs.

---

## Páginas Testadas

Por enquanto, a ferramenta foi testada nas seguintes páginas:

[Notícias de Alenquer](https://www.alenquer.pt/noticias)
