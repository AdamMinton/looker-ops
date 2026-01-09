from looker_sdk import models40 as models
import copy
from .utils import resolve_secret

class OIDCManager:
    def __init__(self, sdk):
        self.sdk = sdk

    def _map_yaml_to_model(self, config):
        cfg = copy.deepcopy(config)
        
        # Map client_id -> identifier
        if 'client_id' in cfg:
            cfg['identifier'] = cfg.pop('client_id')

        # Map client_secret_env_var -> secret
        secret_var = cfg.pop('client_secret_env_var', None)
        if secret_var:
             cfg['secret'] = resolve_secret(secret_var)
        
        # Flatten user_attribute_map
        # API expects user_attribute_map_email, etc.
        attr_map = cfg.pop('user_attribute_map', None)
        if attr_map and isinstance(attr_map, dict):
            # Only map known fields to avoid TypeError in OIDCConfig
            allowed_attrs = ['email', 'first_name', 'last_name']
            for k, v in attr_map.items():
                if k in allowed_attrs:
                     cfg[f'user_attribute_map_{k}'] = v
                # Custom attributes handling would differ (likely user_attributes_with_ids)
                # For now, we ignore unknown keys to prevent crashes.

        # Remove unsupported fields
        cfg.pop('display_name', None) # Not supported in OIDCConfig
        cfg.pop('client_secret', None) # Ensure we don't pass this if it was in yaml
             
        return cfg

    def get_diff(self, config):
        diffs = []
        if not config:
            return diffs
        
        target_data = self._map_yaml_to_model(config)
        
        # Fetch current
        try:
            current = self.sdk.oidc_config()
        except Exception as e:
            # If failed, return error as a diff for now
            print(f"Error fetching OIDC config: {e}")
            return []

        # Compare
        changes = []
        ignore_fields = ['secret', 'url', 'can', 'modified_at', 'modified_by'] # url/can/modified are SDK/system fields
        
        for key, target_val in target_data.items():
             if key in ignore_fields: continue
             
             if hasattr(current, key):
                 current_val = getattr(current, key)
                 
                 if key == 'scopes':
                     # Sort scopes for consistent string comparison
                     if isinstance(target_val, list) and isinstance(current_val, list):
                         target_val = sorted(target_val)
                         current_val = sorted(current_val)

                 if str(current_val) != str(target_val):
                     changes.append(f"{key}: '{current_val}' -> '{target_val}'")
        
        # Secret handling
        # Only update secret if explicitly needed or if other things changed?
        # OIDC config update is a singleton update.
        # If we have changes, we apply them.
        
        if changes:
            diffs.append({
                'action': 'UPDATE',
                'name': 'OIDC Configuration',
                'changes': changes,
                'config': target_data
            })

        return diffs

    def apply_changes(self, diffs):
        for diff in diffs:
            if diff['action'] == 'UPDATE':
                print("Updating OIDC Configuration...")
                cfg = diff['config']
                # clean cfg?
                clean_cfg = {k: v for k, v in cfg.items() if v is not None}
                
                try:
                    conf = models.OIDCConfig(**clean_cfg)
                    self.sdk.update_oidc_config(body=conf)
                    print("Success: Updated OIDC Config")
                except Exception as e:
                    print(f"Failed to update OIDC Config: {e}")
