# Campaign Selector — Rutina OpenClaw

> **Estado**: Pendiente de implementar.
> **Responsable**: OpenClaw (VPS Ubuntu).
> **Patrón**: skill + cron, NO un módulo Python tradicional.
> **Frecuencia**: cada 1 hora (`0 * * * *`).

## Filosofía

No es un software monolítico. Es una **rutina** que OpenClaw ejecuta cada hora y que combina:

- **Skills** (tools ya disponibles: `web_fetch`, `web_search`, `db_query`, `notify_telegram`).
- **Estado persistente** en PostgreSQL (`campaigns`, `campaign_sources`).
- **Política declarativa** en YAML: lista de fuentes, criterios por fuente, scoring mínimo.

La inteligencia (qué cuenta como "relevante") la pone el **LLM** (MiniMax) leyendo la página. El código solo orquesta y persiste.

---

## Diagrama lógico

```
┌─────────────────────────────────────────────────────────────┐
│                  OpenClaw (VPS)                              │
│                                                              │
│   cron cada 1h                                               │
│       │                                                      │
│       ▼                                                      │
│   skill: campaign_selector.run()                             │
│       │                                                      │
│       ├─► Lee `campaign_sources` activas de PostgreSQL       │
│       │                                                      │
│       ├─► Para cada source:                                  │
│       │     ├─► web_fetch(url_listado)                       │
│       │     ├─► web_fetch(detalle) si el listado lo requiere │
│       │     ├─► LLM evalúa: ¿campaña válida? ¿relevante?    │
│       │     │   - tema, idioma, payout, deadline, evidencia  │
│       │     └─► db_query: INSERT en `campaigns`             │
│       │             si pasa el scoring mínimo                │
│       │                                                      │
│       ├─► Anti-duplicados: hash(url) + UNIQUE               │
│       │                                                      │
│       └─► notify_telegram: resumen de la hora                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Persistencia

### Tabla `campaign_sources` (config)

Lista declarativa de webs a vigilar. OpenClaw la lee, no la hardcodea.

```sql
CREATE TABLE campaign_sources (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,                    -- "rewardup", "affiliate-x"
    base_url      TEXT NOT NULL,
    listing_url   TEXT NOT NULL,                    -- URL donde están los enlaces a campañas
    list_selector JSONB NOT NULL,                  -- selector CSS / patrón para extraer links
    detail_prompt TEXT NOT NULL,                   -- prompt que recibe el LLM con el HTML
    score_min     INT NOT NULL DEFAULT 60,         -- 0-100, por debajo se descarta
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at   TIMESTAMPTZ,
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Tabla `campaigns` (lo que descubre)

Una fila por **campaña detectada** (no por source). El estado evoluciona.

```sql
CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       INT NOT NULL REFERENCES campaign_sources(id),
    external_id     TEXT,                          -- id de la plataforma si existe
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,                 -- URL canónica de la campaña
    summary         TEXT,                          -- resumen corto del LLM
    raw_payload     JSONB,                         -- lo que devolvió el LLM (evidencia)
    relevance_score INT NOT NULL,                  -- 0-100
    status          TEXT NOT NULL DEFAULT 'new',   -- new|analyzing|rejected|accepted|done|failed
    evidence        JSONB,                         -- {selector, snippet, screenshot_url?}
    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);

CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_discovered_at ON campaigns(discovered_at DESC);
```

---

## Política declarativa

`/etc/openclaw/campaign_selector.yaml` (ruta sugerida):

```yaml
scheduler:
  cron: "0 * * * *"          # cada hora en punto
  timezone: "Europe/Madrid"
  on_error:
    notify_telegram: true
    backoff_minutes: 30       # si falla, espera 30 min antes de reintentar

evaluation:
  model: "MiniMax"
  prompt: |
    Eres un evaluador de campañas de recompensas para clipers de vídeo.
    Recibes el HTML/contenido de una página de campaña. Devuelve JSON con:
    {
      "is_campaign": bool,
      "relevance_score": 0-100,
      "title": string,
      "summary": string,
      "evidence": { "deadline": str?, "payout": str?, "language": str?, "vertical": str? },
      "rules_summary": string,   # breve descripción de las reglas
      "assets_url": [str]        # URLs de vídeos fuente si las ves
    }
    Criterios:
    - score 0 si NO es campaña o ya está cerrada
    - score 60+ si la campaña está activa y el pago/condiciones merecen la pena
    - score 80+ si es claramente interesante (pago alto, deadline amplio, tema top)
  max_tokens: 2000
  temperature: 0.0
  on_relevance_below: 60
    action: discard       # no se guarda en `campaigns`, solo se loguea

anti_duplicates:
  by: ["source_id", "external_id"]   # unique constraint
  soft_match:
    enabled: true
    fuzzy_threshold: 0.85            # Levenshtein normalizado sobre título
    action: keep_newest              # si se repite, conserva la más reciente

notifications:
  telegram:
    enabled: true
    on_new_campaigns: true
    template: "🆕 {count} campañas nuevas en las últimas {window}\nTop: {titles_short}"
```

---

## Skill `campaign_selector.run()`

Interfaz que expone OpenClaw. Pseudocódigo (no implementación rígida):

```yaml
skill: campaign_selector
description: "Descubre campañas de recompensas desde sources declaradas y las persiste."

inputs: {}
outputs:
  ok: bool
  campaigns_new: int
  campaigns_updated: int
  sources_run: int
  errors: list[str]

steps:
  - read_sources()         -> list[CampaignSource] donde enabled=true
  - for source in sources:
      - try:
          - html = web_fetch(source.listing_url)
          - links = extract_links(html, source.list_selector)
          - for link in links:
              - if already_seen(source, link): continue
              - detail = web_fetch(link)
              - eval = llm_evaluate(detail, source.detail_prompt)
              - if not eval.is_campaign: continue
              - if eval.relevance_score < source.score_min: continue
              - upsert_campaign(source, eval)
      - catch as e:
          - mark_source_error(source, e)
          - notify_telegram("Error en " + source.name)
  - summarize_window()     -> notify_telegram si hay nuevas
```

---

## Por qué este diseño y no un módulo Python

| Aspecto | Skill + cron + YAML | Módulo Python tradicional |
|---|---|---|
| Añadir una web nueva | INSERT en `campaign_sources` + YAML | Tocar código, redeploy |
| Cambiar criterios | Editar `detail_prompt` del LLM | Reescribir regex/parser |
| Iterar el prompt | Reload YAML, sin reinicio | Redeploy |
| Testear | Dry-run con HTML guardado | Mocks, fixtures |
| Coste | Una llamada LLM por campaña | Lo mismo (no es ventaja) |
| Coste de mantener | Bajo (declarativo) | Alto (código de scraping) |

El scraper **cambia cada vez** porque cada web cambia. El LLM tolera cambios estructurales y devuelve JSON estructurado. Por eso la **complejidad se externaliza al prompt**, no al código.

---

## Pruebas

Antes de activar en producción:

1. **Dry-run offline**: cargar 1 web real, ejecutar la skill, guardar resultados en `tests/fixtures/`, revisar a mano.
2. **Shadow run**: la skill corre pero NO notifica ni escribe en `campaigns`, solo en `campaign_selector_logs`.
3. **Live run**: activa `notify_telegram` y `score_min=80` (estricto) durante 1 semana para calibrar.
4. **Calibración**: ajusta `score_min` y `detail_prompt` mirando los falsos positivos.

---

## Lo siguiente

- [ ] Definir `sources` reales (URLs concretas) y meter las 3-5 más estables en `campaign_sources`.
- [ ] Escribir `detail_prompt` base y medir coste medio por evaluación.
- [ ] Configurar el cron en el VPS y la skill.
- [ ] Hacer un shadow run de 24 h antes de notificar.

Ver también:

- `AGENTS.md` para el flujo completo.
- Próximo documento a crear: `docs/campaign_analyzer.md` (cómo el LLM convierte `campaigns` en `CampaignSpec`).
