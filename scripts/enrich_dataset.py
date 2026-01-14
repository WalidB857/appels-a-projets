import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Modèle par défaut : Mistral Small 3.1 (gratuit, performant, bon pour l'extraction structurée)
DEFAULT_MODEL = "mistralai/mistral-small-3.1-24b-instruct:free"

# Liste de modèles de repli à essayer en ordre si le premier échoue
# STRICTEMENT basée sur la liste fournie avec la mention (free)
FALLBACK_MODELS = [
    "google/gemini-2.0-flash-exp:free",          # Gemini 2.0 Flash Experimental
    "meta-llama/llama-3.3-70b-instruct:free",       # Llama 3.3 70B
    "nvidia/nemotron-3-nano-30b-a3b:free",          # Nvidia Nemotron 30B
    "google/gemma-3-27b-it:free",                   # Gemma 3 27B
    "deepseek/deepseek-r1-0528:free",               # DeepSeek R1 (Excellent raisonnement)
    "nousresearch/hermes-3-llama-3.1-405b:free",    # Hermes 3 405B
    "qwen/qwen-2.5-vl-7b-instruct:free",            # Qwen 2.5 VL
    "meta-llama/llama-3.1-405b-instruct:free",      # Llama 3.1 405B
    "mistralai/mistral-7b-instruct:free",           # Mistral 7B
    "allenai/olmo-3.1-32b-think:free",              # Olmo 3.1 (Thinking model)
]

# Liste de tags autorisés (50 tags les plus pertinents et différenciants)
ALLOWED_TAGS = [
    "ESS", "prix", "innovation sociale", "2026",
    "précarité", "santé mentale", "exclusion sociale", "recherche", "populations fragiles",
    "démocratie", "citoyenneté", "projets citoyens",
    "TND", "enfants", "trouble du neurodéveloppement", "appel à projet", "santé",
    "incubateur", "projets solidaires", "concours", "carenews",
    "appel à projets", "financement", "solidarité", "Caisse d'Epargne",
    "entrepreneuriat", "innovation", "talents",
    "intégration", "vulnérables", "inclusion",
    "culture", "bibliothèque", "communauté",
    "QPV", "Paris&Co",
    "développement durable",
    "numérique", "accompagnement", "Antropia ESSEC",
    "transition écologique", "Fondation SUEZ",
    "violences faites aux enfants", "Fonds AXA",
    "aidants", "soutien",
    "Data For Good",
    "humanitaire", "aide internationale",
    "femmes", "détresse",
    "hébergement", "pauvreté",
    # Tags enrichis (Insertion, emploi, égalité, bien-être)
    "recherche d'emploi", "chômage", "bien-être", "confiance en soi",
    "compétences psychosociales", "égalité femmes-hommes", "mixité",
    "mentorat", "formation", "insertion professionnelle", "soft skills",
    "empowerment", "lien social", "entrepreneuriat féminin", "QPV", "quartiers prioritaires",
    # Enrichissement supplémentaire (parcours, résilience, égalité)
    "estime de soi", "résilience", "entraide", "coopération",
    "lutte contre les discriminations", "égalité des chances", "diversité",
    "inclusion numérique", "retour à l'emploi", "entrepreneuriat social",
    "équilibre vie pro-perso", "parentalité",
    # Enrichissement supplémentaire (Focus: Insertion, Mieux-être, Égalité)
    "insertion par l'activité économique", "IAE", "chantier d'insertion",
    "entreprise d'insertion", "accompagnement vers l'emploi", "savoir-être",
    "image de soi", "gestion du stress", "bienveillance", "proactivité", "mise en mouvement",
    "ateliers collaboratifs", "développement de potentiel", "dynamique de groupe",
    "égalité professionnelle", "mixité des métiers", "lutte contre les stéréotypes",
    "place des femmes", "leadership féminin", "droits des femmes", "parité",
    "emploi des jeunes", "emploi des seniors", "reconversion professionnelle",
    "bilan de compétences", "santé au travail", "tiers-lieux", "coworking solidaire"
]

def get_openrouter_client():
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables.")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

def read_file_content(filepath: str) -> str:
    try:
        path = Path(filepath)
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # Afficher des stats sur le contenu lu
            print(f"   📄 Lecture du fichier: {path.name}")
            print(f"      - Taille: {len(content)} caractères")
            print(f"      - Lignes: {content.count(chr(10))} lignes")
            # Afficher un aperçu du début du contenu
            preview = content[:200].replace('\n', ' ')
            print(f"      - Aperçu: {preview}...")
            return content
        else:
            print(f"   ⚠️ Fichier introuvable: {filepath}")
        return ""
    except Exception as e:
        print(f"   ❌ Error reading {filepath}: {e}")
        return ""

def generate_prompt(content: str, current_data: Dict) -> str:
    tags_str = ", ".join(ALLOWED_TAGS)
    return f"""
You are an expert in analyzing "Appels à Projets" (Calls for Projects) for non-profit organizations.
Your task is to extract structured data from the provided text content.

Here is the text content:
\"\"\"
{content[:20000]} 
\"\"\"
(Content truncated if too long)

Existing metadata (context):
- Title: {current_data.get('titre')}
- Organisme: {current_data.get('organisme')}

Please extract the following fields in JSON format. If a field is not found or not applicable, use null.

Fields to extract:
1. `resume`: A concise summary in French (max 400 chars). Focus on the goal.
2. `categories`: List of categories from this fixed list: ["insertion-emploi", "education-jeunesse", "sante-handicap", "culture-sport", "environnement-transition", "solidarite-inclusion", "vie-associative", "numerique", "economie-ess", "logement-urbanisme", "mobilite-transport", "autre"].
3. `tags`: List of relevant keywords (max 5) chosen STRICTLY from this list: [{tags_str}]. If no tag matches, return an empty list.
4. `eligibilite`: List of eligible structures from: ["associations", "collectivites", "etablissements", "entreprises", "professionnels", "particuliers", "autre"].
5. `public_cible`: List of strings describing the target audience (e.g. "Jeunes", "Femmes", "Séniors", "Habitants QPV"). This is distinct from eligibility.
6. `public_cible_detail`: List of strings describing specific target audiences with more details (e.g. "Jeunes de 12-25 ans", "Séniors isolés").
7. `montant_min`: Minimum amount in Euros (number, null if unknown).
8. `montant_max`: Maximum amount in Euros (number, null if unknown).
9. `type_financement`: Type of funding (e.g. "Subvention", "Prix", "Apport en nature").
10. `url_candidature`: Direct URL to apply form if found in text.
11. `email_contact`: Contact email if found. MUST be a valid email format (e.g. "contact@example.com"). Ignore invalid formats.
12. `date_limite`: Deadline in YYYY-MM-DD format if found and clearer than existing.

Output ONLY valid JSON.
"""

def enrich_record(client: OpenAI, record: Dict, primary_model: str) -> Dict:
    # Skip if already enriched successfully (optional, useful for restarting)
    if record.get('enrichment_status') == 'success' and record.get('resume'):
        print(f"⏭️  Déjà enrichi: {record.get('titre')[:50]}")
        return record

    content_file = record.get("content_file")
    if not content_file:
        print(f"⏭️  Skipping {record.get('id')}: No content file.")
        return record

    print(f"\n{'='*70}")
    print(f"🧠 Enrichissement: {record.get('titre')[:60]}")
    print(f"{'='*70}")
    
    content = read_file_content(content_file)
    if not content:
        print(f"   ❌ Empty content for {record.get('id')}")
        return record
    
    # Afficher les métadonnées existantes
    print(f"   📋 Métadonnées existantes:")
    print(f"      - Organisme: {record.get('organisme', 'N/A')}")
    print(f"      - Date limite: {record.get('date_limite', 'N/A')}")
    print(f"      - Périmètre: {record.get('perimetre_geo', 'N/A')}")
    
    prompt = generate_prompt(content, record)
    print(f"   📤 Envoi du prompt au LLM ({len(prompt)} caractères)...")
    
    # Construit la liste des modèles à essayer : le modèle demandé + les fallbacks
    models_to_try = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    
    for model in models_to_try:
        try:
            # Petite pause préventive avant chaque appel
            time.sleep(1)
            print(f"   🤖 Essai avec modèle: {model}")
            
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts JSON data from text. You answer in JSON format only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            response_content = completion.choices[0].message.content
            print(f"   📥 Réponse reçue ({len(response_content)} caractères)")
            
            try:
                extracted_data = json.loads(response_content.strip())
                
                # Afficher les données extraites
                print(f"   ✨ Données extraites:")
                if extracted_data.get('resume'):
                    print(f"      - Résumé: {extracted_data['resume'][:100]}...")
                if extracted_data.get('categories'):
                    print(f"      - Catégories: {', '.join(extracted_data['categories'])}")
                if extracted_data.get('tags'):
                    print(f"      - Tags: {', '.join(extracted_data['tags'][:3])}...")
                if extracted_data.get('eligibilite'):
                    print(f"      - Éligibilité: {', '.join(extracted_data['eligibilite'])}")
                if extracted_data.get('public_cible'):
                    print(f"      - Public cible: {', '.join(extracted_data['public_cible'])}")
                if extracted_data.get('montant_max'):
                    print(f"      - Montant max: {extracted_data['montant_max']}€")
                
                # Update record with extracted data
                # We prioritize extracted data but keep existing if extraction returns null
                fields_to_update = [
                    'resume', 'categories', 'tags', 'eligibilite', 
                    'public_cible', 'public_cible_detail', 'montant_min', 'montant_max', 
                    'type_financement', 'url_candidature', 'email_contact'
                ]
                
                for key in fields_to_update:
                    if extracted_data.get(key) is not None:
                        # Special handling for lists to avoid duplicates if we were to merge
                        # Here we overwrite because LLM has full context
                        record[key] = extracted_data[key]
                
                # Special handling for date_limite: only update if we don't have one or LLM found one
                if not record.get('date_limite') and extracted_data.get('date_limite'):
                     record['date_limite'] = extracted_data['date_limite']

                record['llm_model'] = model
                record['enrichment_status'] = 'success'
                print(f"   ✅ Succès avec {model}")
                return record
                
            except json.JSONDecodeError:
                print(f"   ⚠️ JSON invalide reçu de {model}, essai du modèle suivant...")
                continue # Try next model
                
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(f"   ⚠️ Rate limit (429) sur {model}, passage au modèle suivant...")
                continue # Try next model immediately
            else:
                print(f"   ❌ Erreur API sur {model}: {e}")
                continue # Try next model

    print(f"   ❌ Échec après tous les modèles.")
    record['enrichment_status'] = 'failed_all_models'
    return record

def main():
    parser = argparse.ArgumentParser(description="Enrich AAP dataset with LLM.")
    parser.add_argument("source", help="Source name (folder name in data/, e.g. 'paris')")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Primary OpenRouter model to use")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of records to process (0 for all)")
    parser.add_argument("--force", action="store_true", help="Force re-enrichment of already enriched records")
    
    args = parser.parse_args()
    
    source_dir = Path("data") / args.source
    metadata_file = source_dir / "metadata.json"
    output_file = source_dir / "metadata_enriched.json"
    
    if not metadata_file.exists():
        print(f"❌ Erreur: Fichier metadata.json introuvable dans {metadata_file}")
        return

    print(f"📂 Chargement des données depuis {metadata_file}...")
    with open(metadata_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # If output file exists, load it to resume or update
    if output_file.exists() and not args.force:
        print(f"📂 Fichier enrichi existant trouvé: {output_file}")
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_enriched = json.load(f)
            # Create a map for quick lookup
            enriched_map = {item['id']: item for item in existing_enriched}
            
            # Merge: Use enriched version if available, else original
            merged_data = []
            for item in data:
                if item['id'] in enriched_map:
                    merged_data.append(enriched_map[item['id']])
                else:
                    merged_data.append(item)
            data = merged_data
    elif args.force:
        print(f"⚡ Mode FORCE activé : réenrichissement de tous les enregistrements")
    
    client = get_openrouter_client()
    
    processed_count = 0
    success_count = 0
    skip_count = 0
    fail_count = 0
    total_to_process = len(data) if args.limit == 0 else min(len(data), args.limit)
    
    print(f"\n{'='*70}")
    print(f"🚀 Démarrage de l'enrichissement")
    print(f"{'='*70}")
    print(f"📊 Source: {args.source}")
    print(f"📊 Total d'enregistrements: {len(data)}")
    print(f"📊 À traiter: {total_to_process}")
    print(f"🤖 Modèle principal: {args.model}")
    print(f"🔄 Modèles de secours: {len(FALLBACK_MODELS)} disponibles")
    if args.force:
        print(f"⚡ Mode FORCE : Réenrichissement forcé")
    print(f"{'='*70}\n")
    
    try:
        for i, record in enumerate(data):
            if args.limit > 0 and processed_count >= args.limit:
                break
            
            # Skip if already enriched (check status) UNLESS --force is used
            if not args.force and record.get('enrichment_status') == 'success':
                skip_count += 1
                if i == 0 or (i + 1) % 10 == 0:  # Log every 10 skips
                    print(f"⏭️  Déjà enrichi ({skip_count} ignorés) : {record.get('titre', 'N/A')[:50]}")
                continue

            result = enrich_record(client, record, args.model)
            
            if result.get('enrichment_status') == 'success':
                success_count += 1
            else:
                fail_count += 1
                
            processed_count += 1
            
            # Afficher la progression
            total_checked = i + 1
            progress = total_checked / len(data) * 100
            print(f"\n📈 Progression: {total_checked}/{len(data)} ({progress:.1f}%) | Traités: {processed_count} | Enrichis: {success_count} | Échecs: {fail_count} | Ignorés: {skip_count}")
            
            # Save incrementally every record (safer)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Rate limiting pause
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Interruption par l'utilisateur. Sauvegarde des progrès...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("💾 Progrès sauvegardé.")
        return

    print(f"\n{'='*70}")
    print(f"✅ ENRICHISSEMENT TERMINÉ")
    print(f"{'='*70}")
    print(f"📊 Statistiques finales:")
    print(f"   - Total vérifié: {len(data)}")
    print(f"   - Traités: {processed_count}")
    print(f"   - Succès: {success_count}")
    print(f"   - Échecs: {fail_count}")
    print(f"   - Déjà enrichis (ignorés): {skip_count}")
    if processed_count > 0:
        print(f"   - Taux de succès: {success_count/processed_count*100:.1f}%")
    print(f"💾 Sauvegardé dans: {output_file}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()