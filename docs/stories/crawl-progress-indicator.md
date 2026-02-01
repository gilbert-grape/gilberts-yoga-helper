# Story: Crawl-Fortschrittsanzeige mit Zeitschätzung

## Übersicht

**Als** Benutzer des Gebrauchtwaffen Aggregators
**möchte ich** während eines Crawls sehen, wie weit der Fortschritt ist und wie lange es noch dauert
**damit** ich weiß, ob ich warten soll oder später wiederkommen kann

## Akzeptanzkriterien

### AC1: Fortschrittsanzeige
- [ ] Anzeige "X von Y Quellen" während des Crawls
- [ ] Visueller Fortschrittsbalken (z.B. `████████░░░░`)
- [ ] Aktuell verarbeitete Quelle wird angezeigt

### AC2: Zeitschätzung (ETA)
- [ ] Geschätzte Restzeit in groben Minuten anzeigen ("ca. 3 Min")
- [ ] Keine falsche Präzision (keine Sekunden)

### AC3: Intelligente Berechnung
- [ ] **Mit Historie (≥3 Crawls):** Durchschnitt der letzten 3 erfolgreichen Crawl-Dauern verwenden
- [ ] **Ohne Historie (<3 Crawls):** Echtzeit-Berechnung: `(elapsed / sources_done) * sources_remaining`
- [ ] Nur erfolgreiche Crawls (`is_success == True`) für Historie berücksichtigen

### AC4: Crawl-Historie speichern
- [ ] Neue Tabelle `crawl_runs` mit: `id`, `started_at`, `completed_at`, `duration_seconds`, `sources_attempted`, `sources_succeeded`, `is_success`
- [ ] Nach jedem Crawl einen Eintrag erstellen

## Technische Details

### Backend-Änderungen

**1. Neues Datenbankmodell `CrawlRun`:**
```python
class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    sources_attempted = Column(Integer, default=0)
    sources_succeeded = Column(Integer, default=0)
    is_success = Column(Boolean, default=False)
```

**2. CrawlState erweitern:**
```python
@dataclass
class CrawlState:
    # ... bestehende Felder ...
    sources_total: int = 0
    sources_done: int = 0
    started_at: Optional[datetime] = None
```

**3. Neue CRUD-Funktionen:**
- `save_crawl_run(session, result: CrawlResult)` - Speichert Crawl-Durchgang
- `get_avg_crawl_duration(session, limit=3)` - Holt Durchschnitt der letzten N erfolgreichen Crawls

**4. `/admin/crawl/status` Endpoint erweitern:**
- `sources_total`, `sources_done`, `started_at` zurückgeben
- `avg_duration` (historischer Durchschnitt) zurückgeben

### Frontend-Änderungen

**JavaScript ETA-Berechnung:**
```javascript
function calculateETA(data) {
    const elapsed = (Date.now() - new Date(data.started_at)) / 1000;

    if (data.avg_duration && data.avg_duration > 0) {
        // Historische Berechnung
        const remaining = Math.max(0, data.avg_duration - elapsed);
        return Math.ceil(remaining / 60);
    } else if (data.sources_done > 0) {
        // Echtzeit-Berechnung
        const perSource = elapsed / data.sources_done;
        const remaining = perSource * (data.sources_total - data.sources_done);
        return Math.ceil(remaining / 60);
    }
    return null;
}
```

**UI-Darstellung:**
```
┌─────────────────────────────────────────────┐
│  🔄 Crawl läuft...                          │
│  ████████████░░░░░░░░░░░░  5/13 Quellen     │
│                                             │
│  Aktuell: waffenboerse.ch                   │
│  ⏱️ Noch ca. 3 Minuten                       │
└─────────────────────────────────────────────┘
```

## Aufwand-Schätzung

- Backend (Model, CRUD, State): ~1-2 Stunden
- Migration: ~15 Minuten
- Frontend (JS, HTML): ~1 Stunde
- Tests: ~1 Stunde

**Gesamt: ~4 Stunden**

## Abhängigkeiten

- Bestehende Crawl-Infrastruktur (`CrawlState`, `CrawlResult`)
- Admin-Template `crawl_admin.html`
- SQLAlchemy/Alembic für Migration
