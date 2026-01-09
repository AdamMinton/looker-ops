# Looker Infrastructure as Code (IaC)

This repository contains a **GitOps** solution for managing Looker instance configurations. It allows you to define your Looker **Connections** and **OIDC Authentication** settings in YAML files and apply them idempotently to multiple Looker environments (e.g., Development, Production).

## 🚀 Key Features

*   **Idempotency**: The tool compares your local YAML configuration against the actual Looker instance state. It only triggers API calls when a legitimate change is detected.
*   **Multi-Environment Support**: Manage disjoint environments (e.g., `dev`, `prod`) with separate configuration trees while sharing the same management logic.
*   **Secure**: Secrets (passwords, private keys) are **never** stored in plain text. They are referenced by Environment Variable names in the configuration and resolved at runtime.
*   **CI/CD Integrated**: Designed to run within GitHub Actions, providing "Plan" (PR comments) and "Apply" (Merge to Main) workflows.

## 📂 Project Structure

```text
looker-ops/
├── main.py                        # CLI Entrypoint
├── lib/                           # Core Logic
│   ├── connection_manager.py      # Diff/Apply logic for Database Connections
│   ├── oidc_manager.py            # Diff/Apply logic for OIDC Auth
│   └── utils.py                   # Helper functions (Config parsing, Secret resolution)
├── environments/                  # Environment-specific Configurations
│   ├── dev/
│   │   ├── connections.yaml
│   │   └── oidc.yaml
│   └── prod/
│       ├── connections.yaml
│       └── oidc.yaml
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
```

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
