import argparse
import sys
import os
import yaml
import looker_sdk
import logging
from lib.connection_manager import ConnectionManager
from lib.oidc_manager import OIDCManager
from lib.role_manager import RoleManager
from lib.utils import setup_logging, format_diff

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description="Looker Infrastructure as Code (IaC)")
    parser.add_argument('--check', action='store_true', help="Plan mode: Check for changes without applying")
    parser.add_argument('--apply', action='store_true', help="Apply mode: Execute changes")
    parser.add_argument('--config-dir', default='config', help="Directory containing configuration YAMLs")
    
    args = parser.parse_args()

    if not args.check and not args.apply:
        print("Error: Must specify either --check or --apply")
        sys.exit(1)

    setup_logging()

    try:
        sdk = looker_sdk.init40()
    except Exception as e:
        # Fallback for 'test' section if standard init fails, commonly used in local dev
        try:
             sdk = looker_sdk.init40(config_file="looker.ini", section="test")
        except:
             logging.critical(f"Failed to initialize Looker SDK: {e}")
             sys.exit(1)

    logging.info(f"Connected to Looker API: {sdk.auth.settings.base_url}")

    # Load Configs
    connections_path = os.path.join(args.config_dir, 'connections.yaml')
    oidc_path = os.path.join(args.config_dir, 'oidc.yaml')
    roles_path = os.path.join(args.config_dir, 'roles.yaml')
    
    connections_config = load_config(connections_path) if os.path.exists(connections_path) else []
    oidc_config = load_config(oidc_path) if os.path.exists(oidc_path) else None
    
    roles_config = None
    if os.path.exists(roles_path):
        with open(roles_path, "r") as f:
            roles_config = yaml.safe_load(f)

    # Managers
    conn_manager = ConnectionManager(sdk)
    oidc_manager = OIDCManager(sdk)
    role_mgr = RoleManager(sdk)

    # Execution

    # 1. Connection Management
    print("\n--- Connection Management ---")
    conn_diff = conn_manager.get_diff(connections_config)
    if not conn_diff:
        print("No changes detected for Connections.")
    else:
        for item in conn_diff:
            print(format_diff(item['action'], 'Connection', item['name'], item['changes']))

    # 2. OIDC Management
    oidc_diff = []
    if oidc_config:
        print("\n--- OIDC Management ---")
        oidc_diff = oidc_manager.get_diff(oidc_config)
        if not oidc_diff:
            print("No changes detected for OIDC.")
        else:
            if oidc_diff and isinstance(oidc_diff[0], dict):
                 for item in oidc_diff:
                      print(format_diff(item['action'], 'OIDC Config', 'Global', item['changes']))
            else:
                 for change in oidc_diff:
                     print(change)

    # 3. Roles Management
    print("\n--- Roles Management ---")
    roles_diff = []
    
    if roles_config:
        roles_diff = role_mgr.get_diff(roles_config)
        if not roles_diff:
            print("No changes detected for Roles.")
        else:
             for item in roles_diff:
                rtype = 'Role'
                if 'PERM_SET' in item['action']:
                    rtype = 'Permission Set'
                elif 'MODEL_SET' in item['action']:
                    rtype = 'Model Set'
                
                print(format_diff(item['action'], rtype, item['name'], item['changes']))

    # APPLY PHASE
    if args.apply:
        print("\n=== Applying Changes ===")
        if conn_diff:
            logging.info("Applying Connection changes...")
            conn_manager.apply_changes(conn_diff)
        
        if oidc_diff:
            logging.info("Applying OIDC changes...")
            oidc_manager.apply_changes(oidc_diff)
            
        if roles_diff:
            logging.info("Applying Roles changes...")
            role_mgr.apply_changes(roles_diff)
    else:
        print("\nRun with --apply to execute changes.")

if __name__ == "__main__":
    main()
