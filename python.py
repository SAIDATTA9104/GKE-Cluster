import oci
from google.cloud import secretmanager, storage, bigquery
from google.cloud.exceptions import NotFound
import json
import os
import gzip
import shutil
from datetime import datetime, timedelta, date 
from typing import Dict, Any, Optional
import configparser
import logging
import sys 


# =================================================================
#                         LOGGING INITIALIZATION
# =================================================================

def setup_logging() -> None:
    """Initializes the logging system to output to a local file and console."""
    # Configure the console/default logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure a file handler for local log persistence
    file_handler = logging.FileHandler(LOCAL_LOG_FILE_PATH, mode='w')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    root_logger = logging.getLogger()
    
    # Prevent adding multiple file handlers if the function is called repeatedly
    if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
        root_logger.addHandler(file_handler)
        
    logging.info(f"Logging initialized. Output going to console and local file: {LOCAL_LOG_FILE_PATH}")

def print_to_log(*args, **kwargs) -> None:
    """A wrapper for logging.info to replace the standard print function."""
    logging.info(' '.join(map(str, args)))

# Overrides the built-in 'print' function to use logging for consistent output
_print_standard = print
print = print_to_log

# =================================================================
#                             GCP HELPERS
# =================================================================

def read_secret_text(project_id: str, secret_id: str, version_id: str) -> str:
    """
    Accesses the payload for the given secret version and returns it as a raw string.

    Args:
        project_id: The ID of the GCP project containing the secret.
        secret_id: The ID of the secret to access.
        version_id: The version of the secret (e.g., 'latest').

    Returns:
        The secret payload decoded as a UTF-8 string.
    """
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, secret_id, version_id)
    print(f"--- Accessing secret: {secret_id} ---")
    try:
        response = client.access_secret_version(request={"name": name})
        # Decode and strip potential whitespace from the payload
        payload = response.payload.data.decode("UTF-8").strip() 
        print(f"Successfully retrieved payload for secret ID: {secret_id}")
        return payload
    except Exception as e:
        logging.error(f"ERROR: Failed to access secret '{secret_id}'. Details: {e}")
        raise 

def upload_to_gcs(local_file_path: str, bucket_name: str, folder_name: str, project_id: str) -> bool:
    """
    Uploads a file to a specific folder in a Google Cloud Storage bucket.
    
    Returns:
        True if upload was successful, False otherwise.
    """
    if not os.path.exists(local_file_path):
        print(f"GCS Upload Skipped: File not found at {local_file_path}")
        return False
        
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    filename = os.path.basename(local_file_path)
    # Construct the full GCS destination path
    gcs_path = f"{folder_name.strip('/')}/{filename}" if folder_name else filename
    blob = bucket.blob(gcs_path)
    
    try:
        print(f"Starting upload of {filename} to gs://{bucket_name}/{gcs_path}...")
        blob.upload_from_filename(local_file_path)
        print("Successfully uploaded file to GCS.")
        return True
    except Exception as e:
        logging.error(f"GCS Upload Failed for {filename} to bucket {bucket_name}. Details: {e}")
        return False

# =================================================================
#                             OCI HELPERS
# =================================================================

def create_oci_config_dict_from_ini(ini_content: str, key_pem_content: str) -> Dict[str, str]:
    """
    Constructs the OCI configuration dictionary required by the SDK from secret content.
    
    The function temporarily writes the private key and the modified config INI file 
    to disk, as the OCI SDK requires file paths for configuration.
    
    Args:
        ini_content: The raw text of the OCI configuration INI file.
        key_pem_content: The raw text of the OCI API private key PEM file.
        
    Returns:
        The OCI configuration dictionary.
    """
    print(f"\n--- Preparing OCI Configuration ---")
    
    # 1. Write the private key to a temporary file
    try:
        with open(TEMP_OCI_KEY_FILE, "w") as f:
            f.write(key_pem_content)
        print(f"Successfully wrote OCI private key content to temporary file: {TEMP_OCI_KEY_FILE}")
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary key file: {e}")
        raise

    # 2. Parse INI content and modify the key_file path
    config_parser = configparser.ConfigParser()
    config_parser.read_string(ini_content)
    print("📋 Parsed INI content from config secret.")

    if 'DEFAULT' in config_parser:
        # OCI requires an absolute path for the key file.
        absolute_key_path = os.path.abspath(TEMP_OCI_KEY_FILE)
        config_parser['DEFAULT']['key_file'] = absolute_key_path
        print(f"Replaced 'key_file' path with absolute temporary path: {absolute_key_path}")
    else:
        print("Warning: Could not find [DEFAULT] section in OCI config text. OCI SDK might fail.")

    # 3. Write the modified INI content to a temporary file
    try:
        with open(TEMP_OCI_CONFIG_FILE, 'w') as f:
            config_parser.write(f)
        print(f"⚙️ Wrote final OCI config to temporary file: {TEMP_OCI_CONFIG_FILE}")
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary config file: {e}")
        raise
        
    # 4. Load the config using the OCI SDK from the temporary file
    config = oci.config.from_file(file_location=TEMP_OCI_CONFIG_FILE, profile_name="DEFAULT")
    print("OCI Configuration successfully loaded.")
    return config

def decompress_gz_file(gz_path: str, destination_dir: str) -> Optional[str]:
    """
    Decompresses a .gz file into the specified destination directory.
    
    Returns:
        The path to the uncompressed file, or None on failure.
    """
    if not gz_path.endswith(".gz"):
        print(f"Skipping decompression for non-gz file: {os.path.basename(gz_path)}")
        return gz_path
        
    filename_base = os.path.basename(gz_path)
    # Remove the '.gz' extension
    uncompressed_filename = filename_base.replace(".gz", "") 
    uncompressed_path = os.path.join(destination_dir, uncompressed_filename)
    print(f"  Decompressing {filename_base}...")
    
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(uncompressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"  ----> Unzipped to: {uncompressed_filename}")
        return uncompressed_path
    except Exception as e:
        logging.error(f"ERROR: Failed to decompress {gz_path}. Details: {e}")
        return None

def fetch_oci_reports(oci_config: Dict[str, Any], download_dir: str, csv_dir: str, target_date: date) -> None:
    """
    Connects to OCI Object Storage to download and process cost reports for a specific date.
    
    The GZIP files are downloaded to download_dir, uncompressed to csv_dir, and the 
    uncompressed CSVs are uploaded to the GCS staging bucket.
    """
    downloaded_count = 0
    uploaded_count = 0
    
    print(f"\n--- Target Date for Report Download: {target_date.strftime('%Y-%m-%d')} ---")
    
    try:
        print("\n--- Connecting to OCI Object Storage ---")
        object_storage_client = oci.object_storage.ObjectStorageClient(oci_config)
        print("Object Storage Client initialized.")

        # The bucket name for the cost reports is the tenancy OCID from the config
        report_bucket_name = oci_config['tenancy']
        
        print(f"Tenant OCID (Bucket Name): {report_bucket_name}")
        print(f"Report Namespace: {OCI_REPORT_NAMESPACE}")
        
        # Create local directories if they don't exist
        for d in [download_dir, csv_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
                print(f"Created destination directory: {d}")

        print(f"\nListing objects in OCI bucket: {report_bucket_name}...")
        
        # Use pagination utility to handle potentially large number of objects
        list_objects_response = oci.pagination.list_call_get_all_results(
            object_storage_client.list_objects,
            OCI_REPORT_NAMESPACE,
            report_bucket_name,
            prefix=OCI_REPORT_PREFIX,
            fields='name,timeCreated'
        )

        for obj in list_objects_response.data.objects:
            report_creation_date = obj.time_created.date()
            
            # Filter for reports created on the specific target date
            if report_creation_date != target_date:
                continue 
            
            object_name = obj.name
            print(f"Found report: {object_name} (Created: {report_creation_date})")
            
            # 1. Download the object (the GZIP file)
            object_details = object_storage_client.get_object(
                OCI_REPORT_NAMESPACE, report_bucket_name, object_name
            )

            filename = object_name.rsplit("/", 1)[-1]
            gz_file_path = os.path.join(download_dir, filename)
            
            # Write the object data to the local GZIP file
            with open(gz_file_path, "wb") as f:
                # Stream the content in chunks to handle large files
                for chunk in object_details.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
            
            downloaded_count += 1
            print(f"----> Downloaded to: {gz_file_path}")

            # 2. Decompress the GZIP file to a local CSV file
            uncompressed_path = decompress_gz_file(gz_file_path, csv_dir)
            
            # 3. Upload the uncompressed CSV to GCS Staging
            if uncompressed_path and uncompressed_path != gz_file_path:
                upload_success = upload_to_gcs(
                    uncompressed_path, 
                    GCS_REPORT_BUCKET_NAME, 
                    GCS_STAGING_FOLDER,
                    GCP_PROJECT_ID
                )
                if upload_success:
                    uploaded_count += 1
            
        print("\n--- OCI Report Fetching Summary ---")
        print(f"Total reports found and downloaded for {target_date}: {downloaded_count}")
        print(f"Total CSV files decompressed and uploaded to GCS staging: {uploaded_count}")
        
    except Exception as e:
        logging.critical(f"OCI Report fetching failed critically: {e}", exc_info=True)
        raise 

# =================================================================
#                       BIGQUERY LOAD FUNCTION
# =================================================================

def load_gcs_to_bigquery(project_id: str, dataset_id: str, table_id: str, gcs_uri: str, dataset_location: str) -> None:
    """
    Creates a BigQuery Load Job to load CSV files from GCS into the target table,
    using WRITE_APPEND.
    """
    print(f"\n--- Starting BigQuery Load Job ---")
    print(f"Source URI: {gcs_uri}")
    print(f"Destination Table: {dataset_id}.{table_id}")

    client = bigquery.Client(project=project_id)
    table_ref = client.dataset(dataset_id).table(table_id)
    
    # 1. Define Job Configuration (specifying how BigQuery should read the CSV)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,                # Skip the header row
        autodetect=False,                   # We rely on an existing schema or manual schema definition
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND, # Add data to the existing table
    )

    try:
        # Check if the dataset exists, create it if not found
        try:
            client.get_dataset(dataset_id)
        except NotFound:
            dataset = bigquery.Dataset(f"{project_id}.{dataset_id}")
            dataset.location = dataset_location
            client.create_dataset(dataset, timeout=30)
            print(f"Created BigQuery dataset: {dataset_id}")

        # 2. Start the asynchronous load job
        load_job = client.load_table_from_uri(
            gcs_uri,
            table_ref,
            job_config=job_config
        )

        print(f"Started load job: {load_job.job_id}")
        
        # 3. Wait for the job to complete
        load_job.result() 

        # 4. Final verification and logging
        destination_table = client.get_table(table_ref)
        print("BigQuery Load Job successful.")
        print(f"Loaded {load_job.output_rows} rows into {dataset_id}.{table_id}.")
        print(f"Total rows in table: {destination_table.num_rows}.")

    except Exception as e:
        logging.error(f"BigQuery Load Job failed for {table_id}. Details: {e}", exc_info=True)
        raise

# =================================================================
#                         GCS ARCHIVE & CLEANUP
# =================================================================

def archive_staged_files_in_gcs(project_id: str, bucket_name: str, source_folder: str, destination_folder: str) -> int:
    """
    Moves all files from a source folder (staging) to a destination folder (archive) 
    within the same GCS bucket.
    
    Returns:
        The count of files successfully moved.
    """
    print(f"\n--- Archiving staged files in GCS ---")
    print(f"Source: gs://{bucket_name}/{source_folder}")
    print(f"Destination: gs://{bucket_name}/{destination_folder}")
    
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    
    source_prefix = source_folder.strip('/') + '/'
    dest_prefix = destination_folder.strip('/') + '/'
    
    # List all files (blobs) in the staging folder
    blobs_to_move = list(bucket.list_blobs(prefix=source_prefix))

    # Filter out the folder itself if it was listed as a zero-byte blob
    files_to_move = [blob for blob in blobs_to_move if not blob.name.endswith('/')]
    
    if not files_to_move:
        print("No files found in the staging folder to archive.")
        return 0

    print(f"Found {len(files_to_move)} files to archive.")
    moved_count = 0
    try:
        for source_blob in files_to_move:
            file_name = os.path.basename(source_blob.name)
            destination_blob_name = f"{dest_prefix}{file_name}"
            
            print(f"Moving {source_blob.name} to {destination_blob_name}...")
            
            # 'rename_blob' is an atomic move operation
            bucket.rename_blob(source_blob, new_name=destination_blob_name)
            moved_count += 1
            
        print(f"Successfully archived {moved_count} files to the processed folder.")
        return moved_count
    except Exception as e:
        logging.error(f"GCS file archive operation FAILED. Details: {e}", exc_info=True)
        raise

def clean_up_local_directories(directories: list) -> None:
    """Recursively removes the specified local directories and their contents."""
    print("\n--- Cleaning up temporary local directories ---")
    for d in directories:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f"Cleaned up temporary directory: {d}")
            except OSError as e:
                logging.warning(f"Warning: Could not remove directory {d}. Details: {e}")

# =================================================================
#                             MAIN EXECUTION
# =================================================================

def main():
    """
    Main function to orchestrate the entire process:
    1. Set up logging.
    2. Fetch OCI secrets from GCP Secret Manager.
    3. Configure the OCI SDK.
    4. Download, decompress, and upload reports to GCS staging.
    5. Load staged data from GCS into BigQuery.
    6. Archive the staged GCS files.
    7. Clean up all temporary local files (auth, downloads, CSVs).
    8. Upload the final log file to GCS.
    """
    setup_logging()
    
    logging.info("=" * 80)
    logging.info("OCI REPORT DOWNLOAD, UPLOAD, AND BIGQUERY LOAD SCRIPT STARTED")
    logging.info(f"Target Report Date: {TARGET_REPORT_DATE.strftime('%Y-%m-%d')}")
    logging.info("=" * 80)
    
    try:
        # --- PHASE 1: Authentication and OCI Configuration ---
        oci_ini_content = read_secret_text(GCP_PROJECT_ID, GCP_OCI_CONFIG_SECRET_ID, SECRET_VERSION_ID)
        oci_key_pem_content = read_secret_text(GCP_PROJECT_ID, GCP_OCI_KEY_SECRET_ID, SECRET_VERSION_ID)
        oci_config_data = create_oci_config_dict_from_ini(oci_ini_content, oci_key_pem_content)
        
        # --- PHASE 2: Download, Decompress, and Upload to GCS Staging ---
        fetch_oci_reports(oci_config_data, LOCAL_DOWNLOAD_DIR, LOCAL_CSV_DIR, TARGET_REPORT_DATE)

        # --- PHASE 3: BigQuery Load Job ---
        load_gcs_to_bigquery(
            project_id=GCP_PROJECT_ID, 
            dataset_id=BIGQUERY_DATASET_ID, 
            table_id=BIGQUERY_TABLE_NAME, 
            gcs_uri=GCS_LOAD_URI,
            dataset_location=BIGQUERY_DATASET_LOCATION
        )
        
        # --- PHASE 4: GCS Archiving ---
        # Move the successfully loaded files from staging to the processed/archive folder
        archive_staged_files_in_gcs(
            project_id=GCP_PROJECT_ID,
            bucket_name=GCS_REPORT_BUCKET_NAME,
            source_folder=GCS_STAGING_FOLDER,
            destination_folder=GCS_ARCHIVE_FOLDER
        )
        
        logging.info("\n*** Script completed successfully! All data loaded into BigQuery and staging files archived. ***")

    except Exception:
        # Log the critical error before the finally block executes
        logging.critical("\n*** Script terminated due to a critical error. Check logs for details. ***")

    finally:
        # --- PHASE 5: Local Cleanup and Log Upload ---
        print("\n--- Cleaning up Temporary Authentication Files ---")
        for temp_file in [TEMP_OCI_CONFIG_FILE, TEMP_OCI_KEY_FILE]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    print(f"Cleaned up temporary file: {temp_file}")
                except OSError as e:
                    logging.warning(f"Warning: Could not remove temporary file {temp_file}. Details: {e}")
        
        # Cleanup local downloaded GZIPs and uncompressed CSVs
        clean_up_local_directories([LOCAL_DOWNLOAD_DIR, LOCAL_CSV_DIR])
        
        # Upload the log file to GCS and delete the local copy
        if os.path.exists(LOCAL_LOG_FILE_PATH):
            logging.info(f"\n--- Uploading final log file: {LOCAL_LOG_FILE_PATH} ---")
            log_upload_status = upload_to_gcs(
                LOCAL_LOG_FILE_PATH,
                LOG_GCS_BUCKET,
                LOG_GCS_FOLDER,
                GCP_PROJECT_ID
            )
            if log_upload_status:
                logging.info("Log file uploaded successfully. Removing local copy.")
                os.remove(LOCAL_LOG_FILE_PATH)
            else:
                logging.error("Failed to upload log file to GCS. Local copy remains.")


if __name__ == "__main__":
    main()
