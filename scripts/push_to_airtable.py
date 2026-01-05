import json
import os
from pathlib import Path
import pandas as pd
from appels_a_projets.connectors.airtable_connector import AirtableConnector

SOURCES = ['carenews', 'iledefrance', 'paris', 'ssd']
DATA_DIR = Path("data")

def load_enriched_data():
    all_records = []
    for source in SOURCES:
        enriched_file = DATA_DIR / source / "metadata_enriched.json"
        raw_file = DATA_DIR / source / "metadata.json"
        
        # Priorité au fichier enrichi, sinon le brut
        file_to_load = enriched_file if enriched_file.exists() else raw_file
        
        if file_to_load.exists():
            print(f"📂 Chargement de {source} depuis {file_to_load}...")
            try:
                with open(file_to_load, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Nettoyage et normalisation basique
                    valid_records = []
                    for item in data:
                        # On ignore les items vides ou sans titre
                        if not item or not item.get('titre'):
                            continue
                            
                        # Ajout de la source si manquante
                        if 'source_id' not in item:
                            item['source_id'] = source
                            
                        valid_records.append(item)
                        
                    print(f"   -> {len(valid_records)} enregistrements trouvés.")
                    all_records.extend(valid_records)
            except Exception as e:
                print(f"   ❌ Erreur lors de la lecture de {file_to_load}: {e}")
        else:
            print(f"⚠️ Attention : Aucune donnée trouvée pour {source}")
            
    return pd.DataFrame(all_records)

def main():
    print("🔌 Initialisation du connecteur Airtable...")
    try:
        connector = AirtableConnector()
    except ValueError as e:
        print(f"❌ Erreur de configuration : {e}")
        print("Assurez-vous d'avoir défini AIRTABLE_TOKEN, AIRTABLE_BASE_ID et AIRTABLE_TABLE_NAME dans votre fichier .env")
        return

    # 🗑️ Vider la table Airtable avant d'envoyer les nouvelles données
    print("\n🗑️ Vidage de la table Airtable...")
    try:
        deleted_count = connector.clear_table()
        print(f"✅ {deleted_count} enregistrements supprimés.")
    except Exception as e:
        print(f"❌ Erreur lors du vidage : {e}")
        return

    print("\n📥 Récupération des données locales enrichies...")
    df = load_enriched_data()
    
    if df.empty:
        print("❌ Aucune donnée à envoyer.")
        return
        
    print(f"\n📊 Total : {len(df)} enregistrements à traiter.")
    
    # Filtrage des colonnes techniques à ne pas envoyer
    cols_to_exclude = ['content_file', 'llm_model', 'pdf_filename']
    df = df.drop(columns=[c for c in cols_to_exclude if c in df.columns], errors='ignore')
    print(f"🔧 Colonnes exclues : {', '.join(cols_to_exclude)}")
    
    # Filtrage optionnel : on peut vouloir ne pas envoyer les échecs d'enrichissement
    # Mais souvent on veut tout envoyer pour correction manuelle.
    # Ici on envoie tout ce qui a un titre.
    
    print(f"🚀 Envoi vers Airtable...")
    try:
        count = connector.upload_dataframe(df, auto_filter_fields=True)
        print(f"\n✅ Succès ! {count} enregistrements mis à jour/créés dans Airtable.")
    except Exception as e:
        print(f"\n❌ Erreur lors de l'envoi : {e}")

if __name__ == "__main__":
    main()