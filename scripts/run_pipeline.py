#!/usr/bin/env python
"""
Pipeline complet : Fetch → Enrich → Push to Airtable
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

# Liste des sources à traiter
SOURCES = ['carenews', 'iledefrance', 'paris', 'ssd']

def run_command(command, description, cwd=None):
    """Exécute une commande avec affichage du statut"""
    print(f"\n{'='*70}")
    print(f"🚀 {description}")
    print(f"{'='*70}")
    try:
        result = subprocess.run(
            command,
            check=True,
            shell=True,
            cwd=cwd,
            capture_output=False,
            text=True
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
    parser.add_argument("--skip-push", action="store_true", help="Ignorer l'étape de push vers Airtable")
    
    args = parser.parse_args()
    
    # Vérifier qu'on est à la racine du projet
    if not Path("appels_a_projets").exists():
        print("❌ Veuillez exécuter ce script depuis la racine du projet.")
        return

    print("\n" + "="*70)
    print("🎯 PIPELINE COMPLET AAP-WATCH")
    print("="*70)
    print("Étapes :")
    if not args.skip_fetch:
        print("  1️⃣  Fetch des données (4 sources)")
    if not args.skip_enrich:
        print("  2️⃣  Enrichissement LLM" + (" (MODE FORCE)" if args.force else ""))
    if not args.skip_push:
        print("  3️⃣  Push vers Airtable")
    print("="*70)

    # =========================================================================
    # ÉTAPE 1 : FETCH DES DONNÉES
    # =========================================================================
    fetch_results = {}
    
    if not args.skip_fetch:
        print("\n\n" + "="*70)
        print("📦 ÉTAPE 1/3 : FETCH DES DONNÉES")
        print("="*70)
        
        # Carenews
        fetch_results['carenews'] = run_command(
            f"{sys.executable} -m appels_a_projets.connectors.carenews",
            "Fetch Carenews"
        )
        time.sleep(2)  # Pause entre les sources
        
        # Île-de-France OpenData
        fetch_results['iledefrance'] = run_command(
            f"{sys.executable} -m appels_a_projets.connectors.iledefrance_opendata",
            "Fetch Île-de-France OpenData"
        )
        time.sleep(2)
        
        # Paris
        fetch_results['paris'] = run_command(
            f"{sys.executable} -m appels_a_projets.connectors.paris",
            "Fetch Paris.fr"
        )
        time.sleep(2)
        
        # Seine-Saint-Denis
        fetch_results['ssd'] = run_command(
            f"{sys.executable} -m appels_a_projets.connectors.ssd",
            "Fetch Préfecture 93"
        )
        
        # Résumé du fetch
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
        # Assume all sources exist if skipping fetch
        for source in SOURCES:
            fetch_results[source] = True

    # =========================================================================
    # ÉTAPE 2 : ENRICHISSEMENT LLM
    # =========================================================================
    enrich_results = {}
    
    if not args.skip_enrich:
        print("\n\n" + "="*70)
        print("🧠 ÉTAPE 2/3 : ENRICHISSEMENT LLM")
        if args.force:
            print("⚡ MODE FORCE ACTIVÉ : Réenrichissement de TOUS les enregistrements")
        print("="*70)
        
        for source in SOURCES:
            # Ne traiter que les sources qui ont été fetchées avec succès
            if not fetch_results.get(source, False):
                print(f"⏭️  Ignoré : {source} (fetch échoué)")
                enrich_results[source] = False
                continue
                
            # Vérifier que le fichier metadata.json existe
            metadata_file = Path("data") / source / "metadata.json"
            if not metadata_file.exists():
                print(f"⏭️  Ignoré : {source} (pas de metadata.json)")
                enrich_results[source] = False
                continue
            
            # Construire la commande avec --force si demandé
            force_flag = " --force" if args.force else ""
            enrich_results[source] = run_command(
                f"{sys.executable} scripts/enrich_dataset.py {source}{force_flag}",
                f"Enrichissement LLM : {source}" + (" (FORCE)" if args.force else "")
            )
            time.sleep(2)  # Pause entre les sources
        
        # Résumé de l'enrichissement
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
    # ÉTAPE 3 : PUSH VERS AIRTABLE
    # =========================================================================
    push_success = False
    
    if not args.skip_push:
        print("\n\n" + "="*70)
        print("☁️  ÉTAPE 3/3 : PUSH VERS AIRTABLE")
        print("="*70)
        
        push_success = run_command(
            f"{sys.executable} scripts/push_to_airtable.py",
            "Push vers Airtable"
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
        print(f"☁️  Push Airtable : {'✅ Succès' if push_success else '❌ Échec'}")
    print("="*70)
    
    if push_success or args.skip_push:
        print("\n🎉 Pipeline terminé avec succès !")
    else:
        print("\n⚠️  Pipeline terminé avec des erreurs.")

if __name__ == "__main__":
    main()
