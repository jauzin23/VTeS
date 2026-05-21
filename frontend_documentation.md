# VF-TeS: Frontend & Backend Integration Handover Guide

This guide details the architecture, data contracts, and interaction design of VF-TeS to allow developers (or AI systems) to understand, extend, and rebuild the frontend or backend components.

---

## 1. System Architecture Overview

VF-TeS is structured as a light developer console consisting of:

1. **Frontend**: A React Single Page Application (SPA) built with Vite, CSS Modules, and `@tanstack/react-query` for server mutations.
2. **Backend**: A FastAPI (Python 3) web server that:
   - Controls a headless Chromium instance pool via **Playwright** to discover links, render JavaScript-heavy sites, and perform semantic DOM queries.
   - Audits headings and builds semantic trees.
   - Post-processes page HTML, injecting CSS/JS overlays for interactive visual highlighting inside an iframe preview.
   - Hosts static assets of the built React SPA, providing SPA fallback routing.

---

## 2. Backend API Endpoints

The FastAPI server exposes three key endpoints under port `3001` (by default):

### 2.1 `/api/health`

- **Method**: `GET`
- **Purpose**: Serves as a health status indicator and concurrency queue reporter.
- **Response Example**:
  ```json
  {
    "status": "healthy",
    "active_tasks": 0,
    "pending_tasks": 0,
    "concurrency_limit": 2
  }
  ```

### 2.2 `/api/discover`

- **Method**: `POST`
- **Payload**:
  ```json
  { "url": "https://example.com/listings" }
  ```
- **Purpose**: Discover list/detail URLs on a page, parsing pagination to find structured detail page links (articles, events, notices).
- **Behavior**:
  - Spawns a headless browser, clicks cookie banners, and runs pagination detection (`JS_DETETAR_PAGINACAO`).
  - Resolves links from multiple pages in parallel using a card-based link extraction hierarchy.
  - Returns a unique list of detail page URLs.
- **Response Example**:
  ```json
  {
    "status": "success",
    "target_url": "https://example.com/listings",
    "urls": [
      "https://example.com/listings/detail-item-1",
      "https://example.com/listings/detail-item-2"
    ]
  }
  ```

### 2.3 `/api/audit`

- **Method**: `POST`
- **Payload**:
  ```json
  { "url": "https://example.com/listings/detail-item-1" }
  ```
- **Purpose**: Audits the accessibility structure of a single page's headings, runs semantic checks, and transforms the HTML for iframe injection.
- **Response Example**:
  ```json
  {
    "url": "https://example.com/listings/detail-item-1",
    "finalUrl": "https://example.com/listings/detail-item-1",
    "headings": [
      {
        "index": 0,
        "tag": "H1",
        "level": 1,
        "text": "Título Principal",
        "outerHTML": "<h1>Título Principal</h1>",
        "xpath": "/html/body/main/h1"
      }
    ],
    "analysis": {
      "passed": false,
      "issues": [
        {
          "rule": "2.2",
          "type": "salto-nivel",
          "severity": "critical",
          "message": "Salto na hierarquia detetado de H1 para H3",
          "affectedIndexes": [1]
        }
      ]
    },
    "processedHtml": "<!DOCTYPE html><html>...[Injected scripts & overlays]...</html>",
    "auditadoEm": "2026-05-20T12:00:00Z"
  }
  ```

---

## 3. Heading Analysis Auditing Rules (WCAG 2.1)

The backend (`analyzer.py`) checks headers against three rules:

1. **Rule 2.1 (`h1-ausente` / `h1-multiplo`)**:
   - Critical issue if zero `<h1>` tags exist.
   - Warning issue if more than one `<h1>` tag exists.
2. **Rule 2.2 (`salto-nivel`)**:
   - Critical issue if a heading tag skips a nesting level (e.g. `H1` directly to `H3` or `H4` without a intervening `H2`).
3. **Rule 2.3 (`heading-vazio`)**:
   - Warning issue if a heading has no text or is empty.

---

## 4. Frontend Component Structure & State

State in `client/src/App.jsx` handles two navigation modes:

- **Single URL mode**: Initiated via `useAudit` hook. Directly fires `/api/audit` and displays results.
- **Varrimento Multi-URL mode**: Initiated via `useDiscover` hook.
  - **Dynamic Pagination**: If a single URL is pasted, VF-TeS calls `/api/discover` to run pagination scans, prepending the index page to the audit list.
  - **Direct Multi-URL Paste**: If multiple URLs (separated by spaces or commas) are pasted, VF-TeS bypasses the `/api/discover` endpoint entirely, parsing and listing the URLs directly in the accordion list to be audited individually.
  - It displays an accordion pipeline grid (`AccordionList`) where each row represents a separate page, internally fetching its audit dynamically using `useAudit`.

### 4.1 React State Management Hooks

- **`useAudit.js`**: Wraps API audits in a TanStack Query Mutation (`useMutation`). Keeps track of loaded results, loading states, and error alerts.
- **`useDiscover.js`**: Tracks the multi-url discovery pipeline array. Extends `data.urls` to ensure the original inputted URL is prepended as the first page to be checked.

### 4.2 Key Components

1. **`TopBar`**: Toggles between Página Única and Multi-URL scanning. Uses CSS-driven sliding tabs instead of inputs.
2. **`HeadingTree`**: Renders hierarchical heading trees with custom vertical guide lines. Level badges use matching semantic variables:
   - `H1` = `--h1-cor` (Amber)
   - `H2` = `--h2-cor` (Indigo/Purple)
   - `H3` = `--h3-cor` (Cyber Cyan)
3. **`IssuePanel`**: Displays cards showing accessibility rule failures with left-accent borders (`var(--cor-erro)` for critical, `var(--cor-aviso)` for warnings).
4. **`RenderPanel`**: Wraps the iframe in a browser shell, handling scaling computations.

---

## 5. Page Rendering & Iframe Communication

One of the application's most critical features is the interactive selection between the heading list in the `HeadingTree` component and the visual preview in the `RenderPanel`. This works via dynamic HTML post-processing and a two-way `postMessage` protocol:

### 5.1 Backend HTML Post-Processor (`html_processor.py`)

To render the page correctly inside an iframe without triggering script execution locks, the backend processes the raw page:

1. Strips away all script blocks `<script>` and `<noscript>` to prevent redirections.
2. Disables all links (`a` tags have their `onclick` attributes overridden to `return false`).
3. Prepends a `<base href="...">` containing the target's original absolute base path.
4. Injects CSS rules defining:
   - Helper overlays (`.VF-TeS-overlay`): Absolutely positioned boxes layered directly on top of each heading tag's computed viewport coordinates.
   - Visual boxes: Red borders for elements with structural errors, yellow borders for warning tags, and colored level labels.
5. Injects JS logic that runs inside the iframe:
   - When the page loads, it locates all heading elements and computes their exact position relative to the document:
     ```javascript
     const rect = el.getBoundingClientRect();
     const top = rect.top + window.scrollY;
     const left = rect.left + window.scrollX;
     ```
   - Creates a transparent absolute div overlay on top of each heading with `data-index`.
   - Attaches click listeners: clicking an overlay posts a message to the React window:
     ```javascript
     window.parent.postMessage({ type: "heading-clicked", index: idx }, "*");
     ```
   - Attaches a message listener (`message` event) to wait for heading selections from the React parent:
     - On message type `select-heading`, it matches the selected heading index, adds active glow styles, and scrolls the element smoothly into view:
       ```javascript
       window.scrollTo({ top: elementTop - 100, behavior: "smooth" });
       ```

### 5.2 Frontend React Communication (`RenderPanel.jsx`)

- **Listen to Iframe**: The React panel attaches a window listener for `message` events:
  ```javascript
  useEffect(() => {
    function onMessage(e) {
      if (e.data?.type === "heading-clicked") {
        onSelectHeading(e.data.index); // Update selected state in App.jsx
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [onSelectHeading]);
  ```
- **Send to Iframe**: When the `selectedIndex` state changes (due to a node click in the tree), React forwards a message into the iframe context:
  ```javascript
  useEffect(() => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: "select-heading", index: selectedIndex },
        "*",
      );
    }
  }, [selectedIndex]);
  ```
