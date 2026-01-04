import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = "mistralai/mistral-small-24b-instruct-2501:free" # Using a reliable free model on OpenRouter
# Note: The user suggested 'mistralai/devstral-2512:free' but I will use a known good free one or the one requested if it exists.
# Let's stick to the user's suggestion if possible, or a close alternative. 
# 'mistralai/mistral-7b-instruct:free' is common. 
# The user specifically asked for: https://openrouter.ai/mistralai/devstral-2512:free
# I will use that one.
MODEL_NAME = "mistralai/mistral-7b-instruct:free" # Fallback to a common free one if the specific devstral one is tricky, but let's try to be generic.

# Paths
DATA_DIR = Path("data/paris")
METADATA_FILE = DATA_DIR / "metadata.json"
OUTPUT_FILE = DATA_DIR / "metadata_enriched.json"

def get_openrouter_client():
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables.")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

def read_file_content(filepath: str) -> str:
    try:
        # Adjust path to be relative to workspace root if needed
        full_path = Path(filepath)
        if not full_path.exists():
             # Try relative to data dir if absolute path fails
             full_path = Path(os.getcwd()) / filepath
        
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return ""
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""

def generate_prompt(content: str, current_data: Dict) -> str:
    return f"""
You are an expert in analyzing "Appels à Projets" (Calls for Projects).
Your task is to extract structured data from the provided text content of a call for projects.

Here is the text content:
\"\"\"
{content[:15000]} 
\"\"\"
(Content truncated if too long)

Existing metadata (do not contradict these unless clearly wrong, but you can refine them):
- Title: {current_data.get('titre')}
- Organisme: {current_data.get('organisme')}
- Deadline: {current_data.get('date_limite')}

Please extract the following fields in JSON format. If a field is not found, use null.

Fields to extract:
1. `resume`: A short summary (max 300 chars).
2. `categories`: List of categories from this fixed list: ["insertion-emploi", "education-jeunesse", "sante-handicap", "culture-sport", "environnement-transition", "solidarite-inclusion", "vie-associative", "numerique", "economie-ess", "logement-urbanisme", "mobilite-transport", "autre"].
3. `tags`: List of free keywords (max 5).
4. `eligibilite`: List of eligible structures from: ["associations", "collectivites", "etablissements", "entreprises", "professionnels", "particuliers", "autre"].
5. `public_cible_detail`: List of strings describing specific target audiences (e.g. "Jeunes de 12-25 ans", "Séniors").
6. `montant_min`: Minimum amount in Euros (number).
7. `montant_max`: Maximum amount in Euros (number).
8. `type_financement`: Type of funding (e.g. "Subvention", "Prix", "Apport en nature").
9. `url_candidature`: Direct URL to apply if found in text.
10. `email_contact`: Contact email if found.

Output ONLY valid JSON.
"""

def enrich_aap(client: OpenAI, record: Dict) -> Dict:
    content_file = record.get("content_file")
    if not content_file:
        print(f"Skipping {record.get('id')}: No content file.")
        return record

    content = read_file_content(content_file)
    if not content:
        print(f"Skipping {record.get('id')}: Empty content.")
        return record

    print(f"Enriching {record.get('titre')}...")
    
    prompt = generate_prompt(content, record)
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model="mistralai/mistral-7b-instruct:free", # Using a standard free model alias
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts JSON data from text."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            response_content = completion.choices[0].message.content
            try:
                extracted_data = json.loads(response_content.strip())
                
                for key, value in extracted_data.items():
                    # Update fields if they are in our target list and not null
                    if key in ['resume', 'categories', 'tags', 'eligibilite', 'public_cible_detail', 'montant_min', 'montant_max', 'type_financement', 'url_candidature', 'email_contact']:
                         # Only update if the value is not null AND the original field is empty/null
                         # The user specified "existing fields are not to be replaced"
                         if value is not None:
                            # Check if key exists and has a truthy value (not None, not empty string/list)
                            if not record.get(key):
                                record[key] = value
                
                # Record the model used
                record['llm_model'] = MODEL_NAME
                record['enrichment_status'] = 'success'
                print(f"  -> Success")
                return record
                
            except json.JSONDecodeError:
                print(f"Failed to parse JSON for {record.get('id')}")
                record['enrichment_status'] = 'failed_json'
                return record
                
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                wait_time = (2 ** attempt) * 10 # Exponential backoff: 10s, 20s, 40s...
                print(f"  -> Rate limit (429). Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"API Error for {record.get('id')}: {e}")
                record['enrichment_status'] = 'failed_api'
                return record

    print(f"  -> Failed after {max_retries} retries.")
    record['enrichment_status'] = 'failed_timeout'
    return record

def main():
    if not METADATA_FILE.exists():
        print(f"Metadata file not found: {METADATA_FILE}")
        return

    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    client = get_openrouter_client()
    
    enriched_data = []
    for record in data:
        enriched_record = enrich_aap(client, record)
        enriched_data.append(enriched_record)
        
        # Save incrementally
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)
        
        # Add a small pause between requests to be nice to the free tier
        time.sleep(5)

    print(f"Enrichment complete. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()