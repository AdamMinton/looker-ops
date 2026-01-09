# Looker Infrastructure as Code (IaC)

This repository contains a **GitOps** solution for managing Looker instance configurations. It allows you to define your Looker **Connections** and **OIDC Authentication** settings in YAML files and apply them idempotently to multiple Looker environments (e.g., Development, Production).

## 🚀 Key Features

*   **Idempotency**: The tool compares your local YAML configuration against the actual Looker instance state. It only triggers API calls when a legitimate change is detected.
*   **Multi-Environment Support**: Manage disjoint environments (e.g., `dev`, `prod`) with separate configuration trees while sharing the same management logic.
*   **Secure**: Secrets (passwords, private keys) are **never** stored in plain text. They are referenced by Environment Variable names in the configuration and resolved at runtime.
*   **Safe RBAC Deletion**: Removes roles and permission sets that are no longer in your configuration, with built-in safeguards to protect critical system resources (e.g., Admin, Support roles).
*   **CI/CD Integrated**: Designed to run within GitHub Actions, providing "Plan" (PR comments) and "Apply" (Merge to Main) workflows.

## 📂 Project Structure

```text
looker-ops/
├── main.py                        # CLI Entrypoint
├── lib/                           # Core Logic
│   ├── connection_manager.py      # Diff/Apply logic for Database Connections
│   ├── oidc_manager.py            # Diff/Apply logic for OIDC Auth
│   ├── role_manager.py            # Diff/Apply logic for Roles/Permissions
│   └── utils.py                   # Helper functions (Config parsing, Secret resolution)
├── environments/                  # Environment-specific Configurations
│   ├── dev/
│   │   ├── connections.yaml
│   │   ├── oidc.yaml
│   │   └── roles.yaml
│   └── prod/
│       ├── connections.yaml
│       ├── oidc.yaml
│       └── roles.yaml
├── requirements.txt               # Python Dependencies
└── .github/
    └── workflows/
        └── looker_iac.yml         # GitHub Actions Workflow (Matrix Strategy)
```

## 🛠️ Setup & Installation

### Prerequisites
*   Python 3.9+
*   Admin access to the target Looker instance(s).
*   API Credentials (`client_id`, `client_secret`) for the Looker instance.

### Local Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-org/looker-ops.git
    cd looker-ops
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

### 1. Database Connections (`connections.yaml`)
Define your database connections in a list. Use `password_env_var` or `certificate_env_var` to reference secrets.

```yaml
- name: "snowflake_sales_prod"
  dialect_name: "snowflake"
  host: "my-org.snowflakecomputing.com"
  port: "443"
  database: "SALES_DB"
  schema: "PUBLIC"
  username: "looker_service_account"
  password_env_var: "SNOWFLAKE_PROD_PASSWORD" # Resolves $SNOWFLAKE_PROD_PASSWORD at runtime
  ssl: true

- name: "bq_sales_analytics"
  dialect_name: "bigquery_standard_sql"
  host: "my-gcp-project-id"        # For BigQuery, Host = Project ID
  database: "SALES_DATASET"        # For BigQuery, Database = Dataset Name
  uses_application_default_credentials: true
  max_connections: 50
```

### 2. OIDC Authentication (`oidc.yaml`)
Define the singleton OIDC configuration.

```yaml
enabled: true
identifier: "google_workspace"
# display_name: "Google Login" # Note: Display name is not configurable via API in some versions
issuer: "https://accounts.google.com"
client_id: "123456.apps.googleusercontent.com"
client_secret_env_var: "OIDC_CLIENT_SECRET" # Resolves $OIDC_CLIENT_SECRET at runtime
authorization_endpoint: "https://accounts.google.com/o/oauth2/v2/auth"
token_endpoint: "https://oauth2.googleapis.com/token"
userinfo_endpoint: "https://openidconnect.googleapis.com/v1/userinfo"
audience: "123456.apps.googleusercontent.com" # Usually same as client_id
scopes: ["openid", "email", "profile"]
user_attribute_map:
  email: "email"
  first_name: "given_name"
  last_name: "family_name"
groups_attribute: "groups"

# Mirroring (Optional)
set_roles_from_groups: true # REQUIRED to enable Group Mirroring
mirrored_groups:
  - name: "oidc-admin-group" # Name of the group claim value from IdP
    role_ids: ["2"] # List of Role IDs to assign to this group

# Advanced Options (Optional)
allow_direct_roles: false
allow_normal_group_membership: false
allow_roles_from_normal_groups: false
auth_requires_role: false
# Advanced Options (Optional)
allow_direct_roles: false
allow_normal_group_membership: false
allow_roles_from_normal_groups: false
auth_requires_role: false
```

### 3. Roles & Permissions (`roles.yaml`)
Define your **Permission Sets**, **Model Sets**, and **Roles** by name. The tool automatically resolves dependencies.

```yaml
# 1. Permission Sets
permission_sets:
  - name: "Finance User Perms"
    permissions:
      - "access_data"
      - "see_looks"
      - "see_user_dashboards"
      - "explore"

# 2. Model Sets
model_sets:
  - name: "Finance Models"
    models:
      - "finance_sales"
      - "finance_marketing"

# 3. Roles
roles:
  - name: "Finance Analyst"
    permission_set: "Finance User Perms" # Referenced by Name
    model_set: "Finance Models"          # Referenced by Name
# 3. Roles
roles:
  - name: "Finance Analyst"
    permission_set: "Finance User Perms" # Referenced by Name
    model_set: "Finance Models"          # Referenced by Name
```

### ⚠️ Deletions & Safety
**Removing** a Role, Permission Set, or Model Set from `roles.yaml` will trigger a **Deletion** in Looker.
However, strict safety rules are enforced:
*   **Admin Role**: The `Admin` role is never deleted and its definition (sets) cannot be updated via this tool.
*   **Support Roles**: Roles like `Support Basic Editor`, `Gemini`, etc., are protected from deletion.
*   **System Sets**: The `Admin` Permission Set and `All` Model Set are protected.

## 🔐 Secret Management

**Crucial**: You must export the necessary environment variables before running the tool.

### Required Looker SDK Variables
*   `LOOKERSDK_BASE_URL`: URL of your Looker instance (e.g., `https://example.looker.com`)
*   `LOOKERSDK_CLIENT_ID`: API Client ID
*   `LOOKERSDK_CLIENT_SECRET`: API Client Secret

### Resource Secrets
Any variable referenced in your YAMLs (e.g., `SNOWFLAKE_PROD_PASSWORD`) must be set in the shell or CI environment.

```bash
export SNOWFLAKE_PROD_PASSWORD="super-secure-password"
export OIDC_CLIENT_SECRET="google-oidc-secret"
```

## 🕹️ Usage

### Plan (Dry Run)
Check what changes *would* be made without executing them. Useful for verifying configuration changes.

```bash
# Check 'dev' environment
python main.py --check --config-dir environments/dev

# Check 'prod' environment
python main.py --check --config-dir environments/prod
```

### Apply (Execute)
Apply the configuration to the Looker instance.

```bash
# Apply to 'dev'
python main.py --apply --config-dir environments/dev
```

## 🧪 Unit Testing

The project includes a comprehensive unit test suite covering `RoleManager`, `ConnectionManager`, and `OIDCManager`.
To run the tests:

```bash
# Run all tests
python -m unittest discover tests
```

## 🤖 CI/CD Pipeline (GitHub Actions)

This repository includes a workflow (`.github/workflows/looker_iac.yml`) that automates the GitOps process using a **Matrix Strategy**.

### Multi-Environment Secrets (Best Practice)
This workflow uses **GitHub Environments** to handle secrets securely and natively.

1.  **Create Environments**:
    *   Go to your GitHub Repository -> **Settings** -> **Environments**.
    *   Create two environments: `dev` and `prod`.

2.  **Add Secrets**:
    *   Click on the `dev` environment.
    *   Add the **same** secret names as below. (Repeat for `prod` with production values).

**Required Secrets (Add to BOTH `dev` and `prod` environments):**
*   `LOOKER_URL`
*   `LOOKER_CLIENT_ID`
*   `LOOKER_CLIENT_SECRET`
*   `SNOWFLAKE_PROD_PASSWORD`
*   `OIDC_CLIENT_SECRET`

**Note**: You do NOT need suffixes like `_DEV` or `_PROD`. GitHub automatically injects the correct secret based on the active environment in the job.

### Workflow Overview
1.  **Pull Request**:
    *   Triggers the **Plan** job.
    *   Runs idempotently for **both** `dev` and `prod` environments in parallel.
    *   Posts a "Diff" comment on the PR detailing exactly what will change.
2.  **Merge to Main**:
    *   Triggers the **Apply** job.
    *   Executes the changes against the respective Looker instances.

### Multi-Environment Setup in CI
The workflow uses a matrix strategy (`[dev, prod]`). Ensure your GitHub Repository Secrets accommodate this.
*   If `dev` and `prod` share the same Looker instance, simple global secrets work.
*   If they are **separate instances**, you will need to update the workflow to select the correct credentials based on `${{ matrix.environment }}` (e.g., reading `LOOKERSDK_BASE_URL_DEV` vs `LOOKERSDK_BASE_URL_PROD`).

## ➕ Adding a New Environment

1.  Create a new directory: `mkdir environments/staging`
2.  Add your YAML configs: `cp environments/dev/*.yaml environments/staging/`
3.  Update `.github/workflows/looker_iac.yml`:
    ```yaml
    strategy:
      matrix:
        environment: [dev, staging, prod]
    ```
