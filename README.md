# AAP-Watch 🔔

> Agrégateur d'Appels à Projets pour associations (ESS, solidarité, inclusion)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet)](https://docs.astral.sh/uv/)

## 🎯 Problème résolu

La veille sur les appels à projets (AAP) est chronophage pour les associations :
- Sources dispersées (collectivités, fondations, agrégateurs)
- Pas de centralisation ni d'API unifiée
- Formats hétérogènes
- Risque de rater des deadlines

**AAP-Watch** automatise la collecte, normalisation et alerting des AAP pertinents.

## 📦 Installation

### Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (gestionnaire de packages)

```bash
# Installer uv (si pas déjà installé)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup du projet

```bash
# Cloner le repo
git clone https://github.com/votre-user/appels-a-projets.git
cd appels-a-projets

# Créer l'environnement et installer les dépendances
uv sync

# Activer l'environnement (optionnel, uv run fait ça automatiquement)
source .venv/bin/activate
```

> **Note :** Le projet utilisait initialement Poetry. La migration vers uv a été faite pour une meilleure performance et simplicité. Le fichier `poetry.lock` est conservé pour référence mais n'est plus utilisé.

## 🚀 Utilisation

### Lancer un connecteur

```bash
# Scraper Carenews (HTML scraping)
uv run python -m appels_a_projets.connectors.carenews

# API Île-de-France OpenData
uv run python -m appels_a_projets.connectors.iledefrance_opendata
```

### Utiliser dans du code Python

```python
from appels_a_projets.connectors import CarenewsConnector, IleDeFranceConnector
from appels_a_projets.processing import normalize_all
from appels_a_projets.models import AAPCollection, Category

# 1. Fetch les données brutes
connector = CarenewsConnector()
raw_aaps = connector.run()

# 2. Normaliser vers le schéma AAP
aaps = normalize_all(raw_aaps, "Carenews", "https://www.carenews.com/appels_a_projets")

# 3. Créer une collection (avec déduplication)
collection = AAPCollection(aaps=aaps, sources=["carenews"])

# 4. Filtrer
active_aaps = collection.filter_active()
education_aaps = collection.filter_by_category(Category.EDUCATION_JEUNESSE)

# 5. Exporter
df = collection.to_dataframe()
```

### Explorer les données

Le notebook `appels_a_projets/jobs/inspect_idf.ipynb` permet d'explorer les données de l'API IDF.

```bash
# Lancer Jupyter
uv run jupyter notebook
```

## 📁 Structure du projet

```
appels-a-projets/
├── appels_a_projets/
│   ├── connectors/          # Connecteurs par source
│   │   ├── base.py          # BaseConnector + RawAAP
│   │   ├── carenews.py      # Scraper HTML Carenews
│   │   └── iledefrance_opendata.py  # API IDF
│   ├── models/              # Modèles de données (Pydantic)
│   │   └── aap.py           # AAP, Category, AAPCollection
│   ├── processing/          # Normalisation, déduplication
│   │   └── normalizer.py    # RawAAP → AAP
│   └── jobs/                # Notebooks d'exploration
├── data/                    # Données extraites (JSON)
├── docs/                    # Documentation & specs
├── pyproject.toml           # Config projet (uv/pip)
└── uv.lock                  # Lock file uv
```

## 🔌 Sources de données

| Source | Type | Méthode | Status |
|--------|------|---------|--------|
| Carenews | Agrégateur | HTML scraping | ✅ Implémenté |
| IDF OpenData | API | REST API | ✅ Implémenté |
| Paris.fr | Institutionnel | HTML scraping | 🔜 À faire |
| Profession Banlieue | Centre ressources | RSS | 🔜 À faire |
| DRIEETS IDF | Gouv | RSS | 🔜 À faire |

## 📊 Modèle de données

Chaque AAP est normalisé vers ce schéma :

```python
AAP(
    id="uuid",
    titre="Concours 2026 de La France s'engage",
    url_source="https://...",
    source=Source(id="carenews", name="Carenews", url="..."),
    organisme="Fondation La France s'engage",
    date_publication=date(2025, 12, 24),
    date_limite=date(2026, 1, 29),
    categories=[Category.SOLIDARITE_INCLUSION],
    tags=["ESS", "innovation sociale"],
    perimetre_geo="National",
    public_cible=["associations", "fondations"],
    montant_max=300000,
    resume="...",
    # Computed fields
    fingerprint="abc123...",  # Pour déduplication
    is_active=True,
    days_remaining=26,
)
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

## 🛠️ Développement

### Commandes utiles

```bash
# Installer les dépendances (y compris dev)
uv sync

# Ajouter une dépendance
uv add <package>

# Lancer les tests
uv run pytest

# Linter/Formatter
uv run ruff check .
uv run ruff format .
```

### Branches

- `main` : Version stable
- `dev` : Développement actif
- `feature/*` : Nouvelles fonctionnalités

## 🗺️ Roadmap

### ✅ Phase 0 : POC (Done)

- [x] Scraper Carenews (HTML) → 40+ AAPs
- [x] Connecteur API IDF OpenData → 100+ AAPs
- [x] Modèle de données normalisé (Pydantic)
- [x] Pipeline : Connector → RawAAP → Normalizer → AAP
- [x] Déduplication par fingerprint
- [x] Migration Poetry → uv

### 🔄 Phase 1 : MVP (En cours)

- [ ] Ajouter sources P1 (Paris.fr, RSS)
- [ ] Enrichissement LLM (catégories, tags) via Gemini Flash
- [ ] Stockage Notion API
- [ ] Cron GitHub Actions (collecte quotidienne)
- [ ] Alerte Telegram (nouveaux AAPs)

### 📋 Phase 2 : Consolidation

- [ ] Tests unitaires & intégration
- [ ] UI de consultation (Notion ou web)
- [ ] Métriques (nb AAP/semaine, sources actives)
- [ ] Documentation API

### 🚀 Phase 3 : Expansion

- [ ] Multi-tenant (plusieurs assos)
- [ ] Matching intelligent asso/AAP
- [ ] Scraping fondations privées

## 👥 Équipe

- **Younes Ajeddig** — Développement, scraping
- **Walid Becherif** — Architecture, API IDF

## 📄 License

MIT
