#!/usr/bin/env python3
"""
Export des AAPs vers CSV pour import Airtable.

Usage:
    uv run python scripts/export_csv.py
    uv run python scripts/export_csv.py --output data/mon_export.csv
    uv run python scripts/export_csv.py --active-only
"""

import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export AAPs vers CSV")
    parser.add_argument("--output", "-o", default="data/aap_export.csv", help="Fichier de sortie")
    parser.add_argument("--active-only", action="store_true", help="Exporter uniquement les AAPs actifs")
    args = parser.parse_args()
    
    # Import ici pour éviter le temps de chargement si --help
    from appels_a_projets.connectors.carenews import CarenewsConnector
    from appels_a_projets.connectors.iledefrance_opendata import IleDeFranceConnector
    from appels_a_projets.processing.normalizer import normalize_all
    
    print("📥 Chargement des données...")
    
    # Charger les sources
    carenews = CarenewsConnector()
    idf = IleDeFranceConnector()
    
    print("   • Carenews...", end=" ", flush=True)
    collection = normalize_all(
        carenews.run(), 
        "Carenews", 
        "https://www.carenews.com/appels_a_projets"
    )
    print(f"✓ {len(collection)} AAPs")
    
    print("   • IDF OpenData...", end=" ", flush=True)
    idf_collection = normalize_all(
        idf.run(), 
        "Région Île-de-France", 
        "https://data.iledefrance.fr"
    )
    collection.merge(idf_collection)
    print(f"✓ {len(idf_collection)} AAPs")
    
    print(f"\n📊 Total: {len(collection)} AAPs")
    
    # Filtrer si demandé
    if args.active_only:
        collection = collection.filter_active()
        print(f"📊 Actifs: {len(collection)} AAPs")
    
    # Trier par urgence
    collection = collection.sort_by_urgence()
    
    # Créer le dossier si nécessaire
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Champs à exporter
    fields = [
        "titre", 
        "url_source", 
        "source_id", 
        "source_name", 
        "organisme",
        "date_publication", 
        "date_limite", 
        "categories", 
        "tags", 
        "eligibilite",
        "perimetre_niveau", 
        "perimetre_geo", 
        "montant_min", 
        "montant_max",
        "resume", 
        "url_candidature", 
        "email_contact",
        "fingerprint", 
        "statut", 
        "urgence", 
        "is_active", 
        "days_remaining"
    ]
    
    # Export
    print(f"\n📤 Export vers {output_path}...")
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        
        for aap in collection:
            row = aap.to_dict_for_export()
            
            # Convertir les listes en strings séparées par virgule
            for key in ["categories", "tags", "eligibilite", "public_cible_detail"]:
                if key in row and isinstance(row[key], list):
                    row[key] = ", ".join(str(x) for x in row[key]) if row[key] else ""
            
            # Filtrer aux champs voulus
            row = {k: row.get(k, "") for k in fields}
            writer.writerow(row)
    
    print(f"✅ {len(collection)} AAPs exportés!")
    print(f"\n💡 Pour importer dans Airtable:")
    print(f"   1. Va sur airtable.com → ta base")
    print(f"   2. Clique '+' → Add table → Import CSV")
    print(f"   3. Sélectionne {output_path}")
    print(f"   4. Ajuste les types de champs si nécessaire")


if __name__ == "__main__":
    main()
