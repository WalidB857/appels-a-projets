"""
Normalizer - Convert RawAAP to normalized AAP.

This module handles the conversion from connector-specific RawAAP
to the canonical AAP format.

Responsibilities:
- Date parsing from various formats
- Category mapping to taxonomy
- Eligibility type inference from public_cible
- Geographic scope normalization
"""

from datetime import date, datetime
import re

from appels_a_projets.connectors.base import RawAAP
from appels_a_projets.models.aap import (
    AAP, 
    AAPCollection,
    Category, 
    EligibiliteType,
    Perimetre,
    Source,
    StatutAAP,
)


# =============================================================================
# DATE PARSING
# =============================================================================

def parse_date(date_str: str | None) -> date | None:
    """
    Parse date string to date object.
    Supports multiple formats.
    """
    if not date_str:
        return None
    
    formats = [
        "%Y-%m-%d",       # 2025-12-24
        "%d/%m/%Y",       # 24/12/2025
        "%d-%m-%Y",       # 24-12-2025
        "%Y/%m/%d",       # 2025/12/24
        "%d %B %Y",       # 24 décembre 2025
        "%d %b %Y",       # 24 déc 2025
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    
    return None


# =============================================================================
# CATEGORY MAPPING
# =============================================================================

# Mapping de mots-clés vers catégories
CATEGORY_KEYWORDS = {
    Category.INSERTION_EMPLOI: [
        "emploi", "insertion", "travail", "recrutement", "formation professionnelle",
        "chômage", "réinsertion", "apprentissage"
    ],
    Category.EDUCATION_JEUNESSE: [
        "education", "éducation", "jeunesse", "jeune", "scolaire", "étudiant",
        "lycée", "collège", "université", "enfance", "périscolaire"
    ],
    Category.SANTE_HANDICAP: [
        "santé", "sante", "handicap", "médical", "hôpital", "prévention",
        "maladie", "soin", "thérapie", "pmr", "accessibilité"
    ],
    Category.CULTURE_SPORT: [
        "culture", "culturel", "art", "musique", "théâtre", "sport", "sportif",
        "musée", "patrimoine", "spectacle", "danse", "cinéma"
    ],
    Category.ENVIRONNEMENT_TRANSITION: [
        "environnement", "écologie", "transition", "climat", "énergie",
        "développement durable", "biodiversité", "recyclage", "vert"
    ],
    Category.SOLIDARITE_INCLUSION: [
        "solidarité", "solidarite", "inclusion", "social", "précarité",
        "pauvreté", "aide", "accompagnement", "égalité", "diversité"
    ],
    Category.VIE_ASSOCIATIVE: [
        "associatif", "association", "bénévolat", "volontariat", "engagement",
        "citoyen", "citoyenneté"
    ],
    Category.NUMERIQUE: [
        "numérique", "numerique", "digital", "innovation", "tech", "data",
        "informatique", "startup", "ia", "intelligence artificielle"
    ],
    Category.ECONOMIE_ESS: [
        "ess", "économie sociale", "esus", "coopérative", "scop", "scic",
        "économie solidaire", "impact"
    ],
    Category.LOGEMENT_URBANISME: [
        "logement", "habitat", "urbanisme", "ville", "quartier", "rénovation",
        "hlm", "hébergement"
    ],
    Category.MOBILITE_TRANSPORT: [
        "mobilité", "transport", "déplacement", "vélo", "voiture", "train",
        "route", "circulation"
    ],
}


def infer_categories(text: str, existing_categories: list[str] = None) -> list[Category]:
    """
    Infère les catégories à partir du texte et des catégories existantes.
    """
    result = []
    
    # D'abord, essayer de mapper les catégories existantes
    if existing_categories:
        for cat_str in existing_categories:
            try:
                result.append(Category(cat_str))
            except ValueError:
                # Pas une catégorie valide, on va l'inférer
                pass
    
    # Si on a déjà des catégories, pas besoin d'inférer
    if result:
        return result[:3]  # Max 3 catégories
    
    # Sinon, inférer depuis le texte
    text_lower = text.lower()
    scores = {}
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score
    
    # Trier par score décroissant
    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = [cat for cat, score in sorted_cats[:3]]
    
    return result


# =============================================================================
# ELIGIBILITY MAPPING
# =============================================================================

ELIGIBILITY_KEYWORDS = {
    EligibiliteType.ASSOCIATIONS: [
        "association", "loi 1901", "fondation", "ong", "asso"
    ],
    EligibiliteType.COLLECTIVITES: [
        "collectivité", "commune", "mairie", "département", "région",
        "epci", "intercommunalité", "métropole"
    ],
    EligibiliteType.ETABLISSEMENTS: [
        "établissement", "école", "université", "hôpital", "laboratoire",
        "enseignement", "recherche", "formation"
    ],
    EligibiliteType.ENTREPRISES: [
        "entreprise", "société", "pme", "tpe", "startup", "esus",
        "entreprise sociale", "sarl", "sas"
    ],
    EligibiliteType.PROFESSIONNELS: [
        "professionnel", "indépendant", "artisan", "commerçant", "créateur",
        "freelance", "autoentrepreneur"
    ],
    EligibiliteType.PARTICULIERS: [
        "particulier", "individu", "citoyen", "étudiant", "demandeur",
        "jeune", "senior", "personne"
    ],
}


def infer_eligibility(public_cible: list[str]) -> list[EligibiliteType]:
    """
    Infère les types d'éligibilité depuis les public_cible bruts.
    """
    if not public_cible:
        return []
    
    text = " ".join(public_cible).lower()
    result = set()
    
    for elig_type, keywords in ELIGIBILITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            result.add(elig_type)
    
    return list(result)


# =============================================================================
# GEOGRAPHIC SCOPE
# =============================================================================

def infer_perimetre_niveau(perimetre_geo: str | None) -> Perimetre | None:
    """
    Infère le niveau de périmètre depuis la zone géographique.
    """
    if not perimetre_geo:
        return None
    
    geo_lower = perimetre_geo.lower()
    
    # National / France
    if any(kw in geo_lower for kw in ["france", "national", "métropole"]):
        return Perimetre.NATIONAL
    
    # Européen
    if any(kw in geo_lower for kw in ["europe", "européen", "ue", "union européenne"]):
        return Perimetre.EUROPEEN
    
    # International
    if any(kw in geo_lower for kw in ["international", "mondial", "monde"]):
        return Perimetre.INTERNATIONAL
    
    # Régional (noms de régions françaises)
    regions = [
        "île-de-france", "ile-de-france", "idf", "auvergne", "bretagne",
        "normandie", "occitanie", "paca", "grand est", "hauts-de-france",
        "nouvelle-aquitaine", "pays de la loire", "bourgogne", "centre"
    ]
    if any(r in geo_lower for r in regions):
        return Perimetre.REGIONAL
    
    # Départemental (numéros ou noms de départements)
    if re.search(r'\b(75|77|78|91|92|93|94|95)\b', geo_lower):
        return Perimetre.DEPARTEMENTAL
    deps = ["seine", "hauts-de-seine", "val-de-marne", "essonne", "yvelines"]
    if any(d in geo_lower for d in deps):
        return Perimetre.DEPARTEMENTAL
    
    # Local (villes, arrondissements)
    if any(kw in geo_lower for kw in ["paris", "arrondissement", "commune", "ville"]):
        return Perimetre.LOCAL
    
    return None


# =============================================================================
# MAIN CONVERSION
# =============================================================================

def raw_to_aap(raw: RawAAP, source_name: str, source_url: str) -> AAP:
    """
    Convertit un RawAAP en AAP normalisé.
    
    Args:
        raw: RawAAP object from a connector
        source_name: Human-readable name of the source
        source_url: URL of the source listing page
    
    Returns:
        Normalized AAP object
    """
    source = Source(
        id=raw.source_id,
        name=source_name,
        url=source_url,
        fetched_at=raw.scraped_at,
    )
    
    # Texte pour l'inférence
    text_for_inference = f"{raw.titre} {raw.resume or ''} {raw.description or ''}"
    
    # Inférer les catégories
    categories = infer_categories(text_for_inference, raw.categories)
    
    # Inférer l'éligibilité
    eligibilite = infer_eligibility(raw.public_cible)
    
    # Inférer le niveau de périmètre
    perimetre_niveau = infer_perimetre_niveau(raw.perimetre_geo)
    
    # Déterminer le statut
    date_limite = parse_date(raw.date_limite)
    if date_limite:
        if date_limite < date.today():
            statut = StatutAAP.FERME
        else:
            statut = StatutAAP.OUVERT
    else:
        statut = StatutAAP.PERMANENT  # Pas de deadline = permanent
    
    return AAP(
        titre=raw.titre,
        url_source=raw.url_source,
        source=source,
        # Dates
        date_publication=parse_date(raw.date_publication),
        date_limite=date_limite,
        # Organisme
        organisme=raw.organisme or "Non spécifié",
        organisme_url=raw.organisme_url,
        # Classification
        categories=categories,
        tags=raw.tags,
        # Éligibilité
        eligibilite=eligibilite,
        public_cible_detail=raw.public_cible,
        # Géographie
        perimetre_niveau=perimetre_niveau,
        perimetre_geo=raw.perimetre_geo,
        # Financement
        montant_min=raw.montant_min,
        montant_max=raw.montant_max,
        # Contenu
        resume=raw.resume or "",
        description=raw.description,
        # Contact
        url_candidature=raw.url_candidature,
        email_contact=raw.email_contact,
        # Statut
        statut=statut,
    )


def normalize_all(
    raw_aaps: list[RawAAP],
    source_name: str,
    source_url: str,
) -> AAPCollection:
    """
    Convertit une liste de RawAAPs en collection normalisée.
    
    Args:
        raw_aaps: List of RawAAP objects
        source_name: Human-readable name of the source
        source_url: URL of the source listing page
    
    Returns:
        AAPCollection with normalized AAPs
    """
    aaps = [raw_to_aap(raw, source_name, source_url) for raw in raw_aaps]
    
    collection = AAPCollection(
        aaps=aaps,
        total=len(aaps),
        sources=[raw_aaps[0].source_id] if raw_aaps else [],
    )
    
    # Dédupliquer au cas où
    collection.deduplicate()
    
    return collection
