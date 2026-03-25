"""
Authentication module for Azure DevOps MCP server.

Supports multiple authentication methods, auto-detected from environment variables:

1. **PAT (Personal Access Token)** — Set AZURE_DEVOPS_PAT
2. **Service Principal (Client Credentials)** — Set AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID
3. **Managed Identity** — Set AZURE_USE_MANAGED_IDENTITY=true (for Azure-hosted environments)
4. **Device Code Flow** — Default fallback (interactive, no app registration needed)

Priority: PAT > Client Credentials > Managed Identity > Device Code
"""

import base64
import os
import sys
import webbrowser
from pathlib import Path

import msal

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

# Azure DevOps first-party client ID — supports device code flow without app registration
AZURE_DEVOPS_CLIENT_ID = "872cd9fa-d31f-45e0-9eab-6e460a02d1f1"
AZURE_DEVOPS_SCOPE = ["499b84ac-1321-427f-aa17-267ca6975798/.default"]

# Token cache location (for Device Code and Client Credentials flows)
CACHE_DIR = Path.home() / ".azure-devops-mcp"
CACHE_FILE = CACHE_DIR / "token_cache.json"


# ──────────────────────────────────────────────
# Auth method detection
# ──────────────────────────────────────────────

def _detect_auth_method() -> str:
    """Detect which auth method to use based on environment variables.

    Returns one of: "pat", "client_credentials", "managed_identity", "device_code"
    """
    if os.getenv("AZURE_DEVOPS_PAT"):
        return "pat"
    if os.getenv("AZURE_CLIENT_ID") and os.getenv("AZURE_CLIENT_SECRET") and os.getenv("AZURE_TENANT_ID"):
        return "client_credentials"
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("true", "1", "yes"):
        return "managed_identity"
    return "device_code"


# ──────────────────────────────────────────────
# 1. PAT (Personal Access Token)
# ──────────────────────────────────────────────

def _get_pat_header() -> dict[str, str]:
    """Build a Basic auth header from a Personal Access Token."""
    pat = os.getenv("AZURE_DEVOPS_PAT", "")
    if not pat:
        raise ValueError("AZURE_DEVOPS_PAT environment variable is not set.")
    # Azure DevOps expects Basic auth with empty username and PAT as password
    encoded = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


# ──────────────────────────────────────────────
# 2. Service Principal (Client Credentials)
# ──────────────────────────────────────────────

def _get_client_credentials_token() -> str:
    """Acquire token using OAuth 2.0 client credentials (service principal)."""
    client_id = os.getenv("AZURE_CLIENT_ID", "")
    client_secret = os.getenv("AZURE_CLIENT_SECRET", "")
    tenant_id = os.getenv("AZURE_TENANT_ID", "")

    if not all([client_id, client_secret, tenant_id]):
        raise ValueError(
            "Client credentials auth requires AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, "
            "and AZURE_TENANT_ID environment variables."
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    cache = _get_token_cache()

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
        token_cache=cache,
    )

    result = app.acquire_token_for_client(scopes=AZURE_DEVOPS_SCOPE)

    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Client credentials authentication failed: {error}")

    _save_token_cache(cache)
    return result["access_token"]


# ──────────────────────────────────────────────
# 3. Managed Identity
# ──────────────────────────────────────────────

def _get_managed_identity_token() -> str:
    """Acquire token using Azure Managed Identity (system or user-assigned).

    Requires the azure-identity package. Works on Azure VMs, App Service,
    Azure Functions, Azure Container Instances, and AKS.
    """
    try:
        from azure.identity import ManagedIdentityCredential
    except ImportError:
        raise ImportError(
            "Managed Identity auth requires the 'azure-identity' package. "
            "Install it with: pip install azure-identity"
        )

    client_id = os.getenv("AZURE_CLIENT_ID")  # For user-assigned managed identity
    credential = ManagedIdentityCredential(client_id=client_id)

    # Azure DevOps resource ID
    token = credential.get_token("499b84ac-1321-427f-aa17-267ca6975798/.default")
    return token.token


# ──────────────────────────────────────────────
# 4. Device Code Flow (interactive, original method)
# ──────────────────────────────────────────────

def _get_device_code_token() -> str:
    """Acquire token using MSAL device code flow (interactive).

    No app registration required — uses Azure DevOps first-party client ID.
    """
    tenant = os.getenv("AZURE_TENANT_ID", "organizations")
    authority = f"https://login.microsoftonline.com/{tenant}"

    cache = _get_token_cache()
    app = msal.PublicClientApplication(
        client_id=AZURE_DEVOPS_CLIENT_ID,
        authority=authority,
        token_cache=cache,
    )

    # Try silent acquisition first (cached/refresh token)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(AZURE_DEVOPS_SCOPE, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            return result["access_token"]

    # Fall back to interactive device code flow
    flow = app.initiate_device_flow(scopes=AZURE_DEVOPS_SCOPE)
    if "user_code" not in flow:
        raise RuntimeError(
            f"Failed to initiate device code flow: {flow.get('error_description', 'Unknown error')}"
        )

    # Print instructions to stderr so they don't interfere with MCP stdio
    print(flow["message"], file=sys.stderr, flush=True)

    # Auto-open the browser for convenience
    verification_uri = flow.get("verification_uri")
    if verification_uri:
        try:
            webbrowser.open(verification_uri)
        except Exception:
            pass  # Non-critical — user can still open the URL manually

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Device code authentication failed: {error}")

    _save_token_cache(cache)
    return result["access_token"]


# ──────────────────────────────────────────────
# Token cache helpers
# ──────────────────────────────────────────────

def _get_token_cache() -> msal.SerializableTokenCache:
    """Load or create a persistent token cache."""
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache) -> None:
    """Persist the token cache to disk."""
    if cache.has_state_changed:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")


# ──────────────────────────────────────────────
# Public API (used by all client modules)
# ──────────────────────────────────────────────

def get_token() -> str:
    """Acquire an access token for Azure DevOps using the auto-detected auth method.

    Returns the raw access token string.
    For PAT auth, this raises — use get_auth_header() instead.
    """
    method = _detect_auth_method()

    if method == "pat":
        raise RuntimeError("PAT auth does not use Bearer tokens. Use get_auth_header() directly.")
    elif method == "client_credentials":
        return _get_client_credentials_token()
    elif method == "managed_identity":
        return _get_managed_identity_token()
    else:
        return _get_device_code_token()


def get_auth_header() -> dict[str, str]:
    """Get an Authorization header dict for Azure DevOps REST API calls.

    Auto-detects the auth method from environment variables:
    - AZURE_DEVOPS_PAT → Basic auth
    - AZURE_CLIENT_ID + AZURE_CLIENT_SECRET → Bearer (client credentials)
    - AZURE_USE_MANAGED_IDENTITY=true → Bearer (managed identity)
    - (none of the above) → Bearer (device code flow)
    """
    method = _detect_auth_method()

    if method == "pat":
        return _get_pat_header()
    else:
        token = get_token()
        return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# CLI helpers (used by __main__.py subcommands)
# ──────────────────────────────────────────────

_AUTH_METHOD_LABELS = {
    "pat": "Personal Access Token (PAT)",
    "client_credentials": "Service Principal (Client Credentials)",
    "managed_identity": "Managed Identity",
    "device_code": "Device Code Flow",
}


def login() -> None:
    """Interactive login via device code flow. Prints to stdout for CLI use."""
    from dotenv import load_dotenv

    load_dotenv()

    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    if not org_url:
        print(
            "Error: AZURE_DEVOPS_ORG_URL is not set.\n"
            "Set it before logging in:\n\n"
            "  export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org\n"
        )
        sys.exit(1)

    tenant = os.getenv("AZURE_TENANT_ID", "organizations")
    authority = f"https://login.microsoftonline.com/{tenant}"

    cache = _get_token_cache()
    app = msal.PublicClientApplication(
        client_id=AZURE_DEVOPS_CLIENT_ID,
        authority=authority,
        token_cache=cache,
    )

    # Check for existing cached token
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(AZURE_DEVOPS_SCOPE, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            username = accounts[0].get("username", "unknown")
            print(f"Already logged in as: {username}")
            print(f"Organization:         {org_url}")
            print(f"Token cache:          {CACHE_FILE}")
            return

    # Run device code flow interactively
    flow = app.initiate_device_flow(scopes=AZURE_DEVOPS_SCOPE)
    if "user_code" not in flow:
        print(f"Error: {flow.get('error_description', 'Failed to initiate device code flow')}")
        sys.exit(1)

    print(flow["message"])
    print()

    verification_uri = flow.get("verification_uri")
    if verification_uri:
        try:
            webbrowser.open(verification_uri)
            print("(Browser opened automatically)")
        except Exception:
            pass

    print("\nWaiting for authentication...")
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        print(f"\nLogin failed: {error}")
        sys.exit(1)

    _save_token_cache(cache)

    # Show who logged in
    accounts = app.get_accounts()
    username = accounts[0].get("username", "unknown") if accounts else "unknown"
    print(f"\nLogged in as:    {username}")
    print(f"Organization:    {org_url}")
    print(f"Token cached at: {CACHE_FILE}")
    print("\nYou can now add the server to your AI editor. No PAT needed!")


def status() -> None:
    """Show current auth configuration and token validity."""
    from dotenv import load_dotenv

    load_dotenv()

    org_url = os.getenv("AZURE_DEVOPS_ORG_URL")
    method = _detect_auth_method()
    label = _AUTH_METHOD_LABELS.get(method, method)

    print(f"Auth method:  {label}")
    print(f"Organization: {org_url or '(not set — AZURE_DEVOPS_ORG_URL is missing)'}")
    print(f"Token cache:  {CACHE_FILE}")
    print()

    if not org_url:
        print("Warning: AZURE_DEVOPS_ORG_URL is not set. The server will not start without it.")
        print("  export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org")
        return

    # Check token validity
    if method == "pat":
        pat = os.getenv("AZURE_DEVOPS_PAT", "")
        if pat:
            print(f"PAT: {'*' * (len(pat) - 4)}{pat[-4:]}" if len(pat) > 4 else "PAT: (set)")
            print("Status: Configured (validity cannot be checked without an API call)")
        else:
            print("Status: PAT is empty")
    elif method == "device_code":
        cache = _get_token_cache()
        tenant = os.getenv("AZURE_TENANT_ID", "organizations")
        authority = f"https://login.microsoftonline.com/{tenant}"
        app = msal.PublicClientApplication(
            client_id=AZURE_DEVOPS_CLIENT_ID,
            authority=authority,
            token_cache=cache,
        )
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(AZURE_DEVOPS_SCOPE, account=accounts[0])
            if result and "access_token" in result:
                _save_token_cache(cache)
                print(f"Logged in as: {accounts[0].get('username', 'unknown')}")
                print("Status: Token is valid")
            else:
                print("Status: Token expired — run 'azure-devops-mcp auth login' to re-authenticate")
        else:
            print("Status: Not logged in — run 'azure-devops-mcp auth login'")
    elif method == "client_credentials":
        print("Status: Configured (AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID)")
    elif method == "managed_identity":
        print("Status: Configured (AZURE_USE_MANAGED_IDENTITY=true)")
