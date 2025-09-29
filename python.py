from google.cloud import secretmanager
import json
import os

# Set these environment variables or hardcode (less secure)
# project_id = os.environ.get("GCP_PROJECT_ID")
# secret_id = os.environ.get("GCP_SECRET_ID") # e.g., 'oci_config_json'
# version_id = "latest"

# **Replace with your actual values**
GCP_PROJECT_ID = "your-gcp-project-id"
GCP_SECRET_ID = "oci-config-for-oci-report-script"
SECRET_VERSION_ID = "latest" 

def access_secret_version(project_id: str, secret_id: str, version_id: str) -> dict:
    """
    Access the payload for the given secret version and return it as a dictionary.
    """
    # Create the Secret Manager client.
    client = secretmanager.SecretManagerServiceClient()

    # Build the resource name.
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

    try:
        # Access the secret version.
        response = client.access_secret_version(request={"name": name})

        # Get the secret payload and decode it.
        payload = response.payload.data.decode("UTF-8")
        
        # Assume the secret payload is a JSON string of your OCI configuration
        return json.loads(payload)

    except Exception as e:
        print(f"Error accessing secret {secret_id}: {e}")
        # Re-raise or handle the error as appropriate for your environment
        raise

# Example OCI Configuration structure in GCP Secret Manager (JSON format):
# {
#   "user": "ocid1.user.oc1..aaaa...",
#   "fingerprint": "a4:b3:c2:...",
#   "key_file_content": "-----BEGIN RSA PRIVATE KEY-----...",
#   "tenancy": "ocid1.tenancy.oc1..bbbb...",
#   "region": "us-ashburn-1"
# }

# Get the OCI configuration
# oci_config = access_secret_version(GCP_PROJECT_ID, GCP_SECRET_ID, SECRET_VERSION_ID)
# print("OCI Config Loaded Successfully.")
