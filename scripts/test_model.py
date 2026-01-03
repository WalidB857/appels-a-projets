#!/usr/bin/env python3
"""
Test du nouveau modèle de données AAP.
"""

from appels_a_projets.connectors.carenews import CarenewsConnector
from appels_a_projets.connectors.iledefrance_opendata import IleDeFranceConnector
from appels_a_projets.processing.normalizer import normalize_all
from appels_a_projets.models.aap import Category, EligibiliteType


def main():
    print("=" * 80)
    print("🧪 TEST DU MODÈLE DE DONNÉES AAP")
    print("=" * 80)
    
    # Charger les données
    print("\n📥 Chargement des données...")
    
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
    
    print(f"✅ {len(collection)} AAPs chargés")
    
    # Stats
    print("\n" + "=" * 80)
    print("📊 STATISTIQUES")
    print("=" * 80)
    
    stats = collection.stats()
    print(f"\nTotal: {stats['total']}")
    print(f"Actifs: {stats['actifs']}")
    print(f"Expirés: {stats['expires']}")
    
    print("\nPar urgence:")
    for urg, count in sorted(stats['by_urgence'].items(), key=lambda x: -x[1]):
        print(f"  - {urg}: {count}")
    
    print("\nPar catégorie (top 5):")
    for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1])[:5]:
        print(f"  - {cat}: {count}")
    
    print("\nPar éligibilité:")
    for elig, count in sorted(stats['by_eligibilite'].items(), key=lambda x: -x[1]):
        print(f"  - {elig}: {count}")
    
    # Filtres
    print("\n" + "=" * 80)
    print("🎯 DÉMO DES FILTRES")
    print("=" * 80)
    
    actifs = collection.filter_active()
    print(f"\n✅ AAPs actifs: {len(actifs)}")
    
    urgents = collection.filter_by_urgence("urgent", "proche")
    print(f"⏰ AAPs urgents (< 30j): {len(urgents)}")
    
    assos = actifs.filter_by_eligibilite(EligibiliteType.ASSOCIATIONS)
    print(f"🏛️ AAPs pour associations: {len(assos)}")
    
    solidarite = actifs.filter_by_category(Category.SOLIDARITE_INCLUSION)
    print(f"🤝 AAPs solidarité: {len(solidarite)}")
    
    # Top 5
    print("\n" + "=" * 80)
    print("📋 TOP 5 AAPs URGENTS")
    print("=" * 80)
    
    top5 = actifs.sort_by_urgence()[:5]
    for i, aap in enumerate(top5, 1):
        print(f"\n{i}. {aap.titre[:65]}...")
        print(f"   📅 Deadline: {aap.date_limite} ({aap.urgence})")
        print(f"   🏢 {aap.organisme}")
        print(f"   🏷️ {[c.value for c in aap.categories]}")
    
    # Export test
    print("\n" + "=" * 80)
    print("📤 TEST EXPORT")
    print("=" * 80)
    
    # Export dict
    aap = actifs[0]
    export = aap.to_dict_for_export()
    print(f"\nExemple export dict:")
    for k in ['titre', 'source_id', 'categories', 'eligibilite', 'urgence', 'fingerprint']:
        print(f"  {k}: {export.get(k)}")


if __name__ == "__main__":
    main()
