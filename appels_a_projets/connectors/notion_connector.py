import os
import requests
import pandas as pd
import numpy as np
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class NotionConnector:
    """Connector to send data to Notion Database using raw requests (no notion-client)"""
    
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("NOTION_TOKEN")
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        
        if not all([self.token, self.database_id]):
            raise ValueError("Missing Notion credentials in .env file. Required: NOTION_TOKEN, NOTION_DATABASE_ID")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        self.base_url = "https://api.notion.com/v1"

    def _get_database(self):
        """Fetch database metadata to get schema"""
        url = f"{self.base_url}/databases/{self.database_id}"
        r = requests.get(url, headers=self.headers)
        if r.status_code != 200:
            raise Exception(f"Error getting database: {r.text}")
        return r.json()
    
    def _get_title_property_name(self, db_json: dict) -> str:
        """Find the name of the title property"""
        props = db_json.get("properties", {})
        for name, meta in props.items():
            if meta.get("type") == "title":
                return name
        return "Name" # Fallback

    def create_missing_properties(self, df: pd.DataFrame, title_source_col: str = "titre") -> str:
        """
        Check schema and create missing properties via requests.PATCH.
        Returns the actual Title property name in Notion.
        """
        print("🔄 Vérification du schéma Notion (via api)...")
        
        try:
            db_json = self._get_database()
            existing_props = db_json.get("properties", {})
            title_prop_name = self._get_title_property_name(db_json)
            
            new_props = {}
            
            # Mapping definitions (Schema)
            type_mapping = {
                "date_limite": {"date": {}},
                "date_publication": {"date": {}},
                "montant_min": {"number": {"format": "euro"}},
                "montant_max": {"number": {"format": "euro"}},
                "url_source": {"url": {}},
                "url_candidature": {"url": {}},
                "email_contact": {"email": {}},
                "categories": {"multi_select": {"options": []}},
                "tags": {"multi_select": {"options": []}},
                "eligibilite": {"multi_select": {"options": []}},
                "public_cible": {"multi_select": {"options": []}},
                "public_cible_detail": {"multi_select": {"options": []}},
                "source_id": {"select": {"options": []}},
                "type_financement": {"select": {"options": []}},
                "enrichment_status": {"select": {"options": []}},
                "organisme": {"rich_text": {}},
                "resume": {"rich_text": {}},
                "perimetre_geo": {"rich_text": {}},
            }
            
            excluded_fields = {'content_file', 'llm_model', 'pdf_filename', 'id', 'id_record'}

            for col in df.columns:
                if col in excluded_fields or col == title_source_col:
                    continue
                
                # Check if property already exists (case sensitive usually, but good enough)
                if col in existing_props:
                    continue
                
                # Determine definition
                if col in type_mapping:
                    new_props[col] = type_mapping[col]
                else:
                    # Fallback auto-detection
                    if pd.api.types.is_numeric_dtype(df[col]):
                        new_props[col] = {"number": {"format": "number"}}
                    elif pd.api.types.is_bool_dtype(df[col]):
                        new_props[col] = {"checkbox": {}}
                    elif pd.api.types.is_datetime64_any_dtype(df[col]):
                       new_props[col] = {"date": {}}
                    else:
                        new_props[col] = {"rich_text": {}}

            if not new_props:
                print(f"✅ Schéma déjà à jour. Title property = '{title_prop_name}'")
                return title_prop_name

            print(f"🛠️ Ajout de {len(new_props)} propriétés: {list(new_props.keys())}")
            
            url = f"{self.base_url}/databases/{self.database_id}"
            payload = {"properties": new_props}
            
            r = requests.patch(url, headers=self.headers, json=payload)
            if r.status_code != 200:
                print(f"❌ Erreur patch schema: {r.text}")
            else:
                print("✅ Schéma mis à jour.")
                # Wait for propagation
                time.sleep(2)
            
            return title_prop_name
            
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du schéma: {e}")
            return "Name"

    def _format_property_value(self, value, prop_type: str):
        """Format a single value for Notion API payload"""
        # Fix: Check list/array first to avoid 'truth value ambiguous' error with pd.isna
        if isinstance(value, (list, tuple, np.ndarray)):
            if len(value) == 0:
                return None
        elif pd.isna(value) or value == "" or str(value).lower() == "nan":
            return None
            
        try:
            val_str = str(value)
            
            if prop_type == "title":
                return {"title": [{"text": {"content": val_str[:2000]}}]}
                
            if prop_type == "rich_text":
                return {"rich_text": [{"text": {"content": val_str[:2000]}}]}
                
            if prop_type == "number":
                return {"number": float(value)}
                
            if prop_type == "checkbox":
                return {"checkbox": bool(value)}
                
            if prop_type == "date":
                if isinstance(value, datetime):
                    return {"date": {"start": value.isoformat()}}
                return {"date": {"start": val_str}}
                
            if prop_type == "url":
                if val_str.strip():
                    return {"url": val_str[:2000]}
                return None
                
            if prop_type == "email":
                # Validation fix: email max length
                if len(val_str) > 100 or "@" not in val_str:
                    # Fallback or skip if invalid
                    return None 
                return {"email": val_str}
                
            if prop_type == "select":
                return {"select": {"name": val_str[:100].replace(",", " ")}}
                
            if prop_type == "multi_select":
                if isinstance(value, list):
                    options = [{"name": str(x)[:100].replace(",", " ")} for x in value if x]
                    return {"multi_select": options} if options else None
                return None
                
            # Default fallback
            return {"rich_text": [{"text": {"content": val_str[:2000]}}]}
            
        except Exception:
            return None

    def upload_dataframe(self, df: pd.DataFrame):
        """Upload dataframe rows as pages"""
        # 1. Update Schema
        title_prop_name = self.create_missing_properties(df)
        
        # 2. Get fresh schema for type mapping
        try:
            db_data = self._get_database()
            schema = db_data.get("properties", {})
        except:
            schema = {}

        url = f"{self.base_url}/pages"
        records = df.to_dict('records')
        total = len(records)
        success_count = 0
        
        excluded_fields = {'content_file', 'llm_model', 'pdf_filename', 'id', 'id_record', 'titre'}
        
        print(f"🚀 Début de l'envoi de {total} lignes vers Notion (via requests)...")
        
        for idx, row in enumerate(records, 1):
            try:
                properties = {}
                
                # Title
                title_val = row.get("titre", "Sans titre")
                if pd.isna(title_val): title_val = "Sans titre"
                properties[title_prop_name] = {
                    "title": [{"text": {"content": str(title_val)[:2000]}}]
                }
                
                # Other columns
                for col, val in row.items():
                    if col in excluded_fields:
                        continue
                    
                    # Find type in schema
                    prop_def = schema.get(col, {})
                    prop_type = prop_def.get("type", "rich_text")
                    
                    formatted = self._format_property_value(val, prop_type)
                    if formatted:
                        properties[col] = formatted

                payload = {
                    "parent": {"database_id": self.database_id},
                    "properties": properties
                }
                
                r = requests.post(url, headers=self.headers, json=payload)
                if r.status_code == 200:
                    success_count += 1
                    if idx % 10 == 0:
                        print(f"✅ Envoyé {idx}/{total}")
                else:
                    print(f"❌ Erreur ligne {idx}: {r.text}")

            except Exception as e:
                print(f"❌ Exception ligne {idx}: {e}")
        
        print(f"✅ Terminé : {success_count}/{total} importés.")
        return success_count

    def clear_database(self):
        """Archive all pages"""
        print("🗑️ Vidage de la base Notion (requests)...")
        
        query_url = f"{self.base_url}/databases/{self.database_id}/query"
        pages_to_archive = []
        has_more = True
        next_cursor = None
        
        try:
            # 1. Collect all pages
            while has_more:
                body = {}
                if next_cursor:
                    body["start_cursor"] = next_cursor
                
                r = requests.post(query_url, headers=self.headers, json=body)
                if r.status_code != 200:
                    print(f"❌ Impossible de lister les pages: {r.text}")
                    return 0
                
                data = r.json()
                results = data.get("results", [])
                pages_to_archive.extend(results)
                
                has_more = data.get("has_more", False)
                next_cursor = data.get("next_cursor")
            
            print(f"🔍 {len(pages_to_archive)} pages trouvées à archiver.")
            
            # 2. Archive them
            deleted = 0
            for page in pages_to_archive:
                page_id = page["id"]
                archive_url = f"{self.base_url}/pages/{page_id}"
                
                r = requests.patch(archive_url, headers=self.headers, json={"archived": True})
                if r.status_code == 200:
                    deleted += 1
                else:
                    print(f"❌ Erreur archivage {page_id}: {r.text}")
            
            print(f"✅ {deleted} pages archivées.")
            return deleted
            
        except Exception as e:
            print(f"❌ Erreur globale clear_database: {e}")
            return 0
