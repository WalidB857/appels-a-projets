"""
Script pour créer une base de données Notion AAP-Watch avec toutes les propriétés.
Utilise l'API Notion (septembre 2024).
"""
import os
from notion_client import Client
from dotenv import load_dotenv
import time

load_dotenv()

def create_aap_database():
    """Crée une base de données Notion pour AAP-Watch avec toutes les propriétés"""
    
    notion = Client(auth=os.getenv("NOTION_TOKEN"))
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    
    if not parent_page_id:
        print("❌ Erreur : NOTION_PARENT_PAGE_ID manquant dans .env")
        print("👉 Créez une page Notion, ouvrez-la dans le navigateur")
        print("   L'URL ressemble à : https://notion.so/xxxxx")
        print("   Le xxxxx est votre NOTION_PARENT_PAGE_ID")
        return None
    
    print("🏗️ Création de la base de données Notion AAP-Watch...")
    
    # Définition des propriétés en une seule structure
    # Important : "title" doit être la première propriété
    properties = {
        "titre": {"title": {}},
        "organisme": {"rich_text": {}},
        "resume": {"rich_text": {}},
        "date_publication": {"date": {}},
        "date_limite": {"date": {}},
        "categories": {
            "multi_select": {
                "options": [
                    {"name": "insertion-emploi", "color": "blue"},
                    {"name": "education-jeunesse", "color": "green"},
                    {"name": "sante-handicap", "color": "red"},
                    {"name": "culture-sport", "color": "purple"},
                    {"name": "environnement-transition", "color": "yellow"},
                    {"name": "solidarite-inclusion", "color": "orange"},
                    {"name": "vie-associative", "color": "pink"},
                    {"name": "numerique", "color": "gray"},
                    {"name": "economie-ess", "color": "brown"},
                    {"name": "logement-urbanisme", "color": "default"},
                    {"name": "mobilite-transport", "color": "blue"},
                    {"name": "autre", "color": "gray"},
                ]
            }
        },
        "tags": {"multi_select": {"options": []}},
        "perimetre_geo": {"rich_text": {}},
        "public_cible": {
            "multi_select": {
                "options": [
                    {"name": "Associations", "color": "blue"},
                    {"name": "Jeunes", "color": "green"},
                    {"name": "Femmes", "color": "pink"},
                    {"name": "Séniors", "color": "orange"},
                ]
            }
        },
        "public_cible_detail": {"multi_select": {"options": []}},
        "eligibilite": {
            "multi_select": {
                "options": [
                    {"name": "associations", "color": "blue"},
                    {"name": "collectivites", "color": "green"},
                    {"name": "etablissements", "color": "purple"},
                    {"name": "entreprises", "color": "orange"},
                ]
            }
        },
        "montant_min": {"number": {"format": "euro"}},
        "montant_max": {"number": {"format": "euro"}},
        "type_financement": {
            "select": {
                "options": [
                    {"name": "Subvention", "color": "blue"},
                    {"name": "Prix", "color": "green"},
                    {"name": "Apport en nature", "color": "orange"},
                ]
            }
        },
        "url_source": {"url": {}},
        "url_candidature": {"url": {}},
        "email_contact": {"email": {}},
        "source_id": {
            "select": {
                "options": [
                    {"name": "carenews", "color": "blue"},
                    {"name": "iledefrance", "color": "green"},
                    {"name": "paris", "color": "red"},
                    {"name": "ssd", "color": "orange"},
                ]
            }
        },
        "enrichment_status": {
            "select": {
                "options": [
                    {"name": "success", "color": "green"},
                    {"name": "failed", "color": "red"},
                    {"name": "pending", "color": "yellow"},
                ]
            }
        },
    }
    
    try:
        # Étape 1 : Créer la base avec seulement le titre (propriété minimale)
        print("📝 Étape 1/2 : Création de la base...")
        new_database = notion.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "AAP-Watch 🎯"}}],
            properties={"titre": {"title": {}}},  # Seulement la propriété titre
            is_inline=False,
        )
        
        database_id = new_database["id"]
        print(f"✅ Base créée : {database_id}")
        
        # Attendre un peu pour que Notion synchronise
        print("⏳ Attente de 2 secondes...")
        time.sleep(2)
        
        # Étape 2 : Ajouter toutes les autres propriétés
        print("📝 Étape 2/2 : Ajout des propriétés...")
        
        # Retirer "titre" qui existe déjà
        properties_to_add = {k: v for k, v in properties.items() if k != "titre"}
        
        notion.databases.update(
            database_id=database_id,
            properties=properties_to_add
        )
        
        print(f"✅ {len(properties_to_add)} propriétés ajoutées")
        
        # Attendre la synchronisation finale
        print("⏳ Attente de 3 secondes pour synchronisation finale...")
        time.sleep(3)
        
        # Vérifier que les propriétés sont bien là
        db = notion.databases.retrieve(database_id=database_id)
        final_props = db.get("properties", {})
        
        print(f"")
        print(f"✅ Base de données AAP-Watch créée avec succès !")
        print(f"")
        print(f"📊 Database ID : {database_id}")
        print(f"🔗 URL : https://notion.so/{database_id.replace('-', '')}")
        print(f"📦 Propriétés créées : {len(final_props)}")
        print(f"")
        print(f"🔧 Mettez à jour votre .env :")
        print(f"NOTION_DATABASE_ID={database_id}")
        print(f"")
        print(f"✅ Vous pouvez maintenant lancer : python scripts/push_to_notion.py")
        
        return database_id
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        print(f"")
        print(f"💡 Vérifications :")
        print(f"   1. NOTION_TOKEN commence par 'ntn_' ou 'secret_'")
        print(f"   2. NOTION_PARENT_PAGE_ID est correct")
        print(f"   3. L'intégration a accès à la page parent")
        print(f"      → Ouvrir la page dans Notion")
        print(f"      → Menu '...' → Connections → Ajouter votre intégration")
        print(f"")
        print(f"🔗 Documentation : https://developers.notion.com/reference/create-a-database")
        return None

if __name__ == "__main__":
    create_aap_database()
