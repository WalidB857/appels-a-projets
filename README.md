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
git clone https://github.com/WalidB857/appels-a-projets.git
cd appels-a-projets

# Créer l'environnement et installer les dépendances
uv sync

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials Airtable
```

## 🚀 Utilisation

### Scripts disponibles

```bash
# Tester le modèle de données (charge 443 AAPs)
uv run python scripts/test_model.py

# Exporter les AAPs actifs en CSV
uv run python scripts/export_csv.py --active-only

# Afficher le schéma Airtable recommandé
uv run python scripts/setup_airtable.py --schema

# Tester la connexion Airtable
uv run python scripts/setup_airtable.py --test
```

### Utiliser dans du code Python

```python
from appels_a_projets.connectors import CarenewsConnector, IleDeFranceConnector
from appels_a_projets.processing import normalize_all
from appels_a_projets.models import Category, EligibiliteType

# 1. Fetch et normaliser les données
carenews = CarenewsConnector()
collection = normalize_all(carenews.run(), "Carenews", "https://www.carenews.com")

# 2. Fusionner plusieurs sources
idf = IleDeFranceConnector()
collection.merge(normalize_all(idf.run(), "IDF", "https://data.iledefrance.fr"))

# 3. Filtrer
actifs = collection.filter_active()
assos = actifs.filter_by_eligibilite(EligibiliteType.ASSOCIATIONS)
solidarite = assos.filter_by_category(Category.SOLIDARITE_INCLUSION)
urgents = solidarite.filter_by_urgence("urgent", "proche")

# 4. Statistiques
print(collection.stats())

# 5. Exporter
collection.to_csv("export.csv")
collection.to_json("export.json")
df = collection.to_dataframe()
```

### Explorer les données

```bash
# Lancer Jupyter pour les notebooks d'exploration
uv run jupyter notebook
```

## 📁 Structure du projet

```
appels-a-projets/
├── appels_a_projets/
│   ├── connectors/              # Connecteurs par source
│   │   ├── base.py              # BaseConnector + RawAAP
│   │   ├── carenews.py          # Scraper HTML Carenews
│   │   ├── iledefrance_opendata.py  # API IDF
│   │   └── airtable_connector.py    # Upload Airtable
│   ├── models/                  # Modèles de données (Pydantic)
│   │   └── aap.py               # AAP, Category, EligibiliteType...
│   ├── processing/              # Normalisation, déduplication
│   │   └── normalizer.py        # RawAAP → AAP (avec inférence)
│   └── jobs/                    # Notebooks d'exploration/enrichissement
│       ├── inspect_idf.ipynb
│       ├── scrape_paris.ipynb
│       └── enrichment_*.ipynb   # Enrichissement LLM
├── scripts/                     # Scripts utilitaires
│   ├── test_model.py
│   ├── export_csv.py
│   └── setup_airtable.py
├── data/                        # Données extraites
├── docs/                        # Documentation & specs
├── .env.example                 # Template variables d'environnement
├── pyproject.toml               # Config projet (uv/pip)
└── uv.lock                      # Lock file uv
```

## 🔌 Sources de données

| Source | Type | Méthode | Status | AAPs |
|--------|------|---------|--------|------|
| Carenews | Agrégateur | HTML scraping | ✅ Done | ~100 |
| IDF OpenData | API | REST API | ✅ Done | ~343 |
| Paris.fr | Institutionnel | HTML + PDF + LLM | 🔄 En cours | - |
| Profession Banlieue | Centre ressources | RSS | 🔜 À faire | - |
| DRIEETS IDF | Gouv | RSS | 🔜 À faire | - |

## 📊 Modèle de données

### Taxonomies

**Categories (12):**
`insertion-emploi` · `education-jeunesse` · `sante-handicap` · `culture-sport` · `environnement-transition` · `solidarite-inclusion` · `vie-associative` · `numerique` · `economie-ess` · `logement-urbanisme` · `mobilite-transport` · `autre`

**Éligibilité (7):**
`associations` · `collectivites` · `etablissements` · `entreprises` · `professionnels` · `particuliers` · `autre`

**Périmètre (6):**
`local` · `departemental` · `regional` · `national` · `europeen` · `international`

**Urgence (5):**
`urgent` (≤7j) · `proche` (≤30j) · `confortable` (>30j) · `permanent` · `expire`

### Schéma AAP

```python
AAP(
    # Identité
    id="uuid",
    titre="Concours 2026 de La France s'engage",
    url_source="https://...",
    source=Source(id="carenews", name="Carenews"),
    
    # Dates
    date_publication=date(2025, 12, 24),
    date_limite=date(2026, 1, 29),
    
    # Classification
    categories=[Category.SOLIDARITE_INCLUSION],
    tags=["ESS", "innovation sociale"],
    eligibilite=[EligibiliteType.ASSOCIATIONS],
    
    # Géographie
    perimetre_niveau=Perimetre.NATIONAL,
    perimetre_geo="France",
    
    # Financement
    montant_min=10000,
    montant_max=300000,
    
    # Computed fields
    fingerprint="abc123...",   # Déduplication
    is_active=True,
    days_remaining=26,
    urgence="proche",
    statut=StatutAAP.OUVERT,
)
```

## 💾 Stockage Airtable

La base Airtable contient **200+ AAPs actifs** avec tous les champs du modèle.

```bash
# Vérifier la connexion
uv run python scripts/setup_airtable.py --test

# Exporter et importer de nouvelles données
uv run python scripts/export_csv.py --active-only
# Puis importer le CSV dans Airtable
```

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

- [x] Scraper Carenews (HTML) → ~100 AAPs
- [x] Connecteur API IDF OpenData → ~343 AAPs
- [x] Modèle de données normalisé (Pydantic) avec taxonomies riches
- [x] Pipeline : Connector → RawAAP → Normalizer → AAP → AAPCollection
- [x] Déduplication par fingerprint
- [x] Migration Poetry → uv

### ✅ Phase 1 : MVP (Done)

- [x] Stockage Airtable (200+ AAPs actifs)
- [x] Export CSV avec filtres
- [x] Scripts setup Airtable
- [x] Computed fields : `is_active`, `days_remaining`, `urgence`
- [x] Filtres : by_category, by_eligibilite, by_urgence

### 🔄 Phase 1.5 : Enrichissement (En cours)

- [ ] Paris.fr scraping (PDF + LLM) — *Walid*
- [ ] Enrichissement LLM (catégories, tags) via Claude
- [ ] Cron GitHub Actions (collecte quotidienne)
- [ ] Alerte Telegram (nouveaux AAPs)

### 📋 Phase 2 : Consolidation

- [ ] Ajouter sources RSS (Profession Banlieue, DRIEETS)
- [ ] Tests unitaires & intégration
- [ ] UI de consultation (Notion ou web)
- [ ] Métriques (nb AAP/semaine, sources actives)

### 🚀 Phase 3 : Expansion

- [ ] Multi-tenant (plusieurs assos)
- [ ] Matching intelligent asso/AAP
- [ ] Scraping fondations privées

## 👥 Équipe

- **Younes Ajeddig** — Développement, scraping, data model
- **Walid Becherif** — Architecture, API IDF, enrichissement LLM

## 📄 License

MIT
