import logging
import looker_sdk
from looker_sdk import models40 as models

class RoleManager:
    def __init__(self, sdk):
        self.sdk = sdk
        self.perm_set_map = {} # Name -> ID
        self.model_set_map = {} # Name -> ID
        self.role_map = {} # Name -> ID
        self.role_objects = {} # Name -> Role Object

    def _load_current_state(self):
        """Fetch all existing sets and roles to build ID maps."""
        for ps in self.sdk.all_permission_sets():
            self.perm_set_map[ps.name] = ps.id
        
        for ms in self.sdk.all_model_sets():
            self.model_set_map[ms.name] = ms.id
            
        for r in self.sdk.all_roles():
            self.role_map[r.name] = r.id
            self.role_objects[r.name] = r

    def _resolve_ids(self, role_config):
        """Resolve Permission Set and Model Set Names to IDs."""
        perm_set_name = role_config.get('permission_set')
        model_set_name = role_config.get('model_set')
        
        perm_set_id = self.perm_set_map.get(perm_set_name)
        model_set_id = self.model_set_map.get(model_set_name)
        
        if not perm_set_id:
            raise ValueError(f"Permission Set '{perm_set_name}' not found for Role '{role_config.get('name')}'. Define it in permission_sets first.")
        
        if not model_set_id:
            raise ValueError(f"Model Set '{model_set_name}' not found for Role '{role_config.get('name')}'. Define it in model_sets first.")
            
        return perm_set_id, model_set_id

    def get_diff(self, config_data):
        """Calculate diffs for Permission Sets, Model Sets, and Roles."""
        diffs = []
        if not config_data:
            return diffs
            
        self._load_current_state()
        
        # 1. Permission Sets
        for ps_cfg in config_data.get('permission_sets', []):
            ps_name = ps_cfg['name']
            target_perms = sorted(ps_cfg['permissions'])
            
            if ps_name in self.perm_set_map:
                current_ps = self.sdk.permission_set(self.perm_set_map[ps_name])
                current_perms = sorted(current_ps.permissions or [])
                
                if current_perms != target_perms:
                    diffs.append({
                        'action': 'UPDATE_PERM_SET',
                        'name': ps_name,
                        'id': self.perm_set_map[ps_name],
                        'changes': f"Permissions: {current_perms} -> {target_perms}",
                        'config': ps_cfg
                    })
            else:
                diffs.append({
                    'action': 'CREATE_PERM_SET',
                    'name': ps_name,
                    'changes': f"New Permission Set with {target_perms}",
                    'config': ps_cfg
                })

        # 2. Model Sets
        for ms_cfg in config_data.get('model_sets', []):
            ms_name = ms_cfg['name']
            target_models = sorted(ms_cfg['models'])
            
            if ms_name in self.model_set_map:
                current_ms = self.sdk.model_set(self.model_set_map[ms_name])
                current_models = sorted(current_ms.models or [])
                
                if current_models != target_models:
                    diffs.append({
                        'action': 'UPDATE_MODEL_SET',
                        'name': ms_name,
                        'id': self.model_set_map[ms_name],
                        'changes': f"Models: {current_models} -> {target_models}",
                        'config': ms_cfg
                    })
            else:
                diffs.append({
                    'action': 'CREATE_MODEL_SET',
                    'name': ms_name,
                    'changes': f"New Model Set with {target_models}",
                    'config': ms_cfg
                })

        # 3. Roles
        for r_cfg in config_data.get('roles', []):
            r_name = r_cfg['name']
            target_ps_name = r_cfg.get('permission_set')
            target_ms_name = r_cfg.get('model_set')
            
            if r_name in self.role_objects:
                current_r = self.role_objects[r_name]
                
                curr_ps_id = current_r.permission_set.id if current_r.permission_set else None
                curr_ms_id = current_r.model_set.id if current_r.model_set else None
                
                id_to_perm_name = {v: k for k, v in self.perm_set_map.items()}
                id_to_model_name = {v: k for k, v in self.model_set_map.items()}
                
                curr_ps_name = id_to_perm_name.get(curr_ps_id, f"Unknown ID {curr_ps_id}")
                curr_ms_name = id_to_model_name.get(curr_ms_id, f"Unknown ID {curr_ms_id}")
                
                changes = []
                if curr_ps_name != target_ps_name:
                    changes.append(f"Permission Set: '{curr_ps_name}' -> '{target_ps_name}'")
                if curr_ms_name != target_ms_name:
                    changes.append(f"Model Set: '{curr_ms_name}' -> '{target_ms_name}'")
                
                if changes:
                    # SAFETY CHECK for Admin
                    if r_name == 'Admin':
                         logging.warning(f"Skipping update for protected Role 'Admin'. Detected changes: {changes}")
                         continue
                        
                    diffs.append({
                        'action': 'UPDATE_ROLE',
                        'name': r_name,
                        'id': self.role_map[r_name],
                        'changes': ", ".join(changes),
                        'config': r_cfg
                    })

            else:
                 diffs.append({
                    'action': 'CREATE_ROLE',
                    'name': r_name,
                    'changes': f"New Role linking '{target_ps_name}' and '{target_ms_name}'",
                    'config': r_cfg
                })
        
        # 4. Deletions (Reverse Order of Dependencies for safety, but we calculate them here)
        # We need to delete Roles first, then Sets.
        
        # 4a. Identify Extra Roles
        config_role_names = {r['name'] for r in config_data.get('roles', [])}
        for role_name, role_id in self.role_map.items():
            if role_name not in config_role_names:
                # SAFETY CHECKS
                if role_name == 'Admin':
                    logging.info(f"Skipping deletion of protected Role 'Admin'")
                    continue
                
                # Fallback: Explicit Name Check for Support Roles 
                # (SDK V4.0 Model does not expose 'is_support_role' attribute despite API returning it)
                PROTECTED_SUPPORT_ROLES = {
                    'Support Basic Editor',
                    'Support Advanced Editor',
                    'Customer Engineer Advanced Editor',
                    'Helpdesk User',
                    'Gemini'
                }
                
                if role_name in PROTECTED_SUPPORT_ROLES:
                    logging.info(f"Skipping deletion of protected Support Role '{role_name}'")
                    continue
                
                # If we somehow don't have the object but have the ID (unlikely), safe default?
                # current logic assumes we have it.
                
                diffs.append({
                    'action': 'DELETE_ROLE',
                    'name': role_name,
                    'id': role_id,
                    'changes': 'Role removed from configuration'
                })

        # 4b. Identify Extra Permission Sets
        PROTECTED_PERM_SETS = {
            'Admin', 
            'Support Basic Editor', 
            'Support Advanced Editor', 
            'Customer Engineer Advanced Editor', 
            'Gemini',
            'LookML Dashboard User', # Often system-like
            'User who can\'t view LookML', # Often system-like
            # Add others if needed
        }
        config_perm_names = {p['name'] for p in config_data.get('permission_sets', [])}
        for ps_name, ps_id in self.perm_set_map.items():
            if ps_name not in config_perm_names:
                if ps_name in PROTECTED_PERM_SETS:
                    logging.info(f"Skipping deletion of protected Permission Set '{ps_name}'")
                    continue
                
                diffs.append({
                    'action': 'DELETE_PERM_SET',
                    'name': ps_name,
                    'id': ps_id,
                    'changes': 'Permission Set removed from configuration'
                })

        # 4c. Identify Extra Model Sets
        config_model_names = {m['name'] for m in config_data.get('model_sets', [])}
        for ms_name, ms_id in self.model_set_map.items():
            if ms_name not in config_model_names:
                if ms_name == 'All':
                     logging.info(f"Skipping deletion of protected Model Set '{ms_name}'")
                     continue
                
                diffs.append({
                    'action': 'DELETE_MODEL_SET',
                    'name': ms_name,
                    'id': ms_id,
                    'changes': 'Model Set removed from configuration'
                })
        
        return diffs

    def apply_changes(self, diffs):
        """Apply changes in dependency order."""
        if not diffs:
            return

        # Reload state to be fresh
        self._load_current_state()
        
        # 0. DELETE ROLES (First, to free up sets)
        for diff in diffs:
            if diff['action'] == 'DELETE_ROLE':
                logging.warning(f"DELETING Role '{diff['name']}'...")
                self.sdk.delete_role(role_id=diff['id'])

        # 1. DELETE SETS (Only after roles are gone)
        for diff in diffs:
            if diff['action'] == 'DELETE_PERM_SET':
                 logging.warning(f"DELETING Permission Set '{diff['name']}'...")
                 try:
                    self.sdk.delete_permission_set(permission_set_id=diff['id'])
                 except Exception as e:
                    logging.error(f"Failed to delete Permission Set '{diff['name']}': {e}")
            
            if diff['action'] == 'DELETE_MODEL_SET':
                 logging.warning(f"DELETING Model Set '{diff['name']}'...")
                 try:
                    self.sdk.delete_model_set(model_set_id=diff['id'])
                 except Exception as e:
                    logging.error(f"Failed to delete Model Set '{diff['name']}': {e}")

        # 2. Apply Permission Sets (Creates/Updates)
        for diff in diffs:
            if diff['action'] == 'CREATE_PERM_SET':
                logging.info(f"Creating Permission Set '{diff['name']}'...")
                cfg = diff['config']
                new_ps = self.sdk.create_permission_set(
                    body=models.PermissionSet(
                        name=cfg['name'],
                        permissions=cfg['permissions']
                    )
                )
                self.perm_set_map[new_ps.name] = new_ps.id
                
            elif diff['action'] == 'UPDATE_PERM_SET':
                logging.info(f"Updating Permission Set '{diff['name']}'...")
                cfg = diff['config']
                self.sdk.update_permission_set(
                    permission_set_id=diff['id'],
                    body=models.PermissionSet(
                        permissions=cfg['permissions']
                    )
                )

        # 3. Apply Model Sets (Creates/Updates)
        for diff in diffs:
            if diff['action'] == 'CREATE_MODEL_SET':
                logging.info(f"Creating Model Set '{diff['name']}'...")
                cfg = diff['config']
                new_ms = self.sdk.create_model_set(
                    body=models.ModelSet(
                        name=cfg['name'],
                        models=cfg['models']
                    )
                )
                self.model_set_map[new_ms.name] = new_ms.id
                
            elif diff['action'] == 'UPDATE_MODEL_SET':
                logging.info(f"Updating Model Set '{diff['name']}'...")
                cfg = diff['config']
                self.sdk.update_model_set(
                    model_set_id=diff['id'],
                    body=models.ModelSet(
                        models=cfg['models']
                    )
                )

        # 4. Apply Roles (Creates/Updates)
        for diff in diffs:
            if diff['action'] in ['CREATE_ROLE', 'UPDATE_ROLE']:
                cfg = diff['config']
                try:
                    ps_id, ms_id = self._resolve_ids(cfg)
                except ValueError as e:
                    logging.error(f"Error resolving dependencies for Role '{cfg['name']}': {e}")
                    continue

                if diff['action'] == 'CREATE_ROLE':
                    logging.info(f"Creating Role '{diff['name']}'...")
                    self.sdk.create_role(
                        body=models.Role(
                            name=cfg['name'],
                            permission_set_id=ps_id,
                            model_set_id=ms_id
                        )
                    )
                elif diff['action'] == 'UPDATE_ROLE':
                    logging.info(f"Updating Role '{diff['name']}'...")
                    self.sdk.update_role(
                        role_id=diff['id'],
                        body=models.Role(
                            permission_set_id=ps_id,
                            model_set_id=ms_id
                        )
                    )
