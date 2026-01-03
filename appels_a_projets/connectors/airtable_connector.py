import os
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
    
    def get_table_fields(self):
        """Get list of field names in the Airtable table"""
        try:
            # Get table schema
            base = self.api.base(self.base_id)
            schema = base.schema()
            
            # Find the table and extract field names
            for table in schema.tables:
                if table.name == self.table_name:
                    return [field.name for field in table.fields]
            
            return []
        except Exception as e:
            print(f"⚠️ Could not fetch table schema: {str(e)}")
            return []
    
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
            if col in df_copy.columns:
                # Convert to datetime then to ISO format string
                df_copy[col] = pd.to_datetime(df_copy[col], errors='coerce').dt.strftime('%Y-%m-%d')
                # Replace NaT with empty string
                df_copy[col] = df_copy[col].fillna('')
                print(f"✅ Converted {col} to ISO date format")
        
        # Clean numeric columns (like montant_max)
        numeric_columns = ['montant_max']
        for col in numeric_columns:
            if col in df_copy.columns:
                # Convert to numeric, invalid values become NaN
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
                # Replace NaN with None (Airtable will show as empty)
                df_copy[col] = df_copy[col].where(pd.notna(df_copy[col]), None)
                print(f"✅ Converted {col} to numeric format")
        
        # Filter columns to only include fields that exist in Airtable
        if auto_filter_fields:
            existing_fields = self.get_table_fields()
            if existing_fields:
                df_columns = set(df_copy.columns)
                missing_fields = df_columns - set(existing_fields)
                available_fields = df_columns & set(existing_fields)
                
                if missing_fields:
                    print(f"⚠️ Fields missing in Airtable table: {missing_fields}")
                    print(f"✅ Will upload only these fields: {available_fields}")
                    df_copy = df_copy[list(available_fields)]
                else:
                    print(f"✅ All {len(df_columns)} fields exist in Airtable")
            else:
                print("⚠️ Could not verify fields, uploading all columns")
        
        # Convert DataFrame to list of dictionaries
        records = df_copy.to_dict('records')
        
        # Clean records (replace None with empty string, handle lists properly)
        records_cleaned = []
        for record in records:
            cleaned_record = {}
            for k, v in record.items():
                # Handle lists (for Multiple Select fields)
                if isinstance(v, list):
                    # Only include non-empty lists
                    if len(v) > 0:
                        cleaned_record[k] = v
                    # Skip empty lists (don't include the field)
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
