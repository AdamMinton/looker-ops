import os

def resolve_secret(env_var_name: str) -> str:
    """
    Resolves a secret from an environment variable.
    Returns None if the env var is not set, which might be okay for dry runs 
    if we just want to flag it, but for apply we need it.
    """
    if not env_var_name:
        return None
    val = os.environ.get(env_var_name)
    if val is None:
        print(f"WARNING: Environment variable '{env_var_name}' is not set.")
    return val

def format_diff(action: str, resource_type: str, resource_name: str, changes: list) -> str:
    """
    Standard formatter for diffs.
    action: 'CREATE', 'UPDATE', 'NO_CHANGE'
    """
    if action == 'CREATE':
        return f"[+] CREATE {resource_type} '{resource_name}'"
    elif action == 'UPDATE':
        return f"[~] UPDATE {resource_type} '{resource_name}':\n    - " + "\n    - ".join(changes)
    else:
         return f"    {resource_type} '{resource_name}': No changes"
