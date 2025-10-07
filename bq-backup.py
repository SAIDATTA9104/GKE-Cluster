from google.cloud import bigquery

client = bigquery.Client()

source_dataset_id = "project.source_dataset"
backup_dataset_id = "project.backup_dataset"

tables = client.list_tables(source_dataset_id)

for table in tables:
    source_table_id = f"{source_dataset_id}.{table.table_id}"
    backup_table_id = f"{backup_dataset_id}.{table.table_id}"
    
    job = client.copy_table(source_table_id, backup_table_id)
    job.result()
    print(f"Backed up {source_table_id} to {backup_table_id}")
