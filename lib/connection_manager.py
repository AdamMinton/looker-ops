from looker_sdk import models40 as models
import logging
import copy
from .utils import resolve_secret

class ConnectionManager:
    def __init__(self, sdk):
        self.sdk = sdk

    def _map_yaml_to_model(self, config):
        """
        Maps YAML config dict to a WriteDBConnection model.
        Resolves secrets.
        """
        cfg = copy.deepcopy(config)
        
        # Resolve secrets
        password_var = cfg.pop('password_env_var', None)
        if password_var:
            cfg['password'] = resolve_secret(password_var)
            
        cert_var = cfg.pop('certificate_env_var', None)
        if cert_var:
             cfg['certificate'] = resolve_secret(cert_var)

        return cfg

    def get_diff(self, config_list):
        """
        Returns a list of dicts: {'action': '...', 'name': '...', 'changes': [], 'config': ...}
        """
        diffs = []
        if not config_list:
            return diffs

        # Fetch all connections once for efficiency
        try:
            all_conns = self.sdk.all_connections(fields="name, host, port, database, schema, dialect_name, username, ssl, max_connections, pool_timeout, uses_application_default_credentials")
        except Exception as e:
            logging.error(f"Failed to fetch connections: {e}")
            return []

        for conn_cfg in config_list:
            name = conn_cfg.get('name')
            if not name:
                continue

            target_data = self._map_yaml_to_model(conn_cfg)
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
            ignore_fields = ['password', 'certificate', 'created_at', 'user_id', 'example']
            
            for key, target_val in target_data.items():
                if key in ignore_fields:
                    continue
                
                if hasattr(existing, key):
                    current_val = getattr(existing, key)
                    if str(current_val) != str(target_val):
                         changes.append(f"{key}: '{current_val}' -> '{target_val}'")

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
            
            clean_cfg = {k: v for k, v in cfg.items() if v is not None}

            if action == 'CREATE':
                logging.info(f"Creating connection '{name}'...")
                try:
                    conn = models.WriteDBConnection(**clean_cfg)
                    self.sdk.create_connection(body=conn)
                    logging.info(f"Success: Created '{name}'")
                except Exception as e:
                    logging.error(f"Failed to create '{name}': {e}")
                    
            elif action == 'UPDATE':
                logging.info(f"Updating connection '{name}'...")
                current_name = diff['original'].name
                
                try:
                    conn = models.WriteDBConnection(**clean_cfg)
                    self.sdk.update_connection(connection_name=current_name, body=conn)
                    logging.info(f"Success: Updated '{name}'")
                except Exception as e:
                    logging.error(f"Failed to update '{name}': {e}")
