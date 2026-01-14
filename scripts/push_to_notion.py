import json
import os
from pathlib import Path

import pandas as pd

from appels_a_projets.connectors.notion_connector import NotionConnector

SOURCES = ['carenews', 'iledefrance', 'paris', 'ssd', 'ssd_ressources', 'professionbanlieue', 'appelaprojets']
DATA_DIR = Path("data")


def load_enriched_data(selected_sources: list[str]):
    all_records = []
    for source in selected_sources:
        enriched_file = DATA_DIR / source / "metadata_enriched.json"
        raw_file = DATA_DIR / source / "metadata.json"

        # Priorité au fichier enrichi, sinon le brut
        file_to_load = enriched_file if enriched_file.exists() else raw_file

        if file_to_load.exists():
            print(f"📂 Chargement de {source} depuis {file_to_load}...")
            try:
                with open(file_to_load, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    valid_records = []
                    for item in data:
                        if not item or not item.get('titre'):
                            continue

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
    import argparse

    parser = argparse.ArgumentParser(description="Push AAP dataset vers Notion")
    parser.add_argument(
        "--sources",
        default=",".join(SOURCES),
        help=f"Liste de sources séparées par des virgules parmi: {', '.join(SOURCES)}. Exemple: --sources ssd_ressources",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Ne pas vider/archiver la base Notion avant push (non-destructif).",
    )
    args = parser.parse_args()

    selected_sources = [s.strip() for s in args.sources.split(',') if s.strip()]
    unknown = [s for s in selected_sources if s not in SOURCES]
    if unknown:
        print(f"❌ Sources inconnues: {unknown}. Connues: {SOURCES}")
        return

    print("🔌 Initialisation du connecteur Notion...")
    try:
        connector = NotionConnector()
    except ValueError as e:
        print(f"❌ Erreur de configuration : {e}")
        print("Assurez-vous d'avoir défini NOTION_TOKEN et NOTION_DATABASE_ID dans votre fichier .env")
        return

    if not args.no_clear:
        print("\n🗑️ Vidage de la base Notion...")
        try:
            deleted_count = connector.clear_database()
            print(f"✅ {deleted_count} pages archivées.")
        except Exception as e:
            print(f"❌ Erreur lors du vidage : {e}")
            return
    else:
        print("\n➕ Mode non-destructif: on ne vide pas la base Notion (--no-clear)")

    print("\n📥 Récupération des données locales enrichies...")
    df = load_enriched_data(selected_sources)

    if df.empty:
        print("❌ Aucune donnée à envoyer.")
        return

    print(f"\n📊 Total : {len(df)} enregistrements à traiter.")

    cols_to_exclude = ['content_file', 'llm_model', 'pdf_filename']
    df = df.drop(columns=[c for c in cols_to_exclude if c in df.columns], errors='ignore')
    print(f"🔧 Colonnes exclues : {', '.join(cols_to_exclude)}")

    print(f"🚀 Envoi vers Notion...")
    try:
        count = connector.upload_dataframe(df)
        print(f"\n✅ Succès ! {count} enregistrements créés dans Notion.")
    except Exception as e:
        print(f"\n❌ Erreur lors de l'envoi : {e}")


if __name__ == "__main__":
    main()
