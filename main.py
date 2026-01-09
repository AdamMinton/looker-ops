import argparse
import sys
import os
import yaml
import looker_sdk
from lib.connection_manager import ConnectionManager
from lib.oidc_manager import OIDCManager

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

    # Initialize SDK
    # We assume looker.ini is in the current directory or env vars are set
    # Using 'test' section based on verification step, but arguably this should be configurable or default
    # For now, let's try to use the default 'Looker' section if available, else 'test', or env vars.
    # Actually, let's allow it to be flexible. Init40 with no args uses default behavior (env vars > looker.ini[Looker])
    # But since we know it is 'test' locally... let's check env var for section?
    # Or just use "looker.ini" and let it pick up env vars if set.
    # The user environment seems to rely on looker.ini having [test].
    # We can assume the user runs this with `LOOKERSDK_SECTION=test` or we hardcode looking for 'test' if verify succeded with it?
    # Better: Try to use [Test] if it exists, otherwise Default.
    # For now, I will use `looker_sdk.init40()` which follows standard lookup. 
    # NOTE: verify_api.py showed we needed section="test".
    
    try:
        # Try finding a section from env or default to 'test' if we are local?
        # Actually standard practice is LOOKERSDK_SECTION env var.
        section = os.environ.get("LOOKERSDK_SECTION")
        if not section:
             # Basic fallback logic? Or just let init40 fail if it can't find default?
             # Let's try to be smart like verify_api.py or just rely on 'looker.ini' default lookup
             # If I pass nothing, it looks for [Looker].
             pass
        
        # We will try to init. If it fails and we are local, maybe we hint?
        # Let's use the explicit 'test' section if we are in this specific repo context? 
        # No, that's brittle.
        # I'll stick to standard init40(). The user can export LOOKERSDK_SECTION=test
        sdk = looker_sdk.init40()
    except Exception as e:
        # Fallback for this specific user scenario if standard init fails?
        # We know 'test' works.
        try:
             sdk = looker_sdk.init40(config_file="looker.ini", section="test")
        except:
             print(f"Failed to initialize Looker SDK: {e}")
             sys.exit(1)

    print(f"Connected to Looker API: {sdk.auth.settings.base_url}")

    # Load Configs
    connections_path = os.path.join(args.config_dir, 'connections.yaml')
    oidc_path = os.path.join(args.config_dir, 'oidc.yaml')
    
    connections_config = load_config(connections_path) if os.path.exists(connections_path) else []
    oidc_config = load_config(oidc_path) if os.path.exists(oidc_path) else None

    # Managers
    conn_manager = ConnectionManager(sdk)
    oidc_manager = OIDCManager(sdk)

    # Execution
    print("\n--- Connection Management ---")
    conn_diff = conn_manager.get_diff(connections_config)
    if not conn_diff:
        print("No changes detected for Connections.")
    else:
        for item in conn_diff:
            # Use utils formatter or custom print
            from lib.utils import format_diff
            print(format_diff(item['action'], 'Connection', item['name'], item['changes']))
        
        if args.apply:
            print("Applying Connection changes...")
            conn_manager.apply_changes(conn_diff)

    # OIDC Management
    if oidc_config:
        print("\n--- OIDC Management ---")
        # OIDC Manager will need similar refactoring to return structured diffs
        # For now, if OIDCManager returns strings, this might break. 
        # I will update OIDCManager next.
        oidc_diff = oidc_manager.get_diff(oidc_config)
        if not oidc_diff:
            print("No changes detected for OIDC.")
        else:
            # Assuming OIDCManager is also refactored
             if isinstance(oidc_diff[0], dict):
                 for item in oidc_diff:
                      from lib.utils import format_diff
                      print(format_diff(item['action'], 'OIDC Config', 'Global', item['changes']))
                 
                 if args.apply:
                    print("Applying OIDC changes...")
                    oidc_manager.apply_changes(oidc_diff)
             else:
                 # Legacy string support if I don't update it in time
                 for change in oidc_diff:
                     print(change)

if __name__ == "__main__":
    main()
