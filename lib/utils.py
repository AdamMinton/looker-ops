import os
import logging
import sys

def setup_logging(level=logging.INFO):
    """Configures the root logger."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout
    )

def resolve_secret(env_var_name: str) -> str:
    """
    Resolves a secret from an environment variable.
    Returns None if the env var is not set.
    """
    if not env_var_name:
        return None
    val = os.environ.get(env_var_name)
    if val is None:
        logging.warning(f"Environment variable '{env_var_name}' is not set.")
    return val

def format_diff(action: str, resource_type: str, resource_name: str, changes: list) -> str:
    """
    Standard formatter for diffs.
    action: 'CREATE', 'UPDATE', 'NO_CHANGE'
    """
    if action.startswith('CREATE'):
        return f"[+] {action} {resource_type} '{resource_name}'" + (f": {changes}" if changes else "")
    elif action.startswith('UPDATE'):
        return f"[~] {action} {resource_type} '{resource_name}':\n    - " + "\n    - ".join(changes.split(', ')) if isinstance(changes, str) else changes
    else:
         return f"    {resource_type} '{resource_name}': No changes ({action})"
