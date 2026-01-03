# AAP-Watch — Instructions Copilot

## 🎯 Contexte du projet

**AAP-Watch** est un agrégateur d'Appels à Projets (AAP) destiné aux associations (ESS, solidarité, inclusion).

### Problème résolu
La veille sur les AAP est chronophage car :
- Sources dispersées (collectivités, fondations, agrégateurs)
- Pas de centralisation ni d'API unifiée
- Formats hétérogènes
- Risque de rater des deadlines

### Objectif
Automatiser la collecte, normalisation et alerting des AAP pertinents pour les associations.

---

## 🏗️ Architecture

### Stack technique
- **Langage** : Python 3.12+
- **Package manager** : uv
- **Scraping HTML** : BeautifulSoup + requests
- **Parsing RSS** : feedparser
- **LLM** : Gemini Flash (extraction structurée)
- **Storage** : Notion API (MVP)
- **Orchestration** : GitHub Actions (cron)
- **Alertes** : Telegram Bot

### Structure du projet
```
appels-a-projets/
├── appels_a_projets/
│   ├── connectors/          # Connecteurs par source
│   │   ├── carenews.py      # Scraper HTML Carenews
│   │   ├── iledefrance_opendata.py  # API IDF
│   │   ├── rss_generic.py   # Parser RSS générique
│   │   └── ...
│   ├── models/              # Modèles de données (Pydantic)
│   ├── processing/          # Normalisation, déduplication
│   ├── storage/             # Connecteurs storage (Notion, etc.)
│   └── alerting/            # Notifications (Telegram, email)
├── data/                    # Données locales (dev/debug)
├── docs/                    # Documentation & specs
├── tests/                   # Tests unitaires et intégration
└── .github/workflows/       # GitHub Actions (cron jobs)
```

---

## 📊 Modèle de données AAP

Schéma normalisé pour tous les AAP, quelle que soit la source :

```python
class AAP(BaseModel):
    id: str                          # UUID
    titre: str
    organisme: str
    date_publication: date | None
    date_limite: date | None
    categories: list[str]            # Taxonomie fixe (filtrage)
    tags: list[str]                  # Tags libres (LLM)
    perimetre_geo: str | None
    public_cible: list[str]          # ["associations", "ESUS", ...]
    montant_min: float | None
    montant_max: float | None
    url_source: str
    url_candidature: str | None
    resume: str                      # Max 300 chars
    source_id: str                   # Identifiant source
    created_at: datetime
    fingerprint: str                 # hash(titre+organisme+date_limite)
```

### Catégories (taxonomie fixe)
- `insertion-emploi`
- `education-jeunesse`
- `sante-handicap`
- `culture-sport`
- `environnement-transition`
- `solidarite-inclusion`
- `vie-associative`
- `numerique`
- `autre`

---

## 🔌 Sources de données (MVP)

| Source | Type | Méthode | Priorité |
|--------|------|---------|----------|
| Carenews | Agrégateur | HTML scraping | P0 |
| IDF OpenData | API | REST API | P0 |
| Paris.fr | Institutionnel | HTML scraping | P1 |
| Profession Banlieue | Centre ressources | RSS | P1 |
| DRIEETS IDF | Gouv | RSS | P2 |

### URLs des sources
```
# P0
https://www.carenews.com/appels_a_projets
https://data.iledefrance.fr/explore/dataset/aides-appels-a-projets/api/

# P1
https://www.paris.fr/pages/repondre-a-un-appel-a-projets-5412
https://www.professionbanlieue.org/Appels-a-projets-Appel-a-manifestation-d-interet
```

---

## 🛠️ Conventions de développement

### Style de code
- Python moderne (3.12+) : type hints, match statements, f-strings
- Formatage : ruff (format + lint)
- Validation : Pydantic v2 pour les modèles
- Async : utiliser `httpx` pour les requêtes si besoin de parallélisme

### Patterns pour les connecteurs

Chaque connecteur doit :
1. Hériter d'une classe `BaseConnector`
2. Implémenter `fetch_raw()` → données brutes
3. Implémenter `parse(raw_data)` → liste d'AAP normalisés
4. Gérer ses propres erreurs et logging
5. Respecter les rate limits

```python
class BaseConnector(ABC):
    source_id: str
    source_name: str
    
    @abstractmethod
    def fetch_raw(self) -> Any:
        """Récupère les données brutes de la source"""
        pass
    
    @abstractmethod
    def parse(self, raw_data: Any) -> list[AAP]:
        """Parse et normalise les données en AAP"""
        pass
    
    def run(self) -> list[AAP]:
        """Exécute le pipeline complet"""
        raw = self.fetch_raw()
        return self.parse(raw)
```

### Gestion des erreurs
- Logger toutes les erreurs avec contexte (source, URL, timestamp)
- Ne jamais crasher le pipeline complet si une source échoue
- Retry avec backoff exponentiel pour les erreurs réseau

### Tests
- Un fichier de test par connecteur
- Fixtures avec des exemples de HTML/JSON réels (anonymisés si besoin)
- Mocks pour les appels réseau dans les tests unitaires

---

## 🚀 Commandes utiles

```bash
# Environnement
uv sync                          # Installer les dépendances
source .venv/bin/activate        # Activer l'environnement

# Développement
uv run python -m pytest          # Lancer les tests
uv run ruff check .              # Linter
uv run ruff format .             # Formatter

# Connecteurs (exemples)
uv run python -m appels_a_projets.connectors.carenews
uv run python -m appels_a_projets.connectors.iledefrance_opendata
```

---

## 📝 Notes importantes

1. **Approche pragmatique** : "Déjà fetch les données, après tu verras ton modèle"
2. **Connecteurs ciblés** : Pas d'agent RL/adaptatif pour le MVP, connecteurs dédiés par source
3. **Déduplication** : `fingerprint = hash(titre + organisme + date_limite)`
4. **Coût maîtrisé** : < $10/mois (GitHub Actions gratuit, Gemini Flash ~$1-5)

---

## 👥 Équipe

- **Younes Ajeddig** : Développement, scraping
- **Walid Becherif** : Architecture, API IDF
