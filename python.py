import oci
from google.cloud import secretmanager, storage
import json
import os
import gzip
import shutil
from datetime import datetime, timedelta, date 
from typing import Dict, Any, Optional
import configparser
import logging
import sys 

# --- CONFIGURATION ---

# Your Google Cloud Project ID where the secrets are stored
GCP_PROJECT_ID = 

# OCI Secrets
GCP_CONFIG_SECRET_ID = 
GCP_KEY_SECRET_ID = 
SECRET_VERSION_ID =

# GCS Report Destination
GCS_BUCKET_NAME = 
# Folder to upload uncompressed CSVs to initially (staging area)
GCS_STAGING_FOLDER = "oci-reports/daily-csv/" 
# Folder to move the CSVs to after processing is complete (archive)
GCS_PROCESSED_FOLDER = "oci-reports/processed/"

# GCS Logging Configuration
LOG_GCS_BUCKET = 
LOG_GCS_FOLDER = 
LOG_FILE_NAME = f"oci_download_report_{date.today().strftime('%Y%m%d')}.log"
LOCAL_LOG_FILE_PATH = LOG_FILE_NAME 

# Constants for temporary file names used during authentication
TEMP_CONFIG_FILE_PATH = "oci_config_temp"
TEMP_KEY_FILE_PATH = "oci_api_key_temp.pem"

# Constants for local file paths
DOWNLOAD_DIR = "downloaded_reports" 
LOCAL_CSV_PATH = "local_path_csv" 

# =================================================================
#                         LOGGING INITIALIZATION
# =================================================================

def setup_logging():
    """Initializes the logging system to output to a local file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler = logging.FileHandler(LOCAL_LOG_FILE_PATH, mode='w')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    root_logger = logging.getLogger()
    
    # Avoid adding duplicate handlers if the script is re-run in the same session
    if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
        root_logger.addHandler(file_handler)
        
    logging.info(f"Logging initialized. Output going to console and local file: {LOCAL_LOG_FILE_PATH}")

def print_to_log(*args, **kwargs):
    """Redirects print statements to the logging system."""
    logging.info(' '.join(map(str, args)))

# Override the built-in print function
_print = print
print = print_to_log

# =================================================================
#                         HELPER FUNCTIONS
# =================================================================

def read_secret_text(project_id: str, secret_id: str, version_id: str) -> str:
    """Accesses the payload for the given secret version and returns it as a string."""
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, secret_id, version_id)
    print(f"--- Accessing secret: {name} ---")
    try:
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8").strip() 
        print(f"Successfully retrieved payload for secret ID: {secret_id}")
        return payload
    except Exception as e:
        logging.error(f"ERROR: Failed to access secret '{secret_id}'. Details: {e}")
        raise 

def create_oci_config_dict_from_ini(ini_content: str, key_pem_content: str) -> Dict[str, str]:
    """Constructs the OCI configuration dictionary required by the SDK."""
    print(f"\n--- Preparing OCI Configuration ---")
    try:
        with open(TEMP_KEY_FILE_PATH, "w") as f:
            f.write(key_pem_content)
        print(f"Successfully wrote OCI private key to temporary file: {TEMP_KEY_FILE_PATH}")
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary key file: {e}")
        raise

    config_parser = configparser.ConfigParser()
    config_parser.read_string(ini_content)
    print("📋 Parsed INI content from config secret.")
    
    if 'DEFAULT' in config_parser:
        absolute_key_path = os.path.abspath(TEMP_KEY_FILE_PATH)
        config_parser['DEFAULT']['key_file'] = absolute_key_path
        print(f"Replaced 'key_file' path with absolute temporary path: {absolute_key_path}")
    else:
        print("Warning: Could not find [DEFAULT] section in OCI config text. OCI SDK might fail.")

    try:
        with open(TEMP_CONFIG_FILE_PATH, 'w') as f:
            config_parser.write(f)
        print(f"⚙️ Wrote final OCI config to temporary file: {TEMP_CONFIG_FILE_PATH}")
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary config file: {e}")
        raise

    config = oci.config.from_file(file_location=TEMP_CONFIG_FILE_PATH, profile_name="DEFAULT")
    print("OCI Configuration successfully loaded.")
    return config

def decompress_gz_file(gz_path: str, destination_dir: str) -> Optional[str]:
    """Decompresses a .gz file into the specified destination directory."""
    if not gz_path.endswith(".gz"):
        print(f"Skipping decompression for non-gz file: {os.path.basename(gz_path)}")
        return gz_path
        
    filename_base = os.path.basename(gz_path)
    uncompressed_filename = filename_base[:-3] 
    uncompressed_path = os.path.join(destination_dir, uncompressed_filename)
    
    print(f"   Decompressing {filename_base}...")
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(uncompressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"   ----> Unzipped to: {uncompressed_filename}")
        return uncompressed_path
    except Exception as e:
        logging.error(f"ERROR: Failed to decompress {gz_path}. Details: {e}")
        return None

def upload_to_gcs(local_file_path: str, bucket_name: str, folder_name: str, project_id: str):
    """Uploads a file to a specific folder in a Google Cloud Storage bucket."""
    if not os.path.exists(local_file_path):
        print(f"GCS Upload Skipped: File not found at {local_file_path}")
        return False
        
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    filename = os.path.basename(local_file_path)
    gcs_path = f"{folder_name.strip('/')}/{filename}" if folder_name else filename
    blob = bucket.blob(gcs_path)
    
    try:
        print(f"Starting upload of {filename} to gs://{bucket_name}/{gcs_path}...")
        blob.upload_from_filename(local_file_path)
        print(f"Successfully uploaded file to GCS.")
        return True
    except Exception as e:
        logging.error(f"GCS Upload Failed for {filename} to bucket {bucket_name}. Details: {e}")
        return False

def fetch_oci_reports(oci_config: Dict[str, Any], download_dir: str, csv_dir: str):
    """Connects to OCI Object Storage to download reports for the previous day."""
    downloaded_count = 0
    decompressed_count = 0
    
    yesterday_date = date.today() - timedelta(days=1)
    print(f"\n--- Target Date for Report Download: {yesterday_date.strftime('%Y-%m-%d')} ---")
    
    try:
        print(f"\n--- Connecting to OCI Object Storage ---")
        object_storage_client = oci.object_storage.ObjectStorageClient(oci_config)
        print("Object Storage Client initialized.")

        # NOTE: These values are specific to the OCI tenancy's reporting setup
        REPORT_NAMESPACE =
        REPORT_BUCKET = 
        REPORT_PREFIX = "" 
        
        print(f"Tenant OCID (Bucket Name): {REPORT_BUCKET}")
        print(f"Report Namespace: {REPORT_NAMESPACE}")
        
        for d in [download_dir, csv_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
                print(f"Created destination directory: {d}")

        print(f"\nListing objects in Object Storage bucket: {REPORT_BUCKET}...")
        list_objects_response = oci.pagination.list_call_get_all_results(
            object_storage_client.list_objects,
            REPORT_NAMESPACE,
            REPORT_BUCKET,
            prefix=REPORT_PREFIX,
            fields='name,timeCreated'
        )

        for o in list_objects_response.data.objects:
            report_creation_date = o.time_created.date()
            
            # Filter for reports created on the previous day
            if report_creation_date != yesterday_date:
                continue 
            
            object_name = o.name
            print(f"Found previous day's report: {object_name} (Created: {report_creation_date})")
            
            object_details = object_storage_client.get_object(
                REPORT_NAMESPACE, REPORT_BUCKET, object_name
            )

            filename = object_name.rsplit("/", 1)[-1]
            gz_file_path = os.path.join(download_dir, filename)
            
            with open(gz_file_path, "wb") as f:
                for chunk in object_details.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
            
            downloaded_count += 1
            print(f"----> Downloaded to: {gz_file_path}")

            uncompressed_path = decompress_gz_file(gz_file_path, csv_dir)
            
            if uncompressed_path and uncompressed_path != gz_file_path:
                upload_to_gcs(
                    uncompressed_path, 
                    GCS_BUCKET_NAME, 
                    GCS_STAGING_FOLDER,
                    GCP_PROJECT_ID
                )
                decompressed_count += 1
            
        print(f"\n--- Summary ---")
        print(f"Total reports found for {yesterday_date}: {downloaded_count}")
        print(f"Total files decompressed and uploaded to staging: {decompressed_count}")
        
    except Exception as e:
        logging.critical(f"OCI Report fetching failed critically: {e}", exc_info=True)
        raise 

# =================================================================
#                     GCS FILE MANAGEMENT (NEW)
# =================================================================

def move_staged_files_in_gcs(project_id: str, bucket_name: str, source_folder: str, destination_folder: str):
    """
    Moves all files from a source folder to a destination folder within the same GCS bucket.
    """
    print(f"\n--- Archiving staged files in GCS ---")
    print(f"Source: gs://{bucket_name}/{source_folder}")
    print(f"Destination: gs://{bucket_name}/{destination_folder}")
    
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    
    source_prefix = source_folder.strip('/') + '/'
    dest_prefix = destination_folder.strip('/') + '/'
    
    blobs_to_move = list(bucket.list_blobs(prefix=source_prefix))

    if not blobs_to_move:
        print("No files found in the staging folder to move.")
        return 0

    print(f"Found {len(blobs_to_move)} files to move.")
    moved_count = 0
    try:
        for source_blob in blobs_to_move:
            if source_blob.name.endswith('/'): # Skip folder objects
                continue

            file_name = os.path.basename(source_blob.name)
            destination_blob_name = f"{dest_prefix}{file_name}"
            
            print(f"Moving {source_blob.name} to {destination_blob_name}...")
            
            # 'rename_blob' is an atomic move operation
            bucket.rename_blob(source_blob, new_name=destination_blob_name)
            moved_count += 1
            
        print(f"Successfully moved {moved_count} files to the processed folder.")
        return moved_count
    except Exception as e:
        logging.error(f"GCS file move operation FAILED. Details: {e}", exc_info=True)
        raise

def clean_up_local_directories(directories: list):
    """Recursively removes the specified local directories."""
    print("\n--- Cleaning up temporary local directories ---")
    for d in directories:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f"Cleaned up temporary directory: {d}")
            except OSError as e:
                logging.warning(f"Warning: Could not remove directory {d}. Details: {e}")

# =================================================================
#                         MAIN EXECUTION
# =================================================================

def main():
    """
    Main function to orchestrate the process of downloading OCI reports,
    uploading them to a GCS staging area, and then moving them to a processed folder.
    """
    setup_logging()
    
    logging.info("=" * 80)
    logging.info("OCI REPORT DOWNLOAD AND GCS ARCHIVE SCRIPT STARTED")
    logging.info("=" * 80)
    
    try:
        # 1. OCI Configuration
        oci_ini_content = read_secret_text(GCP_PROJECT_ID, GCP_CONFIG_SECRET_ID, SECRET_VERSION_ID)
        oci_key_pem_content = read_secret_text(GCP_PROJECT_ID, GCP_KEY_SECRET_ID, SECRET_VERSION_ID)
        oci_config_data = create_oci_config_dict_from_ini(oci_ini_content, oci_key_pem_content)
        
        # 2. Fetch OCI Reports, Decompress, and Upload CSVs to GCS Staging
        fetch_oci_reports(oci_config_data, DOWNLOAD_DIR, LOCAL_CSV_PATH)

        # 3. Move files from GCS staging to processed folder
        move_staged_files_in_gcs(
            project_id=GCP_PROJECT_ID,
            bucket_name=GCS_BUCKET_NAME,
            source_folder=GCS_STAGING_FOLDER,
            destination_folder=GCS_PROCESSED_FOLDER
        )
        
        logging.info("\n*** Script completed successfully! All reports archived in GCS. ***")

    except Exception:
        # This catches errors from any step (Secret Manager, OCI, GCS)
        logging.critical("\n*** Script terminated due to a critical error. ***")

    finally:
        # 4. Cleanup temporary local authentication files
        print("\n--- Cleanup Temporary Auth Files ---")
        for temp_file in [TEMP_CONFIG_FILE_PATH, TEMP_KEY_FILE_PATH]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    print(f"Cleaned up temporary file: {temp_file}")
                except OSError as e:
                    logging.warning(f"Warning: Could not remove file {temp_file}. Details: {e}")
        
        # 5. Cleanup local download and CSV directories
        clean_up_local_directories([DOWNLOAD_DIR, LOCAL_CSV_PATH])
        
        # 6. Upload the final log file
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
                logging.error("Failed to upload log file to GCS.")

if __name__ == "__main__":
    main()
