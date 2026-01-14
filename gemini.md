# JetSki / Gemini Knowledge

This file documents specific operational context for this repository.

## Environment & Setup
- **Virtual Environment**: A python venv is located at `venv/` (not `.venv/`).
    - Activate: `source venv/bin/activate`
- **Credentials**: A `looker.ini` file exists in the root.
    - `main.py` is configured to fallback to the `[test]` section if standard environment variable init fails.
    - Useful for local `plan` checks (read-only) even if full write credentials aren't exported.

## Looker SDK & API Nuances
### Project Management
1.  **Creation**: The `WriteProject` model uses the `name` field for the Project ID during creation. It does **not** accept an `id` field, even though the API endpoint is `/projects/{project_id}`.
2.  **Verification (Get Diff)**:
    - To accurately detect projects that exist but are only in "Development Mode" (haven't been pushed/deployed to production), the SDK session must be switched to the `dev` workspace:
      ```python
      sdk.update_session(body=models.WriteApiSession(workspace_id="dev"))
      ```
3.  **Clean State**:
    - Always revert the session to `production` workspace after operations to avoid leaving the SDK in a state that might affect subsequent calls or user expectations.
      ```python
      sdk.update_session(body=models.WriteApiSession(workspace_id="production"))
      ```

### Connection Management
1.  **Secrets Handling**:
    - The SDK's `WriteDBConnection` model expects `password` and `certificate` fields.
    - Our YAML configuration uses `*_env_var` suffixes (e.g., `password_env_var`) to securely reference environment variables.
    - The `ConnectionManager` resolves these environment variables at runtime before populating the SDK model.
2.  **Field Filtering**:
    - When comparing config against existing connections, we explicitly ignore sensitive fields (`password`, `certificate`) and read-only metadata (`created_at`, `user_id`, `example`) to prevent false positive diffs.

### OIDC Management
1.  **Singleton Resource**: OIDC configuration is a singleton in Looker. We use `sdk.oidc_config()` (GET) and `sdk.update_oidc_config()` (PUT) rather than creating new resources.
2.  **Field Mapping**:
    - The SDK model uses `identifier` for the Client ID and `secret` for the Client Secret.
    - Our YAML uses `client_id` and `client_secret_env_var` for clarity and security, which valid fields are mapped to before API calls.
3.  **Group Mirroring**:
    - The `mirrored_groups` YAML list maps to `groups_with_role_ids` in the SDK.
    - We must resolve Role Names (from YAML) to Role IDs (required by SDK) by fetching all roles (`sdk.all_roles()`) and building a lookup map.

### Role Management (RBAC)
1.  **Dependency Order**:
    - **Creation**: Permission Sets -> Model Sets -> Roles. (Roles depend on Sets).
    - **Deletion**: Roles -> Permission Sets / Model Sets. (Sets cannot be deleted if used by a Role).
2.  **Resolution Strategy**:
    - The Manager maintains internal maps (`perm_set_map`, `model_set_map`, `role_map`) to resolve Names to IDs dynamically during the diff/apply process.
3.  **Safety & Protection**:
    - **Support Roles**: The SDK API returns `is_support_role` in some versions, but we fallback to a hardcoded list of protected names (e.g., `Support Basic Editor`, `Gemini`) to prevent accidental deletion.
    - **Admin**: The `Admin` role and its associated sets are strictly ignored during updates and deletions to prevent lockout.

## Running the Tool
- **Plan (Check)**: `python3 main.py --config-dir environments/dev --check`
- **Apply**: `python3 main.py --config-dir environments/dev --apply`
- **Tests**: `python3 -m unittest discover tests`
