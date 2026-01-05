import os
import requests
import re
from pyairtable import Api
from dotenv import load_dotenv
import pandas as pd


class AirtableConnector:
    """Connector to send data to Airtable"""
    
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("AIRTABLE_TOKEN")
        self.base_id = os.getenv("AIRTABLE_BASE_ID")
        self.table_name = os.getenv("AIRTABLE_TABLE_NAME")
        
        if not all([self.token, self.base_id, self.table_name]):
            raise ValueError("Missing Airtable credentials in .env file")
        
        self.api = Api(self.token)
        self.table = self.api.table(self.base_id, self.table_name)
    
    def _get_table_metadata(self):
        """Get table metadata (ID, fields) from schema"""
        try:
            base = self.api.base(self.base_id)
            # Note: pyairtable schema() returns a BaseSchema object
            schema = base.schema()
            for table in schema.tables:
                # Check both name and ID (in case user provided Table ID in .env)
                if table.name == self.table_name or table.id == self.table_name:
                    return table
            return None
        except Exception as e:
            print(f"⚠️ Could not fetch table metadata: {str(e)}")
            if "403" in str(e) or "permission" in str(e).lower():
                print("👉 Hint: Your Airtable token might be missing the 'schema.bases:read' scope.")
            return None

    def get_table_fields(self):
        """Get list of field names in the Airtable table"""
        table = self._get_table_metadata()
        if table:
            return [field.name for field in table.fields]
        return []
    
    def get_field_types(self):
        """Get dictionary of field name -> field type"""
        table = self._get_table_metadata()
        if table:
            return {field.name: field.type for field in table.fields}
        return {}
    
    def sync_schema(self, df: pd.DataFrame) -> bool:
        """
        Create missing fields in Airtable based on DataFrame columns.
        Requires 'schema.bases:write' scope.
        Returns True if successful or not needed, False if metadata could not be fetched.
        """
        print("🔄 Checking schema synchronization...")
        table_meta = self._get_table_metadata()
        if not table_meta:
            print("❌ Could not find table metadata. Cannot sync schema.")
            print("👉 To fix this: Regenerate your Airtable Personal Access Token with these scopes:")
            print("   - data.records:read")
            print("   - data.records:write")
            print("   - schema.bases:read")
            print("   - schema.bases:write")
            return False

        existing_field_names = [f.name for f in table_meta.fields]
        # Identify missing columns (excluding 'id' which is renamed to 'id_record')
        df_cols = [c if c != 'id' else 'id_record' for c in df.columns]
        missing_cols = [c for c in df_cols if c not in existing_field_names]

        if not missing_cols:
            print("✅ Schema is up to date.")
            return True

        print(f"🛠️ Creating {len(missing_cols)} missing fields: {missing_cols}")
        
        # URL for creating fields via Metadata API
        url = f"https://api.airtable.com/v0/meta/bases/{self.base_id}/tables/{table_meta.id}/fields"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        for col in missing_cols:
            field_type = "singleLineText" # Default
            options = None

            # Heuristics for type inference based on column name
            col_lower = col.lower()
            
            if "date" in col_lower:
                field_type = "date"
                options = {"dateFormat": {"name": "iso"}}
            elif "email" in col_lower:
                field_type = "email"
            elif "url" in col_lower or "link" in col_lower:
                field_type = "url"
            elif "montant" in col_lower or "amount" in col_lower:
                field_type = "number"
                options = {"precision": 0}
            elif "resume" in col_lower or "description" in col_lower or "content" in col_lower:
                field_type = "multilineText"
            elif col in ["categories", "tags", "eligibilite", "public_cible", "public_cible_detail"]:
                field_type = "multipleSelects"
                options = {"choices": []} # Start empty, let typecast fill it
            elif col in ["type_financement", "enrichment_status", "source_id", "llm_model"]:
                field_type = "singleSelect"
                options = {"choices": []}
            elif "checkbox" in col_lower:
                field_type = "checkbox"
                options = {"icon": "check", "color": "greenBright"}

            payload = {
                "name": col,
                "type": field_type
            }
            if options:
                payload["options"] = options
            
            try:
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    print(f"   ✅ Created field '{col}' ({field_type})")
                else:
                    print(f"   ❌ Failed to create '{col}': {response.text}")
            except Exception as e:
                print(f"   ❌ Error creating '{col}': {e}")
        
        return True

    def create_table(self, name: str, df_schema: pd.DataFrame = None) -> str:
        """
        Create a new table in the base.
        Args:
            name: Name of the new table
            df_schema: Optional DataFrame to infer fields from
        Returns:
            The ID of the created table
        """
        print(f"🛠️ Creating new table '{name}'...")
        
        # Define default fields if no schema provided
        fields = [
            {"name": "titre", "type": "singleLineText"},
            {"name": "id_record", "type": "singleLineText"}, # Primary key usually needs to be first, but Airtable handles it
        ]
        
        # If DataFrame provided, infer fields
        if df_schema is not None:
            fields = []
            # Ensure primary field is first (usually 'titre' or 'id_record')
            # Airtable requires the first field to be the primary field (text, number, date, etc.)
            primary_field = "titre" if "titre" in df_schema.columns else df_schema.columns[0]
            fields.append({"name": primary_field, "type": "singleLineText"})
            
            for col in df_schema.columns:
                if col == primary_field or col == 'id': continue
                
                col_name = col if col != 'id' else 'id_record'
                field_type = "singleLineText"
                options = None
                
                # Simple type inference
                col_lower = col.lower()
                if "date" in col_lower:
                    field_type = "date"
                    options = {"dateFormat": {"name": "iso"}}
                elif "email" in col_lower:
                    field_type = "email"
                elif "url" in col_lower or "link" in col_lower:
                    field_type = "url"
                elif "montant" in col_lower:
                    field_type = "number"
                    options = {"precision": 0}
                elif "resume" in col_lower or "description" in col_lower:
                    field_type = "multilineText"
                elif col in ["categories", "tags", "eligibilite", "public_cible"]:
                    field_type = "multipleSelects"
                    options = {"choices": []}
                elif col in ["type_financement", "source_id", "enrichment_status"]:
                    field_type = "singleSelect"
                    options = {"choices": []}
                
                field_def = {"name": col_name, "type": field_type}
                if options:
                    field_def["options"] = options
                fields.append(field_def)

        url = f"https://api.airtable.com/v0/meta/bases/{self.base_id}/tables"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": name,
            "fields": fields,
            "description": "Table created by AAP-Watch"
        }
        
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            table_id = response.json().get("id")
            print(f"✅ Table '{name}' created successfully! ID: {table_id}")
            return table_id
        else:
            raise Exception(f"Failed to create table: {response.text}")

    def upload_dataframe(self, df: pd.DataFrame, batch_size: int = 10, auto_filter_fields: bool = True):
        """
        Upload a DataFrame to Airtable
        
        Args:
            df: pandas DataFrame to upload
            batch_size: number of records per batch (max 10 for Airtable)
            auto_filter_fields: if True, only upload fields that exist in Airtable
        
        Returns:
            Number of records uploaded
        """
        # Create a copy to avoid modifying the original DataFrame
        df_copy = df.copy()
        
        # Rename 'id' column if it exists (Airtable reserves this field name)
        if 'id' in df_copy.columns:
            df_copy = df_copy.rename(columns={'id': 'id_record'})
            print("⚠️ Renamed 'id' column to 'id_record' (Airtable reserves 'id' field name)")
        
        # Convert date columns to ISO format (YYYY-MM-DD)
        date_columns = ['date_publication', 'date_limite', 'date_ouverture', 'date_cloture']
        for col in date_columns:
            if (col in df_copy.columns):
                # Convert to datetime then to ISO format string
                df_copy[col] = pd.to_datetime(df_copy[col], errors='coerce').dt.strftime('%Y-%m-%d')
                # Replace NaT with empty string
                df_copy[col] = df_copy[col].fillna('')
                print(f"✅ Converted {col} to ISO date format")
        
        # Clean numeric columns (like montant_max)
        numeric_columns = ['montant_max', 'montant_min']
        for col in numeric_columns:
            if col in df_copy.columns:
                # Convert to numeric, invalid values become NaN
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
                # Replace NaN with None (Airtable will show as empty)
                df_copy[col] = df_copy[col].where(pd.notna(df_copy[col]), None)
                print(f"✅ Converted {col} to numeric format")
        
        # Get field types to handle formatting (list vs string)
        field_types = self.get_field_types()
        
        # Filter columns to only include fields that exist in Airtable
        # Also exclude specific internal fields as requested
        excluded_fields = {'content_file', 'llm_model', 'pdf_filename'}
        
        if auto_filter_fields:
            existing_fields = list(field_types.keys())
            if existing_fields:
                df_columns = set(df_copy.columns)
                # Remove excluded fields from the available fields
                available_fields = (df_columns & set(existing_fields)) - excluded_fields
                
                missing_fields = df_columns - set(existing_fields)
                if missing_fields:
                    print(f"⚠️ Fields missing in Airtable table: {missing_fields}")
                
                print(f"✅ Will upload only these fields: {available_fields}")
                df_copy = df_copy[list(available_fields)]
            else:
                print("⚠️ Could not verify fields, uploading all columns")
                # Still try to drop excluded fields if they exist
                df_copy = df_copy.drop(columns=[c for c in excluded_fields if c in df_copy.columns], errors='ignore')
        else:
             # Even if auto_filter is False, we respect the explicit exclusion list
             df_copy = df_copy.drop(columns=[c for c in excluded_fields if c in df_copy.columns], errors='ignore')
        
        # Convert DataFrame to list of dictionaries
        records = df_copy.to_dict('records')
        
        # Clean records (replace None with empty string, handle lists properly)
        records_cleaned = []
        for record in records:
            cleaned_record = {}
            for k, v in record.items():
                field_type = field_types.get(k)

                # Handle email fields validation
                if field_type == 'email' or k == 'email_contact':
                    # Normalize value if it's a list
                    val_to_check = v
                    if isinstance(v, list):
                        if len(v) > 0:
                            val_to_check = v[0]
                        else:
                            continue
                    
                    # Check for empty/null on the scalar value
                    if pd.isna(val_to_check) or val_to_check == '':
                        continue
                        
                    email_str = str(val_to_check)

                    # Validate format
                    if re.match(r"[^@]+@[^@]+\.[^@]+", email_str):
                        cleaned_record[k] = email_str
                    else:
                        print(f"⚠️ Invalid email format ignored for field '{k}': '{email_str}'")
                    continue

                # Handle lists (for Multiple Select fields)
                if isinstance(v, list):
                    field_type = field_types.get(k)
                    
                    # If field is text, join the list
                    if field_type in ['singleLineText', 'multilineText', 'richText']:
                        cleaned_record[k] = ", ".join(str(x) for x in v if x)
                    # If field is singleSelect, take the first one
                    elif field_type == 'singleSelect':
                         if len(v) > 0:
                             cleaned_record[k] = str(v[0])
                    # Default (multipleSelects or unknown) -> keep as list
                    elif len(v) > 0:
                        cleaned_record[k] = v
                        
                # Handle date fields - don't include if empty
                elif k in date_columns:
                    if pd.isna(v) or v == 'NaT' or v == '':
                        # Don't include empty date fields - Airtable will reject them
                        continue
                    else:
                        cleaned_record[k] = v
                # Handle numeric fields - don't include if None/NaN
                elif k in numeric_columns:
                    if pd.isna(v) or v is None:
                        # Don't include empty numeric fields
                        continue
                    else:
                        cleaned_record[k] = v
                # Handle scalar values
                elif pd.isna(v) or v == 'NaT':
                    cleaned_record[k] = ""
                else:
                    cleaned_record[k] = v
            records_cleaned.append(cleaned_record)
        
        # Upload in batches
        uploaded_count = 0
        total_batches = (len(records_cleaned) - 1) // batch_size + 1
        
        for i in range(0, len(records_cleaned), batch_size):
            batch = records_cleaned[i:i + batch_size]
            try:
                # Use typecast=True to allow Airtable to create new select options
                self.table.batch_create(batch, typecast=True)
                uploaded_count += len(batch)
                print(f"✅ Uploaded batch {i//batch_size + 1}/{total_batches} ({len(batch)} records)")
            except Exception as e:
                print(f"❌ Error uploading batch {i//batch_size + 1}: {str(e)}")
                # Print first record of batch for debugging
                if batch:
                    print(f"🔍 First record in failed batch: {list(batch[0].keys())}")
                    print(f"🔍 Sample values: {dict(list(batch[0].items())[:3])}")
                raise
        
        return uploaded_count
    
    def clear_table(self):
        """Delete all records from the table"""
        all_records = self.table.all()
        record_ids = [record['id'] for record in all_records]
        
        if record_ids:
            # Delete in batches of 10
            for i in range(0, len(record_ids), 10):
                batch_ids = record_ids[i:i + 10]
                self.table.batch_delete(batch_ids)
                print(f"🗑️ Deleted batch {i//10 + 1}/{(len(record_ids)-1)//10 + 1}")
        
        print(f"✅ Cleared {len(record_ids)} records from table")
        return len(record_ids)
