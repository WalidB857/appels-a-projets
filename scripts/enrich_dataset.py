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

# Modèle par défaut : Gemini 2.0 Flash (Très rapide, intelligent, contexte énorme)
DEFAULT_MODEL = "google/gemini-2.0-flash-exp:free"

# Liste de modèles de repli à essayer en ordre si le premier échoue
# STRICTEMENT basée sur la liste fournie avec la mention (free)
FALLBACK_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",       # Llama 3.3 70B
    "mistralai/mistral-small-3.1-24b-instruct:free", # Mistral Small 3.1
    "nvidia/nemotron-3-nano-30b-a3b:free",          # Nvidia Nemotron 30B
    "google/gemma-3-27b-it:free",                   # Gemma 3 27B
    "deepseek/deepseek-r1-0528:free",               # DeepSeek R1 (Excellent raisonnement)
    "nousresearch/hermes-3-llama-3.1-405b:free",    # Hermes 3 405B
    "qwen/qwen-2.5-vl-7b-instruct:free",            # Qwen 2.5 VL
    "meta-llama/llama-3.1-405b-instruct:free",      # Llama 3.1 405B
    "mistralai/mistral-7b-instruct:free",           # Mistral 7B
    "allenai/olmo-3.1-32b-think:free",              # Olmo 3.1 (Thinking model)
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
            return path.read_text(encoding="utf-8")
        return ""
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""

def generate_prompt(content: str, current_data: Dict) -> str:
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
3. `tags`: List of relevant keywords (max 5, in French).
4. `eligibilite`: List of eligible structures from: ["associations", "collectivites", "etablissements", "entreprises", "professionnels", "particuliers", "autre"].
5. `public_cible_detail`: List of strings describing specific target audiences (e.g. "Jeunes de 12-25 ans", "Séniors isolés").
6. `montant_min`: Minimum amount in Euros (number, null if unknown).
7. `montant_max`: Maximum amount in Euros (number, null if unknown).
8. `type_financement`: Type of funding (e.g. "Subvention", "Prix", "Apport en nature").
9. `url_candidature`: Direct URL to apply form if found in text.
10. `email_contact`: Contact email if found.
11. `date_limite`: Deadline in YYYY-MM-DD format if found and clearer than existing.

Output ONLY valid JSON.
"""

def enrich_record(client: OpenAI, record: Dict, primary_model: str) -> Dict:
    # Skip if already enriched successfully (optional, useful for restarting)
    if record.get('enrichment_status') == 'success' and record.get('resume'):
        return record

    content_file = record.get("content_file")
    if not content_file:
        print(f"Skipping {record.get('id')}: No content file.")
        return record

    content = read_file_content(content_file)
    if not content:
        print(f"Skipping {record.get('id')}: Empty content.")
        return record

    print(f"Enriching {record.get('titre')[:50]}...")
    
    prompt = generate_prompt(content, record)
    
    # Construit la liste des modèles à essayer : le modèle demandé + les fallbacks
    models_to_try = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    
    for model in models_to_try:
        try:
            # Petite pause préventive avant chaque appel
            time.sleep(1)
            print(f"  -> Trying model: {model}")
            
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts JSON data from text. You answer in JSON format only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            response_content = completion.choices[0].message.content
            try:
                extracted_data = json.loads(response_content.strip())
                
                # Update record with extracted data
                # We prioritize extracted data but keep existing if extraction returns null
                fields_to_update = [
                    'resume', 'categories', 'tags', 'eligibilite', 
                    'public_cible_detail', 'montant_min', 'montant_max', 
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
                print(f"  -> Success with {model}")
                return record
                
            except json.JSONDecodeError:
                print(f"  -> Failed to parse JSON from {model}. Trying next...")
                continue # Try next model
                
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(f"  -> Rate limit (429) on {model}. Switching to next model...")
                continue # Try next model immediately
            else:
                print(f"  -> API Error on {model}: {e}")
                continue # Try next model

    print(f"  -> Failed after trying all models.")
    record['enrichment_status'] = 'failed_all_models'
    return record

def main():
    parser = argparse.ArgumentParser(description="Enrich AAP dataset with LLM.")
    parser.add_argument("source", help="Source name (folder name in data/, e.g. 'paris')")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Primary OpenRouter model to use")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of records to process (0 for all)")
    
    args = parser.parse_args()
    
    source_dir = Path("data") / args.source
    metadata_file = source_dir / "metadata.json"
    output_file = source_dir / "metadata_enriched.json"
    
    if not metadata_file.exists():
        print(f"Error: Metadata file not found at {metadata_file}")
        return

    print(f"Loading data from {metadata_file}...")
    with open(metadata_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # If output file exists, load it to resume or update
    if output_file.exists():
        print(f"Found existing enriched file at {output_file}. Loading...")
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
    
    client = get_openrouter_client()
    
    processed_count = 0
    total_to_process = len(data) if args.limit == 0 else min(len(data), args.limit)
    
    print(f"Starting enrichment for {total_to_process} records...")
    print(f"Primary model: {args.model}")
    print(f"Fallback models: {len(FALLBACK_MODELS)} available")
    
    try:
        for i, record in enumerate(data):
            if args.limit > 0 and processed_count >= args.limit:
                break
            
            # Skip if already enriched (check status)
            if record.get('enrichment_status') == 'success':
                continue

            enrich_record(client, record, args.model)
            processed_count += 1
            
            # Save incrementally every record (safer)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Rate limiting pause
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Saving progress...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Saved.")
        return

    print(f"Enrichment complete. Saved to {output_file}")

if __name__ == "__main__":
    main()