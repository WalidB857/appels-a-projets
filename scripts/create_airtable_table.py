import json
import os
from pathlib import Path
import pandas as pd
from appels_a_projets.connectors.airtable_connector import AirtableConnector

SOURCES = ['carenews', 'iledefrance', 'paris', 'ssd']
DATA_DIR = Path("data")

def load_enriched_data():
    """Charge les données enrichies pour déduire le schéma"""
    all_records = []
    for source in SOURCES:
        enriched_file = DATA_DIR / source / "metadata_enriched.json"
        raw_file = DATA_DIR / source / "metadata.json"
        
        file_to_load = enriched_file if enriched_file.exists() else raw_file
        
        if file_to_load.exists():
            try:
                with open(file_to_load, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        if not item or not item.get('titre'): continue
                        if 'source_id' not in item: item['source_id'] = source
                        all_records.append(item)
            except Exception:
                pass
    return pd.DataFrame(all_records)

def main():
    print("🚀 Création d'une nouvelle table Airtable...")
    
    # 1. Charger les données pour analyser la structure
    print("📊 Analyse des données locales...")
    df = load_enriched_data()
    if df.empty:
        print("❌ Aucune donnée trouvée. Impossible de déduire le schéma.")
        return

    print(f"   -> {len(df)} enregistrements analysés.")
    print(f"   -> Colonnes détectées : {list(df.columns)}")

    # 2. Initialiser le connecteur
    try:
        connector = AirtableConnector()
    except ValueError as e:
        print(f"❌ Erreur config : {e}")
        return

    # 3. Créer la table
    table_name = "AAP_Enriched_V1"
    print(f"\n🛠️ Création de la table '{table_name}' dans la base {connector.base_id}...")
    
    try:
        table_id = connector.create_table(table_name, df_schema=df)
        
        print("\n" + "="*50)
        print(f"✅ SUCCÈS ! Table créée avec l'ID : {table_id}")
        print("="*50)
        print("\n👉 Action requise :")
        print("Mettez à jour votre fichier .env avec ce nouvel ID :")
        print(f"AIRTABLE_TABLE_NAME={table_id}")
        print("\nPuis relancez l'envoi des données :")
        print("uv run python scripts/push_to_airtable.py")
        
    except Exception as e:
        print(f"\n❌ Erreur lors de la création : {e}")

if __name__ == "__main__":
    main()