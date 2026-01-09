from looker_sdk import models40 as models
import os
import copy
from .utils import resolve_secret, format_diff

class ConnectionManager:
    def __init__(self, sdk):
        self.sdk = sdk

    def _map_yaml_to_model(self, config):
        """
        Maps YAML config dict to a WriteDBConnection model.
        Resolves secrets.
        """
        # Create a deep copy to avoid modifying the input
        cfg = copy.deepcopy(config)
        
        # Resolve secrets
        password_var = cfg.pop('password_env_var', None)
        if password_var:
            cfg['password'] = resolve_secret(password_var)
            
        cert_var = cfg.pop('certificate_env_var', None)
        if cert_var:
             cfg['certificate'] = resolve_secret(cert_var) # Example field, verify exact SDK field name for BQ key authentication


        # Remove internal fields not in WriteDBConnection if any
        # name is required
        
        # Convert to model to ensure typing (optional, or just pass dict to create_connection)
        # However, for comparison, we need to know what fields to compare.
        # We will return the dict intended for the SDK.
        return cfg

    def get_diff(self, config_list):
        """
        Returns a list of dicts: {'action': '...', 'name': '...', 'changes': [], 'config': ...}
        """
        diffs = []
        if not config_list:
            return diffs

        for conn_cfg in config_list:
            name = conn_cfg.get('name')
            if not name:
                continue

            target_data = self._map_yaml_to_model(conn_cfg)
            
            # Check existence
            # all_connections returns a list of all connections
            # Optimally we should fetch once, but for simplicity here we fetch per loop or fetch once outside?
            # Fetching once outside is better for performance but requires refactor.
            # Let's fetch per loop for now to match structure, or fetch all if not cached?
            # Actually, let's just use all_connections() and filter.
            all_conns = self.sdk.all_connections(fields="name, host, port, database, schema, dialect_name, username, ssl, max_connections, pool_timeout, uses_application_default_credentials") 
            # Note: specify fields to ensure we get what we need? Or default is all.
            # Default is usually enough.
            
            existing = next((c for c in all_conns if c.name == name), None)
            
            if not existing:
                diffs.append({
                    'action': 'CREATE',
                    'name': name,
                    'changes': ['New connection'],
                    'config': target_data
                })
                continue

            # Compare fields
            changes = []
            
            # Fields to ignore in comparison (e.g. read-only fields or secrets we can't read back)
            ignore_fields = ['password', 'certificate', 'created_at', 'user_id', 'example'] 
            
            # We iterate over TARGET fields. If it's in target, we enforce it.
            for key, target_val in target_data.items():
                if key in ignore_fields:
                    continue
                
                if hasattr(existing, key):
                    current_val = getattr(existing, key)
                    
                    # Normalization
                    # Strings vs Ints (port)
                    if str(current_val) != str(target_val):
                         changes.append(f"{key}: '{current_val}' -> '{target_val}'")
                else:
                    # Looker might accept fields that aren't in the read model?
                    # Or our YAML has extra fields.
                    pass

            # Secret handling logic
            # If password_env_var is present, we assume we MUST apply it if:
            # 1. We differ in other fields (safe to rotate)
            # 2. OR user flags explicit rotation (not implemented yet)
            # 3. For now, we only update password if other things change OR if it's a creation.
            # Wait, if I change the env var CONTENT, valid `password` will differ, but I can't see the current one.
            # Best practice: Don't update password unless requested or connection is new. 
            # OR invalidating it.
            # Let's start with: If there are OTHER changes, we include the password in the update.
            # If there are NO other changes, we assume password is fine.
            # This means to rotate password, one must pretend to change something else or we add a force flag later.
            
            if changes:
                diffs.append({
                    'action': 'UPDATE',
                    'name': name,
                    'changes': changes,
                    'config': target_data, # Includes resolved password
                    'original': existing
                })

        return diffs

    def apply_changes(self, diffs):
        for diff in diffs:
            action = diff['action']
            name = diff['name']
            cfg = diff['config']
            
            if action == 'CREATE':
                print(f"Creating connection '{name}'...")
                # WriteDBConnection expect strict types.
                # SDK's create_connection accepts a WriteDBConnection object or dict (usually object).
                # Let's try passing dict via **cfg but we need to filter unknown keys?
                # Safer to construct the object if possible, or blindly try.
                # 'models.WriteDBConnection' is what we want.
                
                # Filter None values?
                clean_cfg = {k: v for k, v in cfg.items() if v is not None}
                
                try:
                    conn = models.WriteDBConnection(**clean_cfg)
                    self.sdk.create_connection(body=conn)
                    print(f"Success: Created '{name}'")
                except Exception as e:
                    print(f"Failed to create '{name}': {e}")
                    
            elif action == 'UPDATE':
                print(f"Updating connection '{name}'...")
                # Update requires the name usually as path param, and body
                # update_connection(connection_name, body)
                current_name = diff['original'].name # Should be same as name
                
                clean_cfg = {k: v for k, v in cfg.items() if v is not None}
                
                try:
                    conn = models.WriteDBConnection(**clean_cfg)
                    self.sdk.update_connection(connection_name=current_name, body=conn)
                    print(f"Success: Updated '{name}'")
                except Exception as e:
                    print(f"Failed to update '{name}': {e}")
