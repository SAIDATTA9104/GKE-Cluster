import oci
from google.cloud import secretmanager
import json
import os
import gzip
import shutil
from datetime import datetime
from typing import Dict, Any
import configparser
from io import StringIO

# --- GCP SECRET CONFIGURATION (REQUIRED: REPLACE PLACEHOLDERS) ---

# Your Google Cloud Project ID where the secrets are stored
GCP_PROJECT_ID = "your-gcp-project-id"

# 1. SECRET ID holding the OCI Configuration FILE content (INI text)
# Example Secret Content: 
# [DEFAULT]
# user=ocid1.user.oc1..aaaa...
# fingerprint=a4:b3:c2:...
# key_file=/path/to/key/file.pem  <-- Path will be replaced by the script
# tenancy=ocid1.tenancy.oc1..bbbb...
# region=us-ashburn-1
GCP_CONFIG_SECRET_ID = "oci-config-ini-file-text"

# 2. SECRET ID holding the OCI API Private Key file content (PEM text)
# Example Secret Content:
# -----BEGIN RSA PRIVATE KEY-----...
# -----END RSA PRIVATE KEY-----
GCP_KEY_SECRET_ID = "oci-private-key-pem-text"

# Usually 'latest', unless you need a specific pinned version
SECRET_VERSION_ID = "latest"

# -----------------------------------------------------------------

# Constants for temporary file names used during authentication
TEMP_CONFIG_FILE_PATH = "oci_config_temp"
TEMP_KEY_FILE_PATH = "oci_api_key_temp.pem"


def read_secret_text(project_id: str, secret_id: str, version_id: str) -> str:
    """
    Access the payload for the given secret version and return it as a raw string.
    
    Args:
        project_id: Your Google Cloud project ID.
        secret_id: The ID of the secret.
        version_id: The version of the secret (e.g., 'latest').
        
    Returns:
        The raw string content of the secret payload.
    """
    client = secretmanager.SecretManagerServiceClient()
    # Build the resource name.
    name = client.secret_version_path(project_id, secret_id, version_id)

    print(f"--- Accessing secret: {name} ---")

    try:
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        
        print(f"✅ Successfully retrieved payload for secret ID: {secret_id}")
        return payload

    except Exception as e:
        print(f"❌ ERROR: Failed to access secret '{secret_id}'.")
        print(f"Details: {e}")
        raise # Re-raise to halt script if GCP auth or secret access fails

def create_oci_config_dict_from_ini(
    ini_content: str, 
    key_pem_content: str
) -> Dict[str, str]:
    """
    Constructs and returns the OCI configuration dictionary required by the SDK.
    It writes the key and config text to temporary files for OCI SDK to load.
    
    Returns:
        A dictionary containing the OCI configuration data.
    """
    
    print(f"\n--- Preparing OCI Configuration ---")
    
    # 1. Write the private key content to a temporary file
    try:
        with open(TEMP_KEY_FILE_PATH, "w") as f:
            f.write(key_pem_content)
        print(f"🔑 Successfully wrote OCI private key content to temporary file: {TEMP_KEY_FILE_PATH}")
    except IOError as e:
        print(f"❌ ERROR: Could not write temporary key file: {e}")
        raise

    # 2. Parse the INI content to modify the key_file path
    config_parser = configparser.ConfigParser()
    config_parser.read_string(ini_content)
    print("📋 Parsed INI content from config secret.")

    # Update the key_file path in the INI structure to point to the temporary file
    if 'DEFAULT' in config_parser:
        absolute_key_path = os.path.abspath(TEMP_KEY_FILE_PATH)
        config_parser['DEFAULT']['key_file'] = absolute_key_path
        print(f"🔄 Replaced 'key_file' path with absolute temporary path: {absolute_key_path}")
    else:
        print("⚠️ Warning: Could not find [DEFAULT] section in OCI config text. OCI SDK might fail.")
        
    # 3. Write the modified INI content to a temporary config file
    try:
        with open(TEMP_CONFIG_FILE_PATH, 'w') as f:
            config_parser.write(f)
        print(f"⚙️ Wrote final OCI config to temporary file: {TEMP_CONFIG_FILE_PATH}")
    except IOError as e:
        print(f"❌ ERROR: Could not write temporary config file: {e}")
        raise

    # 4. Load the configuration dictionary using the OCI SDK utility
    config = oci.config.from_file(file_location=TEMP_CONFIG_FILE_PATH, profile_name="DEFAULT")
    print("✅ OCI Configuration successfully loaded using oci.config.from_file.")
    
    return config

def fetch_oci_reports(oci_config: Dict[str, Any], destination_dir: str = "downloaded_reports"):
    """
    Connects to OCI Object Storage using the provided config to list and 
    download ALL available Cost Reports.
    """
    downloaded_count = 0
    try:
        print(f"\n--- Connecting to OCI Object Storage ---")
        
        # Initialize the Object Storage Client with the loaded config
        object_storage_client = oci.object_storage.ObjectStorageClient(oci_config)
        print("✅ Object Storage Client initialized.")

        # OCI Cost/Usage reports are stored in an Oracle-owned bucket
        REPORT_NAMESPACE = "bling"
        # The bucket name is automatically the Tenancy OCID
        REPORT_BUCKET = oci_config['tenancy'] 
        REPORT_PREFIX = "reports/cost-csv" 
        
        print(f"Tenant OCID (Bucket Name): {REPORT_BUCKET}")
        print(f"Report Namespace: {REPORT_NAMESPACE}")
        print(f"Report Prefix (Type): {REPORT_PREFIX}")

        # Create destination directory
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)
            print(f"Created destination directory: {destination_dir}")

        # List all objects (reports) in the bucket
        print(f"Listing objects in Object Storage bucket: {REPORT_BUCKET}...")
        list_objects_response = oci.pagination.list_call_get_all_results(
            object_storage_client.list_objects,
            REPORT_NAMESPACE,
            REPORT_BUCKET,
            prefix=REPORT_PREFIX,
            fields='name,timeCreated'
        )

        reports = list_objects_response.data.objects
        # Sort reports by creation time (most recent first) for consistent processing order
        reports = sorted(reports, key=lambda x: x.time_created, reverse=True)
        print(f"📊 Found {len(reports)} cost reports. Starting download sequence...")

        if not reports:
            print("No cost reports found.")
            return

        # Iterate through all found reports and download them
        for i, report in enumerate(reports):
            report_name = report.name
            
            print(f"\n--- Processing Report {i + 1}/{len(reports)}: {report_name} ---")

            local_file_path_gz = os.path.join(destination_dir, os.path.basename(report_name))
            local_file_path_csv = local_file_path_gz.replace(".gz", "")

            # Check if CSV already exists to prevent re-downloading
            if os.path.exists(local_file_path_csv):
                print(f"ℹ️ CSV already exists locally. Skipping download for: {local_file_path_csv}")
                continue

            print(f"Downloading report to: {local_file_path_gz}...")
            
            # Get the object (report file)
            get_object_response = object_storage_client.get_object(
                REPORT_NAMESPACE,
                REPORT_BUCKET,
                report_name
            )

            # Write the content to a compressed file
            with open(local_file_path_gz, 'wb') as f:
                # Use a buffer size of 1MB for reading/writing chunks
                for chunk in get_object_response.data.read(1024 * 1024): 
                    f.write(chunk)
            
            print(f"✅ Download complete. File size: {os.path.getsize(local_file_path_gz) / (1024*1024):.2f} MB")

            # Unzip the file
            print(f"Unzipping report to: {local_file_path_csv}")
            with gzip.open(local_file_path_gz, 'rb') as f_in:
                with open(local_file_path_csv, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            print(f"✅ Report successfully unzipped and ready at: {local_file_path_csv}")
            os.remove(local_file_path_gz)
            print(f"Cleaned up compressed file: {local_file_path_gz}")
            downloaded_count += 1
            
        print(f"\n--- Download Summary ---")
        print(f"Total reports found: {len(reports)}")
        print(f"Total reports newly downloaded/processed: {downloaded_count}")


    except Exception as e:
        print(f"❌ OCI Report fetching failed: {e}")
        # Log the specific OCI SDK error and raise to be caught by main
        raise 

    finally:
        print(f"\n--- Starting Temporary File Cleanup ---")
        # Clean up the temporary key and config files
        if os.path.exists(TEMP_KEY_FILE_PATH):
            os.remove(TEMP_KEY_FILE_PATH)
            print(f"✅ Cleaned up temporary key file: {TEMP_KEY_FILE_PATH}")
        else:
            print(f"ℹ️ Temporary key file not found for cleanup: {TEMP_KEY_FILE_PATH}")
            
        if os.path.exists(TEMP_CONFIG_FILE_PATH):
            os.remove(TEMP_CONFIG_FILE_PATH)
            print(f"✅ Cleaned up temporary config file: {TEMP_CONFIG_FILE_PATH}")
        else:
            print(f"ℹ️ Temporary config file not found for cleanup: {TEMP_CONFIG_FILE_PATH}")


def main():
    """
    Main function to orchestrate fetching secrets and downloading the OCI report.
    """
    print("=" * 60)
    print("OCI REPORT DOWNLOAD SCRIPT (INI Text & Key from Separate Secrets)")
    print("=" * 60)
    
    try:
        # 1. Fetch OCI Configuration INI Text
        oci_ini_content = read_secret_text(
            GCP_PROJECT_ID, 
            GCP_CONFIG_SECRET_ID, 
            SECRET_VERSION_ID
        )
        print("✅ GCP OCI Config (INI) secret retrieval complete.")

        # 2. Fetch OCI Private Key PEM Text
        oci_key_pem_content = read_secret_text(
            GCP_PROJECT_ID, 
            GCP_KEY_SECRET_ID, 
            SECRET_VERSION_ID
        )
        print("✅ GCP OCI Private Key (PEM) secret retrieval complete.")


        # 3. Create OCI Config Dictionary from the text secrets
        oci_config_data = create_oci_config_dict_from_ini(
            oci_ini_content, 
            oci_key_pem_content
        )
        print("✅ OCI Configuration preparation successful. Starting report download...")


        # 4. Fetch OCI Reports using the retrieved configuration
        fetch_oci_reports(oci_config_data)
        
        print("\n*** Script completed successfully! ***")

    except Exception:
        # The specific error was already printed in the called function
        print("\n*** Script terminated due to previous errors. Please check the logs above. ***")


if __name__ == "__main__":
    main()
