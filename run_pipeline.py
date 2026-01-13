import argparse
import asyncio
import logging

from appels_a_projets.connectors.carenews import CarenewsConnector
from appels_a_projets.connectors.iledefrance_opendata import IleDeFranceConnector
from appels_a_projets.connectors.paris import ParisConnector
from appels_a_projets.connectors.ssd_ressources import SSDRessourcesConnector

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NOTE: Ce script "run_pipeline.py" à la racine est un ancien pipeline async.
# Le pipeline recommandé est scripts/run_pipeline.py.
# On garde néanmoins ce fichier fonctionnel avec les connecteurs présents dans le repo.

active_connectors = [
    # CarenewsConnector(),  # Optionnel
    IleDeFranceConnector(),
    ParisConnector(),
    SSDRessourcesConnector(),
]


async def process_batch(items, llm_processor, force: bool = False):
    enriched_items = []
    for item in items:
        try:
            enriched = await llm_processor.enrich(item, force=force)
            if enriched:
                enriched_items.append(enriched)
        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement de {getattr(item, 'titre', 'item')}: {e}")
    return enriched_items


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Force le réenrichissement de tous les enregistrements")
    parser.add_argument("--destination", default="notion", choices=["notion", "airtable"], help="Destination de sauvegarde")
    args = parser.parse_args()

    # 1. Collecte
    all_raw_items = []
    for connector in active_connectors:
        logger.info(f"🔵 Lancement du connecteur : {connector.source_name}")
        try:
            raw = connector.fetch_raw()
            items = connector.parse(raw)
            logger.info(f"✅ {len(items)} items trouvés via {connector.source_name}")
            all_raw_items.extend(items)
        except Exception as e:
            logger.error(f"❌ Erreur sur le connecteur {connector.source_name}: {e}")

    logger.info(f"📊 Total items collectés (brut) : {len(all_raw_items)}")

    # 2. Enrichissement (LLM)
    try:
        from appels_a_projets.processing.enrichment import LLMProcessor

        logger.info("🧠 Démarrage de l'enrichissement LLM...")
        llm_processor = LLMProcessor()
        final_aaps = await process_batch(all_raw_items, llm_processor, force=args.force)
        logger.info(f"✨ Total items enrichis et valides : {len(final_aaps)}")
    except ModuleNotFoundError:
        logger.warning("LLMProcessor introuvable (processing/enrichment). Skip enrich.")
        final_aaps = all_raw_items

    # 3. Sauvegarde
    if args.destination == "notion":
        try:
            from appels_a_projets.storage.notion import NotionStorage

            logger.info("Sauvegarde vers Notion...")
            storage = NotionStorage()
            await storage.save_batch(final_aaps)
            logger.info("🚀 Sauvegarde terminée !")
        except ModuleNotFoundError:
            logger.warning("NotionStorage introuvable (storage/notion). Utilise scripts/push_to_notion.py à la place.")
    else:
        logger.warning(f"Destination {args.destination} non implémentée.")


if __name__ == "__main__":
    asyncio.run(main())