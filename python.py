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
    
    if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
        root_logger.addHandler(file_handler)
        
    logging.info(f"Logging initialized. Output going to console and local file: {LOCAL_LOG_FILE_PATH}")

def print_to_log(*args, **kwargs) -> None:
    """A wrapper for logging.info to replace the standard print function."""
    logging.info(' '.join(map(str, args)))

# Overrides the built-in 'print' function to use logging for consistent output
print = print_to_log


# =================================================================
#                             GCP/OCI HELPERS
# =================================================================

def read_secret_text(project_id: str, secret_id: str, version_id: str) -> str:
    """Accesses the payload for the given secret version and returns it as a raw string."""
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, secret_id, version_id)
    print(f"--- Accessing secret: {secret_id} ---")
    try:
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8").strip() 
        print(f"Successfully retrieved payload for secret ID: {secret_id}")
        return payload
    except Exception as e:
        logging.error(f"ERROR: Failed to access secret '{secret_id}'. Details: {e}")
        raise 

def create_oci_config_dict_from_ini(ini_content: str, key_pem_content: str) -> Dict[str, str]:
    """Constructs the OCI configuration dictionary required by the SDK from secret content."""
    print(f"\n--- Preparing OCI Configuration ---")
    
    # 1. Write the private key to a temporary file
    try:
        with open(TEMP_OCI_KEY_FILE, "w") as f:
            f.write(key_pem_content)
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary key file: {e}")
        raise

    # 2. Modify INI content to point to the temporary key file
    config_parser = configparser.ConfigParser()
    config_parser.read_string(ini_content)
    
    if 'DEFAULT' in config_parser:
        absolute_key_path = os.path.abspath(TEMP_OCI_KEY_FILE)
        config_parser['DEFAULT']['key_file'] = absolute_key_path

    # 3. Write the modified INI content to a temporary file
    try:
        with open(TEMP_OCI_CONFIG_FILE, 'w') as f:
            config_parser.write(f)
    except IOError as e:
        logging.error(f"ERROR: Could not write temporary config file: {e}")
        raise
        
    # 4. Load the config using the OCI SDK
    config = oci.config.from_file(file_location=TEMP_OCI_CONFIG_FILE, profile_name="DEFAULT")
    print("OCI Configuration successfully loaded.")
    return config

def decompress_gz_file(gz_path: str, destination_dir: str) -> Optional[str]:
    """Decompresses a .gz file into the specified destination directory."""
    if not gz_path.endswith(".gz"):
        return gz_path
        
    filename_base = os.path.basename(gz_path)
    uncompressed_filename = filename_base.replace(".gz", "") 
    uncompressed_path = os.path.join(destination_dir, uncompressed_filename)
    
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(uncompressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"  ----> Unzipped to: {uncompressed_path}")
        return uncompressed_path
    except Exception as e:
        logging.error(f"ERROR: Failed to decompress {gz_path}. Details: {e}")
        return None

def upload_to_gcs(local_file_path: str, bucket_name: str, folder_name: str, project_id: str) -> bool:
    """Uploads a file to a specific folder in a Google Cloud Storage bucket."""
    if not os.path.exists(local_file_path):
        return False
        
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    filename = os.path.basename(local_file_path)
    gcs_path = f"{folder_name.strip('/')}/{filename}" if folder_name else filename
    blob = bucket.blob(gcs_path)
    
    try:
        print(f"Starting upload of {filename} to gs://{bucket_name}/{gcs_path}...")
        blob.upload_from_filename(local_file_path)
        print("Successfully uploaded file to GCS.")
        return True
    except Exception as e:
        logging.error(f"GCS Upload Failed for {filename}. Details: {e}")
        return False

def fetch_oci_reports(oci_config: Dict[str, Any], download_dir: str, csv_dir: str, target_date: date) -> int:
    """Connects to OCI Object Storage to download, decompress, and upload reports."""
    downloaded_count = 0
    uploaded_count = 0
    
    try:
        object_storage_client = oci.object_storage.ObjectStorageClient(oci_config)
        report_bucket_name = oci_config['tenancy']
        
        # Create local directories
        for d in [download_dir, csv_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

        # List objects
        list_objects_response = oci.pagination.list_call_get_all_results(
            object_storage_client.list_objects,
            OCI_REPORT_NAMESPACE,
            report_bucket_name,
            prefix=OCI_REPORT_PREFIX,
            fields='name,timeCreated'
        )

        for obj in list_objects_response.data.objects:
            report_creation_date = obj.time_created.date()
            
            if report_creation_date != target_date:
                continue 
            
            object_name = obj.name
            print(f"Found report: {object_name} (Created: {report_creation_date})")
            
            # 1. Download the GZIP object
            object_details = object_storage_client.get_object(
                OCI_REPORT_NAMESPACE, report_bucket_name, object_name
            )

            filename = object_name.rsplit("/", 1)[-1]
            gz_file_path = os.path.join(download_dir, filename)
            
            with open(gz_file_path, "wb") as f:
                for chunk in object_details.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
            
            downloaded_count += 1

            # 2. Decompress
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
            
        print(f"\nSummary: Downloaded {downloaded_count}, Uploaded {uploaded_count} to staging.")
        return uploaded_count
        
    except Exception as e:
        logging.critical(f"OCI Report fetching failed critically: {e}", exc_info=True)
        raise 

def load_gcs_to_bigquery(project_id: str, dataset_id: str, table_id: str, gcs_uri: str, dataset_location: str) -> None:
    """Creates a BigQuery Load Job to load CSV files from GCS into the target table."""
    client = bigquery.Client(project=project_id)
    table_ref = client.dataset(dataset_id).table(table_id)
    
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=False,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    try:
        # Check if the dataset exists, create it if not
        try:
            client.get_dataset(dataset_id)
        except NotFound:
            dataset = bigquery.Dataset(f"{project_id}.{dataset_id}")
            dataset.location = dataset_location
            client.create_dataset(dataset, timeout=30)
            print(f"Created BigQuery dataset: {dataset_id}")

        load_job = client.load_table_from_uri(
            gcs_uri,
            table_ref,
            job_config=job_config
        )

        load_job.result() # Wait for the job to complete
        
        print(f"BigQuery Load Job successful. Loaded {load_job.output_rows} rows.")

    except Exception as e:
        logging.error(f"BigQuery Load Job failed for {table_id}. Details: {e}", exc_info=True)
        raise

def archive_staged_files_in_gcs(project_id: str, bucket_name: str, source_folder: str, destination_folder: str) -> int:
    """Moves all files from a source folder (staging) to a destination folder (archive)."""
    print(f"\n--- Archiving staged files: {source_folder} to {destination_folder} ---")
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    
    source_prefix = source_folder.strip('/') + '/'
    dest_prefix = destination_folder.strip('/') + '/'
    
    blobs_to_move = list(bucket.list_blobs(prefix=source_prefix))
    files_to_move = [blob for blob in blobs_to_move if not blob.name.endswith('/')]
    
    if not files_to_move:
        print("No files found in the staging folder to archive.")
        return 0

    moved_count = 0
    try:
        for source_blob in files_to_move:
            file_name = os.path.basename(source_blob.name)
            destination_blob_name = f"{dest_prefix}{file_name}"
            bucket.rename_blob(source_blob, new_name=destination_blob_name)
            moved_count += 1
            
        print(f"Successfully archived {moved_count} files.")
        return moved_count
    except Exception as e:
        logging.error(f"GCS file archive operation FAILED. Details: {e}", exc_info=True)
        raise

def clean_up_local_files(directories: list, files: list) -> None:
    """Removes specified local directories and files."""
    print("\n--- Cleaning up temporary local files ---")
    # Clean up directories
    for d in directories:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f"Cleaned up directory: {d}")
            except OSError as e:
                logging.warning(f"Warning: Could not remove directory {d}. Details: {e}")
                
    # Clean up individual files
    for f in files:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Cleaned up file: {f}")
            except OSError as e:
                logging.warning(f"Warning: Could not remove file {f}. Details: {e}")


# =================================================================
#                             MAIN EXECUTION
# =================================================================

def main():
    """
    Main function to orchestrate the entire scheduled process.
    """
    setup_logging()
    
    logging.info("=" * 80)
    logging.info("OCI REPORT DOWNLOAD, UPLOAD, AND BIGQUERY LOAD SCRIPT STARTED")
    logging.info(f"Target Report Date: {TARGET_REPORT_DATE.strftime('%Y-%m-%d')}")
    logging.info(f"GCS Staging URI: {GCS_LOAD_URI}")
    logging.info("=" * 80)
    
    files_uploaded_to_staging = 0

    try:
        # 1. Fetch Secrets and Configure OCI SDK
        oci_ini_content = read_secret_text(GCP_PROJECT_ID, GCP_OCI_CONFIG_SECRET_ID, SECRET_VERSION_ID)
        oci_key_pem_content = read_secret_text(GCP_PROJECT_ID, GCP_OCI_KEY_SECRET_ID, SECRET_VERSION_ID)
        oci_config_data = create_oci_config_dict_from_ini(oci_ini_content, oci_key_pem_content)
        
        # 2. Fetch OCI Reports, Decompress, and Upload CSVs to GCS Staging
        files_uploaded_to_staging = fetch_oci_reports(
            oci_config_data, LOCAL_DOWNLOAD_DIR, LOCAL_CSV_DIR, TARGET_REPORT_DATE
        )

        if files_uploaded_to_staging == 0:
            logging.info("No new reports found or uploaded. Skipping BQ load and archiving.")
            return

        # 3. Execute the BigQuery Load Job
        load_gcs_to_bigquery(
            project_id=GCP_PROJECT_ID, 
            dataset_id=BIGQUERY_DATASET_ID, 
            table_id=BIGQUERY_TABLE_NAME, 
            gcs_uri=GCS_LOAD_URI,
            dataset_location=BIGQUERY_DATASET_LOCATION
        )
        
        # 4. ARCHIVE GCS STAGING FILES after successful BQ load
        archive_staged_files_in_gcs(
            project_id=GCP_PROJECT_ID,
            bucket_name=GCS_REPORT_BUCKET_NAME,
            source_folder=GCS_STAGING_FOLDER,
            destination_folder=GCS_ARCHIVE_FOLDER
        )
        
        logging.info("\n*** Script completed successfully! All data loaded and archived. ***")

    except Exception:
        # Re-raise the exception to ensure the Cloud Run Job registers a failure
        logging.critical("\n*** Script terminated due to a critical error. ***")
        sys.exit(1)

    finally:
        # 5. Local Cleanup and Log Upload
        
        # Cleanup temporary local directories and OCI auth files
        clean_up_local_files(
            directories=[LOCAL_DOWNLOAD_DIR, LOCAL_CSV_DIR],
            files=[TEMP_OCI_CONFIG_FILE, TEMP_OCI_KEY_FILE]
        )
        
        # Upload the log file to GCS
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
