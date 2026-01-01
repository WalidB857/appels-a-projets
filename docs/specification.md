# AAP-Watch — Spécifications v0.1

> Agrégateur d'Appels à Projets pour associations (ESS, solidarité, inclusion)
> 
> **Auteurs :** Younes Ajeddig, Walid Becherif  
> **Date :** 01/01/2026  
> **Statut :** Draft - En discussion

---

## 1. Contexte & Problème

### 1.1 Utilisateur cible

**Persona principal :** Pauline (chargée de mission en association)
- Doit répondre à des AAP pour financer l'activité de l'asso
- Les subventions = 80-90% du budget (vs 10-20% formations/autres)
- Sa responsable passe un temps significatif sur la veille AAP

**Marché potentiel :** Toutes les associations font cette veille (ESS, solidarité, insertion, culture...)

### 1.2 Pain point

La veille sur les appels à projets (AAP) est chronophage car :
- Sources dispersées (collectivités, fondations, agrégateurs)
- Pas de centralisation ni d'API unifiée
- Formats hétérogènes
- Risque de rater des deadlines

> 💡 **Validation à obtenir :** Temps passé par mois sur cette tâche (Pauline + responsable)
> Si plusieurs jours/mois → business model viable

### 1.3 Objectif

Automatiser la collecte, normalisation et alerting des AAP pertinents.

### 1.4 Pourquoi ça n'existe pas déjà ?

Même constat que les marchés publics : fragmentation extrême des sources, pas d'incitation des émetteurs à standardiser. Opportunité de marché si on crack le problème technique.

---

## 2. Périmètre fonctionnel

### 2.1 In Scope (MVP)

| Fonction | Description |
|----------|-------------|
| Collecte automatisée | Ingestion quotidienne/hebdo des sources définies |
| Normalisation | Extraction structurée (titre, dates, thème, périmètre...) |
| Stockage centralisé | Base consultable avec filtres |
| Alertes | Notification des nouveaux AAP par thème/deadline |
| Déduplication | Éviter les doublons cross-sources |

### 2.2 Out of Scope (V1)

- Candidature automatique aux AAP
- Scraping LinkedIn (trop risqué)
- Sources nécessitant authentification
- Analyse de pertinence personnalisée (matching asso/AAP)

---

## 3. Sources de données

### 3.1 Sources validées pour MVP

| Source | Type | Méthode | Priorité |
|--------|------|---------|----------|
| Carenews | Agrégateur | HTML scraping | P0 |
| IDF OpenData | API | REST API | P0 |
| Paris.fr | Institutionnel | HTML scraping | P1 |
| Profession Banlieue | Centre ressources | RSS | P1 |
| DRIEETS IDF | Gouv | RSS | P2 |

### 3.2 Sources à auditer (V2)

| Source | Difficulté | Notes |
|--------|------------|-------|
| Seine-Saint-Denis | 🔴 | Anti-bot (shield/redirect) |
| Fondations privées | 🔴 | Pas de listing, juste "proposer un projet" |
| novapec.fr | ? | À tester |
| lelabo-partenariats.org | ? | À tester |

### 3.3 Fondations mentionnées (hors scope MVP)

AESIO, AFNIC, Air Liquide, Bouygues, Bolloré, Caritas, Crédit Agricole, EDF, Fondation de France, FDJ

> ⚠️ La plupart n'ont pas de page "liste des AAP" mais seulement "proposer un projet"

### 3.4 Stratégie d'acquisition de sources

```
Phase 1 : Sources publiques (scraping/API)
    └── MVP avec 5 sources stables

Phase 2 : Contact direct des organismes
    └── "Avez-vous un flux RSS ou API pour vos AAP ?"
    └── Plus simple si on a déjà un produit à montrer
    └── Certains peuvent ouvrir un accès sur demande

Phase 3 : Partenariats
    └── Intégration avec plateformes existantes
    └── Data sharing avec agrégateurs
```

> 💡 "Des fois, demander un flux d'information directement à l'organisme, ça permet qu'ils t'ouvrent un RSS ou une API. Mais c'est plus simple si t'as déjà un truc à présenter." — Walid

---

## 4. Modèle de données

> ⚠️ **Approche pragmatique :** "Déjà fetch les données, après tu verras ton modèle" — Walid
> 
> On commence simple, on itère.

### 4.1 Schéma AAP normalisé (V1)
<!-- A voir avec ce qu'on obtient comme données -->
```json
{
  "id": "uuid",
  "titre": "string",
  "organisme": "string",
  "date_publication": "date",
  "date_limite": "date",
  "categories": ["string"],      // Taxonomie fixe (filtrage)
  "tags": ["string"],            // Tags libres générés par LLM
  "perimetre_geo": "string",
  "public_cible": ["associations", "ESUS", "collectifs"...],
  "montant_min": "number | null",
  "montant_max": "number | null",
  "url_source": "string",
  "url_candidature": "string | null",
  "resume": "string (300 chars)",
  "source_id": "string",
  "created_at": "datetime",
  "fingerprint": "hash(titre+organisme+date_limite)"
}
```

### 4.2 Catégories vs Tags

| Aspect | Catégories | Tags |
|--------|------------|------|
| **Contrôle** | Fixées par nous | Libres (LLM) |
| **Usage** | Filtrage UI | Recherche, découverte |
| **Cardinalité** | 1-3 par AAP | 0-10 par AAP |
| **Exemple** | `insertion-emploi` | `jeunes`, `QPV`, `formation`, `numérique` |

### 4.3 Taxonomie catégories (draft)

```
categories/
├── insertion-emploi
├── education-jeunesse
├── sante-handicap
├── culture-sport
├── environnement-transition
├── solidarite-inclusion
├── vie-associative
├── numerique
└── autre
```

### 4.4 Modèle relationnel (si Supabase/SQL)

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────┐
│   sources   │       │       aap        │       │ categories  │
├─────────────┤       ├──────────────────┤       ├─────────────┤
│ id          │──┐    │ id               │    ┌──│ id          │
│ name        │  │    │ titre            │    │  │ slug        │
│ url         │  │    │ source_id ───────│────┘  │ label       │
│ type        │  └───▶│ ...              │       └─────────────┘
│ connector   │       │ fingerprint      │              │
└─────────────┘       └──────────────────┘              │
                              │                         │
                              │    ┌────────────────────┘
                              ▼    ▼
                      ┌─────────────────┐
                      │ aap_categories  │  (many-to-many)
                      ├─────────────────┤
                      │ aap_id          │
                      │ category_id     │
                      └─────────────────┘
```

---

## 5. Architecture technique

### 5.1 Philosophie : Connecteurs modulaires

**Décision clé :** Connecteurs ciblés par type de source (pas d'agent RL/adaptatif pour le MVP)

```
Rationale :
├── APIs stables      → Connecteur dédié (fiable, maintenable)
├── RSS              → Connecteur générique feedparser
├── HTML structuré   → Scraper par source (templates)
└── HTML variable    → Agent LLM (V2, si nécessaire)
```

> "Pour les API, connecteur c'est mieux qu'agent. C'est stable." — Walid

### 5.2 Taxonomie des sources

```
┌─────────────────────────────────────────────────────────────────┐
│                    TYPE DE SOURCE                                │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│   API REST   │     RSS      │ HTML Simple  │  HTML Complexe    │
│              │              │              │  (JS/Anti-bot)    │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ Connecteur   │ Connecteur   │ Scraper      │ Agent/Playwright  │
│ API dédié    │ RSS générique│ BeautifulSoup│ (V2)              │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ • IDF Data   │ • Prof.Ban.  │ • Carenews   │ • Seine-St-Denis  │
│              │ • DRIEETS    │ • Paris.fr   │ • Fondations ?    │
└──────────────┴──────────────┴──────────────┴───────────────────┘
```

### 5.3 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│                        SOURCES                                   │
│  [Carenews] [IDF API] [Paris.fr] [RSS feeds] [...]              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                              │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ RSS Parser  │  │ API Client  │  │ HTML Scraper│              │
│  │ (feedparser)│  │ (requests)  │  │ (BS4)       │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
│  Orchestration : GitHub Actions (cron daily/weekly)             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PROCESSING LAYER                               │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 LLM Extraction                           │    │
│  │  Input: HTML/texte brut                                  │    │
│  │  Output: JSON normalisé (schéma §4.1)                    │    │
│  │  Model: Gemini Flash (cost-efficient)                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Déduplication                               │    │
│  │  fingerprint = hash(titre + organisme + date_limite)     │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                                 │
│                                                                  │
│  Option A: Notion (gratuit, UI native)                          │
│  Option B: Airtable (API + UI, limites gratuites)               │
│  Option C: Supabase (SQL, scalable, gratuit tier)               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT LAYER                                  │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Digest Hebdo│  │ Alerte Urgente│ │ Dashboard  │              │
│  │ (email)     │  │ (Telegram)   │  │ (Notion)   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Stack technique proposée

| Composant | Choix MVP | Alternative |
|-----------|-----------|-------------|
| Langage | Python 3.11+ | - |
| Orchestration | GitHub Actions | n8n, Make.com |
| Scraping HTML | BeautifulSoup + requests | Playwright (si JS) |
| Parsing RSS | feedparser | - |
| LLM | Gemini Flash | Claude Haiku |
| Storage | Notion API | Airtable, Supabase |
| Alertes | Telegram Bot | Email SMTP, Slack |
| Repo | GitHub (public ou privé) | - |

### 5.3 Estimation coûts

| Poste | Estimation mensuelle |
|-------|---------------------|
| GitHub Actions | Gratuit (2000 min/mois) |
| Gemini Flash API | ~$1-5 (selon volume) |
| Notion | Gratuit |
| Telegram Bot | Gratuit |
| **Total** | **< $10/mois** |

---

## 6. User Stories MVP

### US-01 : Collecte automatique
> En tant qu'utilisateur, je veux que les AAP soient collectés automatiquement chaque jour, pour ne pas avoir à visiter chaque site manuellement.

**Critères d'acceptation :**
- [ ] Cron quotidien 6h00
- [ ] Sources P0 et P1 couvertes
- [ ] Logs d'exécution accessibles

### US-02 : Consultation centralisée
> En tant qu'utilisateur, je veux consulter tous les AAP dans une interface unique avec filtres (thème, deadline, périmètre).

**Critères d'acceptation :**
- [ ] Base Notion/Airtable accessible
- [ ] Filtres par thème, date limite, source
- [ ] Tri par date de publication ou deadline

### US-03 : Alertes nouveaux AAP
> En tant qu'utilisateur, je veux recevoir une alerte (Telegram/email) quand un nouvel AAP correspond à mes thèmes d'intérêt.

**Critères d'acceptation :**
- [ ] Digest hebdo dimanche soir
- [ ] Alerte immédiate si deadline < 15 jours
- [ ] Filtrage par thème configurable

### US-04 : Pas de doublons
> En tant qu'utilisateur, je ne veux pas voir le même AAP plusieurs fois s'il apparaît sur plusieurs sources.

**Critères d'acceptation :**
- [ ] Déduplication par fingerprint
- [ ] Merge des sources si doublon

---

## 7. Roadmap

### Phase 0 : POC (1-2 jours)
- [ ] Scraper Carenews (1 source)
- [ ] Extraction LLM → JSON
- [ ] Stockage Notion
- [ ] Alerte Telegram manuelle

### Phase 1 : MVP (1-2 semaines)
- [ ] Ajouter sources P0/P1 (IDF API, Paris.fr, RSS)
- [ ] Cron GitHub Actions
- [ ] Déduplication
- [ ] Digest hebdo automatique

### Phase 2 : Consolidation (1 mois)
- [ ] Auditer sources V2
- [ ] UI de configuration (thèmes, alertes)
- [ ] Métriques (nb AAP/semaine, sources actives)

### Phase 3 : Expansion (optionnel)
- [ ] Ouvrir à d'autres assos (multi-tenant?)
- [ ] Scraping fondations privées (si faisable)
- [ ] Matching intelligent asso/AAP

---

## 8. Décisions à prendre

| Question | Options | Recommandation |
|----------|---------|----------------|
| Storage | Notion vs Airtable vs Supabase | **Notion** (gratuit, UI prête) |
| Alertes | Telegram vs Email vs Slack | **Telegram** (temps réel, gratuit) |
| Orchestration | GitHub Actions vs n8n vs Make | **GitHub Actions** (gratuit, code-first) |
| Repo | Public vs Privé | À décider |
| Fréquence collecte | Quotidien vs Hebdo | **Quotidien** (coût négligeable) |

---

## 9. Risques identifiés

| Risque | Impact | Probabilité | Mitigation |
|--------|--------|-------------|------------|
| Site change sa structure HTML | Scraper casse | Moyenne | Tests de régression, alertes erreur |
| Anti-bot (Cloudflare, DataDome) | Source inaccessible | Faible (MVP) | Exclure source ou Playwright |
| Coût API LLM explose | Budget dépassé | Faible | Limites quotidiennes, cache |
| Données incomplètes | AAP mal parsés | Moyenne | Review manuelle, fallback |

---

## 10. Prochaines étapes

### Immédiat (cette semaine)

1. **Pauline** : Demander à sa responsable le temps passé/mois sur la veille AAP
2. **Walid** : Tester l'API IDF (déjà fait ✓)
3. **Younes + Walid** : Valider cette spec, choisir storage

### POC (1-2 jours)

```
Jour 1 : Scraper Carenews → JSON normalisé → Notion/Airtable
Jour 2 : GitHub Actions cron + Telegram alert
```

### Post-POC

- Ajouter les autres sources P0/P1
- Présenter le MVP à Pauline → feedback
- Si traction → explorer business model

---

## 11. Business Model (exploration)

### 11.1 Hypothèse de valeur

| Métrique | À valider |
|----------|-----------|
| Temps veille/mois (1 personne) | ? jours |
| Nb personnes qui font ça dans l'asso | ? |
| Nb d'assos en France | ~1.5M (dont ~150k employeuses) |
| Coût d'opportunité | Temps × salaire chargé |

### 11.2 Modèles possibles

| Modèle | Prix | Cible |
|--------|------|-------|
| **Freemium** | 0€ / 10-30€/mois | Petites assos / Moyennes assos |
| **SaaS asso** | 50-100€/mois | Grosses assos, réseaux |
| **Place de marché** | Commission sur matching | Fondations + assos |
| **Open source + support** | 0€ + consulting | Dev + assos tech-savvy |

### 11.3 Concurrence

| Acteur | Positionnement | Limite |
|--------|---------------|--------|
| Carenews | Agrégateur généraliste | Pas d'alertes personnalisées, UX moyenne |
| Admical | Mécénat d'entreprise | Focus fondations, pas collectivités |
| ? | - | Marché fragmenté, pas de leader clair |

> 💡 **À creuser :** Pourquoi personne n'a cracké ce marché ? Barrières techniques ? Willingness to pay des assos ?

---

## Annexes

### A. URLs des sources MVP

```
# P0 - Priorité haute
https://www.carenews.com/appels_a_projets
https://data.iledefrance.fr/explore/dataset/aides-appels-a-projets/api/

# P1 - Priorité moyenne  
https://www.paris.fr/pages/repondre-a-un-appel-a-projets-5412
https://www.professionbanlieue.org/Appels-a-projets-Appel-a-manifestation-d-interet

# P2 - Priorité basse
https://idf.drieets.gouv.fr/Appel-a-projets
```

### B. Exemple prompt LLM extraction

```
Tu es un extracteur de données structurées. 
Analyse ce contenu HTML d'un appel à projets et retourne un JSON avec :
- titre (string)
- organisme (string)  
- date_publication (YYYY-MM-DD ou null)
- date_limite (YYYY-MM-DD ou null)
- themes (array de strings parmi: insertion-emploi, education-jeunesse, 
  sante-handicap, culture-sport, environnement-transition, 
  solidarite-inclusion, vie-associative, numerique, autre)
- perimetre_geo (string: "Paris", "IDF", "93", "National"...)
- resume (string, max 300 caractères)
- url_candidature (string ou null)

Réponds UNIQUEMENT avec le JSON, sans commentaire.

Contenu à analyser :
---
{HTML_CONTENT}
---
```

### C. Contacts

- **Younes Ajeddig** : [email] 
- **Walid Becherif** : [email]
- **Pauline** : [à compléter]