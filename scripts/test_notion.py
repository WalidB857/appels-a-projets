from notion_client import Client
import os
import json
from dotenv import load_dotenv

load_dotenv()

notion = Client(auth=os.getenv("NOTION_TOKEN"))

# Test : récupérer la base
database_id = os.getenv("NOTION_DATABASE_ID")

try:
    db = notion.databases.retrieve(database_id=database_id)
    
    print(f"✅ Connexion réussie !")
    print(f"📊 Base : {db.get('title', [{}])[0].get('plain_text', 'Sans titre')}")
    print(f"🆔 Database ID : {db.get('id')}")
    
    # Vérifier si des propriétés existent
    properties = db.get('properties', {})
    
    if properties:
        print(f"🔧 Propriétés ({len(properties)}) :")
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get('type', 'unknown')
            print(f"   - {prop_name} ({prop_type})")
    else:
        print("⚠️  Aucune propriété définie dans la base.")
        print("\n📝 Pour créer les colonnes nécessaires :")
        print("   1. Ouvre ta base Notion dans le navigateur")
        print("   2. Ajoute les colonnes selon le schéma AAP :")
        print("      - Titre (Title)")
        print("      - Organisme (Text)")
        print("      - Résumé (Text)")
        print("      - Date limite (Date)")
        print("      - Date publication (Date)")
        print("      - Catégories (Multi-select)")
        print("      - Tags (Multi-select)")
        print("      - Éligibilité (Multi-select)")
        print("      - Public cible (Multi-select)")
        print("      - Montant min (Number)")
        print("      - Montant max (Number)")
        print("      - Type financement (Select)")
        print("      - Périmètre géo (Text)")
        print("      - URL source (URL)")
        print("      - URL candidature (URL)")
        print("      - Email contact (Email)")
        print("      - Source (Select)")
        print("      - Statut enrichissement (Select)")
    
    # Debug: afficher la structure complète si besoin
    if os.getenv("DEBUG"):
        print("\n🔍 Structure complète de la base :")
        print(json.dumps(db, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"❌ Erreur : {e}")
    print(f"\n💡 Vérifications :")
    print(f"   - NOTION_TOKEN est défini : {'✅' if os.getenv('NOTION_TOKEN') else '❌'}")
    print(f"   - NOTION_DATABASE_ID est défini : {'✅' if os.getenv('NOTION_DATABASE_ID') else '❌'}")
    print(f"   - L'intégration est connectée à la base : Vérifie dans Notion (menu '...' → Connections)")