#!/usr/bin/env python
"""
Pipeline complet : Fetch → Enrich → Push to Airtable/Notion

Extensions:
- Option --sources pour limiter le pipeline à une ou plusieurs sources (ex: ssd_ressources)
- Option --only-source (alias ergonomique) pour une seule source

Exemples:
- Scraper + enrichir + push Notion (sans vider la base) pour AppelAProjets:
  python scripts/run_pipeline.py --sources appelaprojets --destination notion --no-clear
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# Liste des sources à traiter
SOURCES = ['carenews', 'iledefrance', 'paris', 'ssd', 'ssd_ressources', 'professionbanlieue', 'appelaprojets']


def run_command(command, description, cwd=None):
    """Exécute une commande avec affichage du statut"""
    print(f"\n{'='*70}")
    print(f"🚀 {description}")
    print(f"{'='*70}")
    try:
        subprocess.run(
            command,
            check=True,
            shell=True,
            cwd=cwd,
            capture_output=False,
            text=True,
        )
        print(f"✅ {description} terminé avec succès.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} a échoué avec l'erreur : {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Pipeline complet AAP-Watch")
    parser.add_argument("--force", action="store_true", help="Force le réenrichissement de tous les enregistrements (même déjà enrichis)")
    parser.add_argument("--skip-fetch", action="store_true", help="Ignorer l'étape de fetch (utiliser les données existantes)")
    parser.add_argument("--skip-enrich", action="store_true", help="Ignorer l'étape d'enrichissement LLM")
    parser.add_argument("--skip-push", action="store_true", help="Ignorer l'étape de push vers Airtable/Notion")
    parser.add_argument("--destination", choices=["airtable", "notion"], default="airtable", help="Destination du push (airtable ou notion)")

    # Nouveau: limiter à une liste de sources
    parser.add_argument(
        "--sources",
        default=",".join(SOURCES),
        help=f"Liste de sources séparées par des virgules parmi: {', '.join(SOURCES)}. Exemple: --sources ssd_ressources",
    )

    # Nouveau: pour un push Notion non-destructif
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="(Notion) Ne pas vider/archiver la base avant push (ajout/upsert).",
    )

    # Nouveau: alias ergonomique pour une seule source
    parser.add_argument(
        "--only-source",
        default=None,
        help=f"Alias de --sources pour une seule source. Ex: --only-source appelaprojets. Options: {', '.join(SOURCES)}",
    )

    args = parser.parse_args()

    if args.only_source:
        args.sources = args.only_source

    selected_sources = [s.strip() for s in args.sources.split(',') if s.strip()]
    unknown = [s for s in selected_sources if s not in SOURCES]
    if unknown:
        print(f"❌ Sources inconnues: {unknown}. Connues: {SOURCES}")
        return

    # Vérifier qu'on est à la racine du projet
    if not Path("appels_a_projets").exists():
        print("❌ Veuillez exécuter ce script depuis la racine du projet.")
        return

    print("\n" + "="*70)
    print("🎯 PIPELINE COMPLET AAP-WATCH")
    print("="*70)
    print(f"Sources: {', '.join(selected_sources)}")
    print("Étapes :")
    if not args.skip_fetch:
        print("  1️⃣  Fetch des données")
    if not args.skip_enrich:
        print("  2️⃣  Enrichissement LLM" + (" (MODE FORCE)" if args.force else ""))
    if not args.skip_push:
        destination_name = "Airtable" if args.destination == "airtable" else "Notion"
        print(f"  3️⃣  Push vers {destination_name}")
    print("="*70)

    # =========================================================================
    # ÉTAPE 1 : FETCH DES DONNÉES
    # =========================================================================
    fetch_results: dict[str, bool] = {}

    if not args.skip_fetch:
        print("\n\n" + "="*70)
        print("📦 ÉTAPE 1/3 : FETCH DES DONNÉES")
        print("="*70)

        for source in selected_sources:
            cmd_by_source = {
                'carenews': f"{sys.executable} -m appels_a_projets.connectors.carenews",
                'iledefrance': f"{sys.executable} -m appels_a_projets.connectors.iledefrance_opendata",
                'paris': f"{sys.executable} -m appels_a_projets.connectors.paris",
                'ssd': f"{sys.executable} -m appels_a_projets.connectors.ssd",
                'ssd_ressources': f"{sys.executable} -m appels_a_projets.connectors.ssd_ressources",
                'professionbanlieue': f"{sys.executable} -m appels_a_projets.connectors.professionbanlieue",
                'appelaprojets': f"{sys.executable} -m appels_a_projets.connectors.appelaprojets",
            }
            fetch_results[source] = run_command(cmd_by_source[source], f"Fetch {source}")
            time.sleep(2)

        print("\n" + "="*70)
        print("📊 RÉSUMÉ DU FETCH")
        print("="*70)
        success_count = sum(1 for v in fetch_results.values() if v)
        for source, success in fetch_results.items():
            status = "✅" if success else "❌"
            print(f"  {status} {source}")
        print(f"\n  Total : {success_count}/{len(fetch_results)} sources récupérées")

        if success_count == 0:
            print("\n❌ Aucune source n'a pu être récupérée. Arrêt du pipeline.")
            return

    else:
        print("\n⏭️  Étape FETCH ignorée (--skip-fetch)")
        for source in selected_sources:
            fetch_results[source] = True

    # =========================================================================
    # ÉTAPE 2 : ENRICHISSEMENT LLM
    # =========================================================================
    enrich_results: dict[str, bool] = {}

    if not args.skip_enrich:
        print("\n\n" + "="*70)
        print("🧠 ÉTAPE 2/3 : ENRICHISSEMENT LLM")
        if args.force:
            print("⚡ MODE FORCE ACTIVÉ : Réenrichissement de TOUS les enregistrements")
        print("="*70)

        for source in selected_sources:
            if not fetch_results.get(source, False):
                print(f"⏭️  Ignoré : {source} (fetch échoué)")
                enrich_results[source] = False
                continue

            metadata_file = Path("data") / source / "metadata.json"
            if not metadata_file.exists():
                print(f"⏭️  Ignoré : {source} (pas de metadata.json)")
                enrich_results[source] = False
                continue

            force_flag = " --force" if args.force else ""
            enrich_results[source] = run_command(
                f"{sys.executable} scripts/enrich_dataset.py {source}{force_flag}",
                f"Enrichissement LLM : {source}" + (" (FORCE)" if args.force else ""),
            )
            time.sleep(2)

        print("\n" + "="*70)
        print("📊 RÉSUMÉ DE L'ENRICHISSEMENT")
        print("="*70)
        enrich_success_count = sum(1 for v in enrich_results.values() if v)
        for source, success in enrich_results.items():
            status = "✅" if success else "❌"
            print(f"  {status} {source}")
        print(f"\n  Total : {enrich_success_count}/{len(enrich_results)} sources enrichies")

    else:
        print("\n⏭️  Étape ENRICHISSEMENT ignorée (--skip-enrich)")
        enrich_success_count = 0

    # =========================================================================
    # ÉTAPE 3 : PUSH VERS AIRTABLE/NOTION
    # =========================================================================
    push_success = False

    if not args.skip_push:
        destination_name = "Airtable" if args.destination == "airtable" else "Notion"
        print("\n\n" + "="*70)
        print(f"☁️  ÉTAPE 3/3 : PUSH VERS {destination_name.upper()}")
        print("="*70)

        if args.destination == "airtable":
            push_success = run_command(
                f"{sys.executable} scripts/push_to_airtable.py",
                "Push vers Airtable",
            )
        else:
            no_clear_flag = " --no-clear" if args.no_clear else ""
            sources_flag = f" --sources {','.join(selected_sources)}"
            push_success = run_command(
                f"{sys.executable} scripts/push_to_notion.py{no_clear_flag}{sources_flag}",
                "Push vers Notion",
            )

    else:
        print("\n⏭️  Étape PUSH ignorée (--skip-push)")

    # =========================================================================
    # RÉSUMÉ FINAL
    # =========================================================================
    print("\n\n" + "="*70)
    print("🏁 RÉSUMÉ FINAL DU PIPELINE")
    print("="*70)
    if not args.skip_fetch:
        success_count = sum(1 for v in fetch_results.values() if v)
        print(f"📦 Fetch :         {success_count}/{len(fetch_results)} sources")
    if not args.skip_enrich:
        print(f"🧠 Enrichissement : {enrich_success_count}/{len(enrich_results)} sources" + (" (FORCE)" if args.force else ""))
    if not args.skip_push:
        destination_name = "Airtable" if args.destination == "airtable" else "Notion"
        print(f"☁️  Push {destination_name} : {'✅ Succès' if push_success else '❌ Échec'}")
    print("="*70)

    if push_success or args.skip_push:
        print("\n🎉 Pipeline terminé avec succès !")
    else:
        print("\n⚠️  Pipeline terminé avec des erreurs.")


if __name__ == "__main__":
    main()
