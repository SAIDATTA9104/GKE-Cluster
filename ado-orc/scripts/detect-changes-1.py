import os
import sys
import subprocess
import yaml
from load_config import load_modules


def run_command(cmd: str) -> str:
    """Run a shell command and return its output or exit on failure."""
    result = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {cmd}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def get_system_access_token() -> str:
    """Get the Azure DevOps System Access Token from environment variables."""
    access_token = os.getenv("SYSTEM_ACCESSTOKEN")
    if not access_token:
        print("##vso[task.logissue type=warning]SYSTEM_ACCESSTOKEN not found. Authentication may fail.")
        return ""
    return access_token


def get_changed_files():
    """Return a list of changed files based on PR or direct push."""
    build_reason = os.getenv("BUILD_REASON", "")
    target_branch = os.getenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "")
    access_token = get_system_access_token()

    if build_reason.lower() == "pullrequest" and target_branch:
        branch = target_branch.replace("refs/heads/", "")
        print(f"PR detected: comparing with target branch: {branch}")
        
        # Use System Access Token for authentication
        if access_token:
            fetch_cmd = f'git -c http.extraheader="AUTHORIZATION: bearer {access_token}" fetch origin {branch}'
        else:
            fetch_cmd = f'git fetch origin {branch}'
        
        run_command(fetch_cmd)
        changed_files = run_command(f"git diff --name-only origin/{branch}...HEAD")
    else:
        print("Direct push detected: comparing with previous commit")
        changed_files = run_command("git diff --name-only HEAD~1 HEAD")

    return changed_files.splitlines()


def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_changes.py <config_path>")
        sys.exit(1)

    config_path = sys.argv[1]

    # Load modules + execution order
    modules_dict = load_modules(config_path)
    print("Modules loaded from config:", modules_dict)

    modules_changed = {name: False for name in modules_dict.keys()}

    # Load ignore paths if present
    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
    ignore_prefixes = config.get("Ignore_Paths", [])

    # Get changed files
    print("Ignore Paths:", ignore_prefixes)
    changed_files = get_changed_files()
    print("Changed files:")
    for file in changed_files:
        print(file)

        # Skip ignored files
        if any(file.startswith(prefix) for prefix in ignore_prefixes):
            continue

        # Mark changed modules
        for name, path in modules_dict.items():
            if file.startswith(path):
                modules_changed[name] = True

    # Collect changed modules
    changed_modules = [name for name, changed in modules_changed.items() if changed]
    changed_modules_str = ",".join(changed_modules)

    if not changed_modules:
        print("##vso[task.logissue type=warning]No module changes detected. Skipping pipeline.")
        print("##vso[task.complete result=SucceededWithIssues;]")
        sys.exit(0)
    else:
        print(f"The following modules will be deployed: {changed_modules_str}")
        print(f"##vso[task.setvariable variable=changedModules;isOutput=true]{changed_modules_str}")


if __name__ == "__main__":
    main()
