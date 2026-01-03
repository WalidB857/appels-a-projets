#!/usr/bin/env python3
"""
Script pour uploader des AAPs vers Airtable.

Airtable ne permet pas de créer des champs via API (sans Enterprise).
Ce script:
1. Exporte le schéma attendu pour création manuelle
2. Upload les données en filtrant les champs existants

Usage:
    uv run python scripts/setup_airtable.py --schema    # Affiche le schéma
    uv run python scripts/setup_airtable.py --upload    # Upload les AAPs
    uv run python scripts/setup_airtable.py --test      # Test connexion
"""

import argparse
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

# Schéma Airtable recommandé
AIRTABLE_SCHEMA = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    SCHÉMA AIRTABLE POUR AAP-WATCH                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  CHAMPS ESSENTIELS (créer en premier)                                       ║
║  ─────────────────────────────────────                                       ║
║  • titre              → Single line text (Primary field)                    ║
║  • url_source         → URL                                                 ║
║  • source_id          → Single line text                                    ║
║  • organisme          → Single line text                                    ║
║  • date_limite        → Date                                                ║
║  • resume             → Long text                                           ║
║                                                                              ║
║  CLASSIFICATION                                                              ║
║  ──────────────                                                              ║
║  • categories         → Multiple select                                     ║
║      Options: insertion-emploi, education-jeunesse, sante-handicap,         ║
║               culture-sport, environnement-transition, solidarite-inclusion,║
║               vie-associative, numerique, economie-ess, logement-urbanisme, ║
║               mobilite-transport, autre                                     ║
║                                                                              ║
║  • eligibilite        → Multiple select                                     ║
║      Options: associations, collectivites, etablissements, entreprises,     ║
║               professionnels, particuliers, autre                           ║
║                                                                              ║
║  • tags               → Multiple select (ou Long text)                      ║
║                                                                              ║
║  GÉOGRAPHIE                                                                  ║
║  ──────────                                                                  ║
║  • perimetre_niveau   → Single select                                       ║
║      Options: local, departemental, regional, national, europeen,           ║
║               international                                                 ║
║  • perimetre_geo      → Single line text                                    ║
║                                                                              ║
║  FINANCEMENT                                                                 ║
║  ──────────                                                                  ║
║  • montant_min        → Number (Integer)                                    ║
║  • montant_max        → Number (Integer)                                    ║
║  • taux_financement   → Number (Decimal, 0-100)                            ║
║  • type_financement   → Single select                                       ║
║                                                                              ║
║  DATES                                                                       ║
║  ─────                                                                       ║
║  • date_publication   → Date                                                ║
║  • date_limite        → Date                                                ║
║                                                                              ║
║  CONTACT                                                                     ║
║  ───────                                                                     ║
║  • url_candidature    → URL                                                 ║
║  • email_contact      → Email                                               ║
║                                                                              ║
║  MÉTADONNÉES (calculées)                                                    ║
║  ───────────────────────                                                     ║
║  • fingerprint        → Single line text                                    ║
║  • statut             → Single select (ouvert, ferme, permanent, inconnu)   ║
║  • urgence            → Single select (urgent, proche, confortable,         ║
║                                        permanent, expire)                   ║
║  • is_active          → Checkbox                                            ║
║  • days_remaining     → Number (Integer) - ou Formula depuis date_limite    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


def print_schema():
    """Affiche le schéma Airtable à créer."""
    print(AIRTABLE_SCHEMA)


def test_connection():
    """Test la connexion à Airtable."""
    from pyairtable import Api
    
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME")
    
    if not all([token, base_id, table_name]):
        print("❌ Variables d'environnement manquantes!")
        print("   Créer un fichier .env avec:")
        print("   AIRTABLE_TOKEN=pat...")
        print("   AIRTABLE_BASE_ID=app...")
        print("   AIRTABLE_TABLE_NAME=tbl... (ou nom de la table)")
        return False
    
    try:
        api = Api(token)
        table = api.table(base_id, table_name)
        records = table.all(max_records=1)
        
        print("✅ Connexion Airtable OK!")
        print(f"   Base: {base_id}")
        print(f"   Table: {table_name}")
        
        if records:
            print(f"\n📋 Champs existants dans la table:")
            for field in sorted(records[0]['fields'].keys()):
                print(f"   • {field}")
        else:
            print("\n📋 Table vide - prête pour l'import!")
        
        return True
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False


def get_existing_fields():
    """Récupère les champs existants dans Airtable."""
    from pyairtable import Api
    
    api = Api(os.environ["AIRTABLE_TOKEN"])
    table = api.table(os.environ["AIRTABLE_BASE_ID"], os.environ["AIRTABLE_TABLE_NAME"])
    
    records = table.all(max_records=1)
    if records:
        return set(records[0]['fields'].keys())
    return set()


def upload_aaps():
    """Upload les AAPs vers Airtable."""
    from pyairtable import Api
    
    from appels_a_projets.connectors.carenews import CarenewsConnector
    from appels_a_projets.connectors.iledefrance_opendata import IleDeFranceConnector
    from appels_a_projets.processing.normalizer import normalize_all
    
    print("📥 Chargement des AAPs...")
    
    # Collecter les données
    carenews = CarenewsConnector()
    idf = IleDeFranceConnector()
    
    collection = normalize_all(
        carenews.run(),
        "Carenews",
        "https://www.carenews.com/appels_a_projets"
    )
    collection.merge(normalize_all(
        idf.run(),
        "Région Île-de-France", 
        "https://data.iledefrance.fr"
    ))
    
    # Filtrer uniquement les actifs
    actifs = collection.filter_active()
    print(f"✅ {len(actifs)} AAPs actifs à uploader")
    
    # Récupérer les champs existants
    existing_fields = get_existing_fields()
    print(f"📋 Champs existants dans Airtable: {len(existing_fields)}")
    
    # Préparer les records
    records_to_upload = []
    for aap in actifs:
        record = aap.to_dict_for_export()
        
        # Convertir les listes en strings pour Airtable (si pas Multiple select)
        if 'categories' in record and isinstance(record['categories'], list):
            # Garder comme liste pour Multiple select
            pass
        if 'eligibilite' in record and isinstance(record['eligibilite'], list):
            pass
        if 'tags' in record and isinstance(record['tags'], list):
            pass
        
        # Filtrer les champs None
        record = {k: v for k, v in record.items() if v is not None and v != "" and v != []}
        
        # Si table existante, filtrer aux champs connus
        if existing_fields:
            record = {k: v for k, v in record.items() if k in existing_fields}
        
        records_to_upload.append({"fields": record})
    
    # Upload par batch
    api = Api(os.environ["AIRTABLE_TOKEN"])
    table = api.table(os.environ["AIRTABLE_BASE_ID"], os.environ["AIRTABLE_TABLE_NAME"])
    
    print(f"\n🚀 Upload de {len(records_to_upload)} records...")
    
    batch_size = 10
    uploaded = 0
    errors = 0
    
    for i in range(0, len(records_to_upload), batch_size):
        batch = records_to_upload[i:i+batch_size]
        try:
            table.batch_create(batch)
            uploaded += len(batch)
            print(f"   ✅ {uploaded}/{len(records_to_upload)}")
        except Exception as e:
            errors += len(batch)
            print(f"   ❌ Erreur batch {i//batch_size + 1}: {e}")
            # Essayer un par un pour identifier le problème
            for rec in batch:
                try:
                    table.create(rec["fields"])
                    uploaded += 1
                except Exception as e2:
                    print(f"      ❌ {rec['fields'].get('titre', 'N/A')[:40]}: {e2}")
    
    print(f"\n{'='*60}")
    print(f"📊 Résultat: {uploaded} uploadés, {errors} erreurs")


def main():
    parser = argparse.ArgumentParser(description="Setup Airtable pour AAP-Watch")
    parser.add_argument("--schema", action="store_true", help="Affiche le schéma à créer")
    parser.add_argument("--test", action="store_true", help="Test la connexion")
    parser.add_argument("--upload", action="store_true", help="Upload les AAPs")
    
    args = parser.parse_args()
    
    if args.schema:
        print_schema()
    elif args.test:
        test_connection()
    elif args.upload:
        if test_connection():
            print("\n" + "="*60 + "\n")
            upload_aaps()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
