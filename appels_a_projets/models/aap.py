"""
AAP Data Models - Normalized schema for Appels à Projets.

This module defines the canonical data model for all AAPs, regardless of source.

Design Principles:
==================
1. SOURCE-AGNOSTIC: Le modèle doit pouvoir ingérer des AAP de n'importe quelle source
   (agrégateurs, APIs, institutionnels, fondations...)
   
2. RICH BUT FLEXIBLE: Champs riches quand disponibles, mais pas bloquants
   - Seuls `titre` et `url_source` sont vraiment requis
   - Tout le reste peut être enrichi progressivement (LLM, scraping détaillé)
   
3. ACTIONABLE: Focus sur ce qui aide l'utilisateur à AGIR
   - Filtrer par date limite (urgence)
   - Filtrer par éligibilité (public_cible)
   - Filtrer par thématique (categories)
   - Filtrer par géographie (perimetre_geo)
   
4. DEDUPABLE: Le fingerprint permet de détecter les doublons cross-sources

Sources analysées pour ce modèle:
- Carenews (HTML scraping) - 100+ AAPs, données légères
- IDF OpenData (API REST) - 343 AAPs, données riches
- À venir: Paris.fr, DRIEETS, fondations privées...
"""

from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator


# =============================================================================
# TAXONOMIES
# =============================================================================

class Category(str, Enum):
    """
    Taxonomie fixe des catégories thématiques.
    
    Basée sur l'analyse des sources:
    - IDF OpenData utilise ces catégories
    - Carenews sera mappé via LLM
    - Assez générique pour couvrir toutes les sources
    """
    INSERTION_EMPLOI = "insertion-emploi"
    EDUCATION_JEUNESSE = "education-jeunesse"
    SANTE_HANDICAP = "sante-handicap"
    CULTURE_SPORT = "culture-sport"
    ENVIRONNEMENT_TRANSITION = "environnement-transition"
    SOLIDARITE_INCLUSION = "solidarite-inclusion"
    VIE_ASSOCIATIVE = "vie-associative"
    NUMERIQUE = "numerique"
    ECONOMIE_ESS = "economie-ess"
    LOGEMENT_URBANISME = "logement-urbanisme"
    MOBILITE_TRANSPORT = "mobilite-transport"
    AUTRE = "autre"


class EligibiliteType(str, Enum):
    """
    Types d'organisations éligibles (taxonomie simplifiée).
    
    Objectif: Permettre un filtrage rapide "Est-ce que mon asso est éligible?"
    Mappé depuis les public_cible détaillés des sources.
    """
    ASSOCIATIONS = "associations"           # Loi 1901, fondations, ONG
    COLLECTIVITES = "collectivites"         # Communes, EPCI, départements, régions
    ETABLISSEMENTS = "etablissements"       # Écoles, universités, hôpitaux, labos
    ENTREPRISES = "entreprises"             # TPE, PME, ESS, ESUS
    PROFESSIONNELS = "professionnels"       # Indépendants, artisans, créateurs
    PARTICULIERS = "particuliers"           # Individus, étudiants, demandeurs d'emploi
    AUTRE = "autre"


class Perimetre(str, Enum):
    """
    Périmètre géographique (niveau).
    """
    LOCAL = "local"             # Commune, arrondissement
    DEPARTEMENTAL = "departemental"
    REGIONAL = "regional"
    NATIONAL = "national"
    EUROPEEN = "europeen"
    INTERNATIONAL = "international"


class StatutAAP(str, Enum):
    """
    Statut du cycle de vie d'un AAP.
    """
    OUVERT = "ouvert"
    FERME = "ferme"
    PERMANENT = "permanent"     # AAP sans date limite
    INCONNU = "inconnu"


# =============================================================================
# MODÈLES
# =============================================================================

class Source(BaseModel):
    """
    Métadonnées de la source d'un AAP.
    """
    id: str = Field(..., description="Identifiant source (ex: 'carenews', 'iledefrance_opendata')")
    name: str = Field(..., description="Nom lisible de la source")
    url: str = Field(..., description="URL où l'AAP a été trouvé")
    fetched_at: datetime = Field(default_factory=datetime.now, description="Date de collecte")


class AAP(BaseModel):
    """
    Modèle canonique d'un Appel à Projets.
    
    Ce modèle est conçu pour être:
    - SOURCE-AGNOSTIC: Accepte des données de qualité variable
    - ACTIONABLE: Focus sur les critères de décision des associations
    - DEDUPABLE: Fingerprint unique pour éviter les doublons
    
    Hiérarchie des champs:
    ----------------------
    CRITIQUES (obligatoires): titre, url_source
    IMPORTANTS (filtrage): date_limite, eligibilite, categories, perimetre
    UTILES (contexte): organisme, resume, montants, contact
    BONUS (enrichissement LLM): tags, description détaillée
    """
    
    # =========================================================================
    # IDENTITÉ
    # =========================================================================
    id: str = Field(
        default_factory=lambda: str(uuid4()), 
        description="UUID unique de l'AAP"
    )
    
    # =========================================================================
    # CHAMPS CRITIQUES (vraiment obligatoires)
    # =========================================================================
    titre: str = Field(
        ..., 
        min_length=1, 
        max_length=500, 
        description="Titre de l'AAP"
    )
    url_source: str = Field(
        ..., 
        description="URL originale de l'AAP (lien vers la page source)"
    )
    source: Source = Field(
        ..., 
        description="Métadonnées de la source"
    )
    
    # =========================================================================
    # DATES - Critères d'urgence
    # =========================================================================
    date_publication: date | None = Field(
        default=None, 
        description="Date de publication/ouverture"
    )
    date_limite: date | None = Field(
        default=None, 
        description="Date limite de candidature (None = permanent ou inconnu)"
    )
    date_debut: date | None = Field(
        default=None,
        description="Date de début du programme/financement"
    )
    date_fin: date | None = Field(
        default=None,
        description="Date de fin du programme/financement"
    )
    
    # =========================================================================
    # ORGANISME - Qui propose l'AAP?
    # =========================================================================
    organisme: str = Field(
        default="Non spécifié", 
        description="Organisme/structure proposant l'AAP"
    )
    organisme_type: str | None = Field(
        default=None,
        description="Type d'organisme (Fondation, Région, Ministère, etc.)"
    )
    organisme_url: str | None = Field(
        default=None, 
        description="Site web de l'organisme"
    )
    
    # =========================================================================
    # CLASSIFICATION THÉMATIQUE
    # =========================================================================
    categories: list[Category] = Field(
        default_factory=list,
        description="Catégories thématiques (taxonomie fixe, max 3)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags libres pour la recherche (LLM ou source)"
    )
    
    # =========================================================================
    # ÉLIGIBILITÉ - Qui peut candidater?
    # =========================================================================
    eligibilite: list[EligibiliteType] = Field(
        default_factory=list,
        description="Types de structures éligibles (taxonomie simplifiée)"
    )
    public_cible_detail: list[str] = Field(
        default_factory=list,
        description="Détail des publics cibles (texte brut de la source)"
    )
    criteres_eligibilite: str | None = Field(
        default=None,
        description="Critères d'éligibilité détaillés (texte libre)"
    )
    
    # =========================================================================
    # PÉRIMÈTRE GÉOGRAPHIQUE
    # =========================================================================
    perimetre_niveau: Perimetre | None = Field(
        default=None,
        description="Niveau géographique (local, régional, national...)"
    )
    perimetre_geo: str | None = Field(
        default=None,
        description="Zone géographique précise (ex: 'Île-de-France', 'Paris 18e')"
    )
    
    # =========================================================================
    # FINANCEMENT
    # =========================================================================
    montant_min: float | None = Field(
        default=None, 
        ge=0, 
        description="Montant minimum (€)"
    )
    montant_max: float | None = Field(
        default=None, 
        ge=0, 
        description="Montant maximum (€)"
    )
    taux_financement: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Taux de financement (%)"
    )
    type_financement: str | None = Field(
        default=None,
        description="Type: subvention, prêt, garantie, prix..."
    )
    
    # =========================================================================
    # CONTENU
    # =========================================================================
    resume: str = Field(
        default="",
        max_length=500,
        description="Résumé court (max 500 caractères)"
    )
    description: str | None = Field(
        default=None, 
        description="Description complète"
    )
    objectifs: str | None = Field(
        default=None,
        description="Objectifs de l'AAP"
    )
    modalites: str | None = Field(
        default=None,
        description="Modalités de participation/candidature"
    )
    
    # =========================================================================
    # CONTACT & CANDIDATURE
    # =========================================================================
    url_candidature: str | None = Field(
        default=None, 
        description="Lien direct pour candidater"
    )
    email_contact: str | None = Field(
        default=None, 
        description="Email de contact"
    )
    telephone_contact: str | None = Field(
        default=None,
        description="Téléphone de contact"
    )
    
    # =========================================================================
    # MÉTADONNÉES SYSTÈME
    # =========================================================================
    statut: StatutAAP = Field(
        default=StatutAAP.INCONNU,
        description="Statut calculé de l'AAP"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, 
        description="Date de création du record"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, 
        description="Dernière mise à jour"
    )
    
    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================
    
    @computed_field
    @property
    def fingerprint(self) -> str:
        """
        Empreinte unique pour déduplication cross-sources.
        Basé sur: titre normalisé + organisme + date_limite
        """
        # Normaliser le titre (lowercase, strip, remove accents basique)
        titre_norm = self.titre.lower().strip()
        org_norm = self.organisme.lower().strip()
        date_str = str(self.date_limite) if self.date_limite else "permanent"
        
        content = f"{titre_norm}|{org_norm}|{date_str}"
        return sha256(content.encode()).hexdigest()[:16]
    
    @computed_field
    @property
    def is_active(self) -> bool:
        """L'AAP est-il encore ouvert aux candidatures?"""
        if self.statut == StatutAAP.FERME:
            return False
        if self.statut == StatutAAP.PERMANENT:
            return True
        if not self.date_limite:
            return True  # Pas de deadline = considéré actif
        return self.date_limite >= date.today()
    
    @computed_field
    @property
    def days_remaining(self) -> int | None:
        """Jours restants avant la deadline."""
        if not self.date_limite:
            return None
        delta = self.date_limite - date.today()
        return max(0, delta.days)
    
    @computed_field
    @property
    def urgence(self) -> str:
        """
        Niveau d'urgence basé sur les jours restants.
        Utile pour prioriser l'affichage.
        """
        days = self.days_remaining
        if days is None:
            return "permanent"
        if days <= 0:
            return "expire"
        if days <= 7:
            return "urgent"
        if days <= 30:
            return "proche"
        return "confortable"
    
    # =========================================================================
    # VALIDATORS
    # =========================================================================
    
    @field_validator("categories", mode="before")
    @classmethod
    def validate_categories(cls, v):
        """Convertit les strings en Category enum."""
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        result = []
        for cat in v:
            if isinstance(cat, Category):
                result.append(cat)
            elif isinstance(cat, str):
                try:
                    result.append(Category(cat))
                except ValueError:
                    # Catégorie inconnue → on l'ignore (pas AUTRE automatiquement)
                    pass
        return result
    
    @field_validator("eligibilite", mode="before")
    @classmethod
    def validate_eligibilite(cls, v):
        """Convertit les strings en EligibiliteType enum."""
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        result = []
        for elig in v:
            if isinstance(elig, EligibiliteType):
                result.append(elig)
            elif isinstance(elig, str):
                try:
                    result.append(EligibiliteType(elig))
                except ValueError:
                    pass
        return result
    
    @field_validator("resume", mode="before")
    @classmethod
    def truncate_resume(cls, v):
        """Tronque le résumé à 500 caractères max."""
        if v and len(v) > 500:
            return v[:497] + "..."
        return v or ""
    
    @field_validator("statut", mode="before")
    @classmethod
    def compute_statut(cls, v, info):
        """Calcule le statut si non fourni."""
        if v and v != StatutAAP.INCONNU:
            return v
        # Le statut sera recalculé via is_active après création
        return StatutAAP.INCONNU
    
    # =========================================================================
    # MÉTHODES UTILITAIRES
    # =========================================================================
    
    def is_eligible_for(self, type_structure: EligibiliteType) -> bool:
        """Vérifie si un type de structure est éligible."""
        if not self.eligibilite:
            return True  # Pas de restriction = ouvert à tous
        return type_structure in self.eligibilite
    
    def matches_categories(self, categories: list[Category]) -> bool:
        """Vérifie si l'AAP correspond à au moins une catégorie."""
        if not categories:
            return True
        return bool(set(self.categories) & set(categories))
    
    def to_dict_for_export(self) -> dict:
        """
        Export vers dict pour Airtable/Notion/etc.
        Flatten les enums et computed fields.
        """
        return {
            "id": self.id,
            "titre": self.titre,
            "url_source": self.url_source,
            "source_id": self.source.id,
            "source_name": self.source.name,
            "organisme": self.organisme,
            "organisme_type": self.organisme_type,
            "date_publication": str(self.date_publication) if self.date_publication else None,
            "date_limite": str(self.date_limite) if self.date_limite else None,
            "categories": [c.value for c in self.categories],
            "tags": self.tags,
            "eligibilite": [e.value for e in self.eligibilite],
            "public_cible_detail": self.public_cible_detail,
            "perimetre_niveau": self.perimetre_niveau.value if self.perimetre_niveau else None,
            "perimetre_geo": self.perimetre_geo,
            "montant_min": self.montant_min,
            "montant_max": self.montant_max,
            "taux_financement": self.taux_financement,
            "type_financement": self.type_financement,
            "resume": self.resume,
            "url_candidature": self.url_candidature,
            "email_contact": self.email_contact,
            # Computed
            "fingerprint": self.fingerprint,
            "is_active": self.is_active,
            "days_remaining": self.days_remaining,
            "urgence": self.urgence,
            "statut": self.statut.value,
        }
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "titre": "Concours 2026 de La France s'engage",
                "url_source": "https://www.carenews.com/appels-a-projet/concours-2026",
                "source": {
                    "id": "carenews",
                    "name": "Carenews",
                    "url": "https://www.carenews.com/appels_a_projets"
                },
                "organisme": "Fondation La France s'engage",
                "date_publication": "2025-12-24",
                "date_limite": "2026-01-29",
                "categories": ["solidarite-inclusion", "vie-associative"],
                "eligibilite": ["associations"],
                "perimetre_niveau": "national",
                "perimetre_geo": "France",
                "montant_max": 300000,
                "resume": "Concours annuel sélectionnant 10-15 projets d'innovation sociale...",
            }
        }
    }


class AAPCollection(BaseModel):
    """
    Collection d'AAPs avec méthodes de filtrage et export.
    """
    aaps: list[AAP] = Field(default_factory=list)
    total: int = Field(default=0)
    fetched_at: datetime = Field(default_factory=datetime.now)
    sources: list[str] = Field(default_factory=list)
    
    def __len__(self) -> int:
        return len(self.aaps)
    
    def __iter__(self):
        return iter(self.aaps)
    
    def __getitem__(self, idx):
        return self.aaps[idx]
    
    # =========================================================================
    # AJOUT ET DÉDUPLICATION
    # =========================================================================
    
    def add(self, aap: AAP) -> bool:
        """
        Ajoute un AAP s'il n'est pas déjà présent (par fingerprint).
        Returns True si ajouté, False si doublon.
        """
        existing_fingerprints = {a.fingerprint for a in self.aaps}
        if aap.fingerprint in existing_fingerprints:
            return False
        self.aaps.append(aap)
        self.total = len(self.aaps)
        if aap.source.id not in self.sources:
            self.sources.append(aap.source.id)
        return True
    
    def merge(self, other: "AAPCollection") -> int:
        """
        Fusionne une autre collection, en dédupliquant.
        Returns le nombre d'AAPs ajoutés.
        """
        added = 0
        for aap in other.aaps:
            if self.add(aap):
                added += 1
        return added
    
    def deduplicate(self) -> int:
        """
        Supprime les doublons internes.
        Returns le nombre de doublons supprimés.
        """
        seen = set()
        unique = []
        for aap in self.aaps:
            if aap.fingerprint not in seen:
                seen.add(aap.fingerprint)
                unique.append(aap)
        removed = len(self.aaps) - len(unique)
        self.aaps = unique
        self.total = len(unique)
        return removed
    
    # =========================================================================
    # FILTRAGE
    # =========================================================================
    
    def filter_active(self) -> "AAPCollection":
        """Retourne uniquement les AAPs actifs (non expirés)."""
        return AAPCollection(
            aaps=[a for a in self.aaps if a.is_active],
            sources=self.sources.copy(),
        )
    
    def filter_by_category(self, *categories: Category) -> "AAPCollection":
        """Retourne les AAPs correspondant à au moins une catégorie."""
        cats = set(categories)
        return AAPCollection(
            aaps=[a for a in self.aaps if cats & set(a.categories)],
            sources=self.sources.copy(),
        )
    
    def filter_by_eligibilite(self, *types: EligibiliteType) -> "AAPCollection":
        """Retourne les AAPs où au moins un type est éligible."""
        types_set = set(types)
        return AAPCollection(
            aaps=[a for a in self.aaps if not a.eligibilite or (types_set & set(a.eligibilite))],
            sources=self.sources.copy(),
        )
    
    def filter_by_urgence(self, *niveaux: str) -> "AAPCollection":
        """Filtre par niveau d'urgence: 'urgent', 'proche', 'confortable', 'permanent', 'expire'."""
        return AAPCollection(
            aaps=[a for a in self.aaps if a.urgence in niveaux],
            sources=self.sources.copy(),
        )
    
    def filter_by_source(self, *source_ids: str) -> "AAPCollection":
        """Filtre par source."""
        return AAPCollection(
            aaps=[a for a in self.aaps if a.source.id in source_ids],
            sources=[s for s in self.sources if s in source_ids],
        )
    
    def filter_by_perimetre(self, niveau: Perimetre) -> "AAPCollection":
        """Filtre par niveau de périmètre géographique."""
        return AAPCollection(
            aaps=[a for a in self.aaps if a.perimetre_niveau == niveau],
            sources=self.sources.copy(),
        )
    
    def search(self, query: str) -> "AAPCollection":
        """
        Recherche textuelle simple dans titre, résumé, tags.
        """
        query_lower = query.lower()
        results = []
        for aap in self.aaps:
            searchable = f"{aap.titre} {aap.resume} {' '.join(aap.tags)}".lower()
            if query_lower in searchable:
                results.append(aap)
        return AAPCollection(aaps=results, sources=self.sources.copy())
    
    # =========================================================================
    # TRI
    # =========================================================================
    
    def sort_by_deadline(self, ascending: bool = True) -> "AAPCollection":
        """Trie par date limite (None à la fin)."""
        def sort_key(aap):
            if aap.date_limite is None:
                return date.max if ascending else date.min
            return aap.date_limite
        
        return AAPCollection(
            aaps=sorted(self.aaps, key=sort_key, reverse=not ascending),
            sources=self.sources.copy(),
        )
    
    def sort_by_urgence(self) -> "AAPCollection":
        """Trie par urgence (urgent en premier)."""
        priority = {"expire": 0, "urgent": 1, "proche": 2, "confortable": 3, "permanent": 4}
        return AAPCollection(
            aaps=sorted(self.aaps, key=lambda a: priority.get(a.urgence, 5)),
            sources=self.sources.copy(),
        )
    
    # =========================================================================
    # STATISTIQUES
    # =========================================================================
    
    def stats(self) -> dict:
        """Retourne des statistiques sur la collection."""
        by_category = {}
        by_urgence = {}
        by_source = {}
        by_eligibilite = {}
        
        for aap in self.aaps:
            # Catégories
            for cat in aap.categories:
                by_category[cat.value] = by_category.get(cat.value, 0) + 1
            
            # Urgence
            by_urgence[aap.urgence] = by_urgence.get(aap.urgence, 0) + 1
            
            # Source
            by_source[aap.source.id] = by_source.get(aap.source.id, 0) + 1
            
            # Éligibilité
            for elig in aap.eligibilite:
                by_eligibilite[elig.value] = by_eligibilite.get(elig.value, 0) + 1
        
        return {
            "total": len(self.aaps),
            "actifs": sum(1 for a in self.aaps if a.is_active),
            "expires": sum(1 for a in self.aaps if not a.is_active),
            "by_category": by_category,
            "by_urgence": by_urgence,
            "by_source": by_source,
            "by_eligibilite": by_eligibilite,
        }
    
    # =========================================================================
    # EXPORT
    # =========================================================================
    
    def to_dataframe(self):
        """Convertit en pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([a.to_dict_for_export() for a in self.aaps])
    
    def to_json(self, path: str | None = None) -> str:
        """Export JSON."""
        import json
        data = [a.to_dict_for_export() for a in self.aaps]
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        if path:
            with open(path, "w") as f:
                f.write(json_str)
        return json_str
    
    def to_csv(self, path: str):
        """Export CSV."""
        self.to_dataframe().to_csv(path, index=False)
