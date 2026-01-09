import logging
import looker_sdk
from looker_sdk import models40 as models

class RoleManager:
    def __init__(self, sdk):
        self.sdk = sdk
        self.perm_set_map = {} # Name -> ID
        self.model_set_map = {} # Name -> ID
        self.role_map = {} # Name -> ID

    def _load_current_state(self):
        """Fetch all existing sets and roles to build ID maps."""
        # Permission Sets
        for ps in self.sdk.all_permission_sets():
            self.perm_set_map[ps.name] = ps.id
        
        # Model Sets
        for ms in self.sdk.all_model_sets():
            self.model_set_map[ms.name] = ms.id
            
        # Roles
        for r in self.sdk.all_roles():
            self.role_map[r.name] = r.id

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
                # Check updates
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
        # NOTE: We can't fully validate Role linkage diffs until IDs are resolved (logic split)
        # But for 'check', we can optimistically assume creation or check existing if mapped.
        for r_cfg in config_data.get('roles', []):
            r_name = r_cfg['name']
            target_ps_name = r_cfg.get('permission_set')
            target_ms_name = r_cfg.get('model_set')
            
            if r_name in self.role_map:
                current_r = self.sdk.role(self.role_map[r_name])
                
                # Compare Names of linked sets (requires fetching the sets attached to role if names aren't in role obj)
                # Role object has permission_set_id and model_set_id
                # We need to reverse lookup ID -> Name to compare nicely, OR fetch the sets.
                # Simplest: Fetch sets by ID from current role
                
                curr_ps_id = current_r.permission_set.id if current_r.permission_set else None
                curr_ms_id = current_r.model_set.id if current_r.model_set else None
                
                # Check mapping (Inverse lookup or fetch)
                # Optimization: We already fetched all sets in _load_current_state, but we only stored Name->ID.
                # Let's trust the ID map we built.
                
                # We need to know if target_ps_name resolves to curr_ps_id
                # BUT, if we are creating new sets, they don't have IDs yet.
                # So for diffing, we assume:
                # If target Set is NEW, Role WILL change.
                # If target Set EXISTS, we check if Role points to it.
                
                # This is tricky in 'check' phase.
                # We can output "Will link to Permission Set 'X'"
                
                # For now, let's just show intent.
                pass
                # Constructing meaningful diff for Roles requires nuanced logic. 
                # Let's defer strict Role diffing to "Compare with current configuration"
                
                # Simple check: Does currently assigned Permission Set Name match target?
                # We need ID -> Name map
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
        
        return diffs

    def apply_changes(self, diffs):
        """Apply changes in dependency order."""
        if not diffs:
            return

        # Reload state to be fresh
        self._load_current_state()
        
        # 1. Apply Permission Sets
        for diff in diffs:
            if diff['action'] == 'CREATE_PERM_SET':
                print(f"Creating Permission Set '{diff['name']}'...")
                cfg = diff['config']
                new_ps = self.sdk.create_permission_set(
                    body=models.PermissionSet(
                        name=cfg['name'],
                        permissions=cfg['permissions']
                    )
                )
                self.perm_set_map[new_ps.name] = new_ps.id # Update map for Roles
                
            elif diff['action'] == 'UPDATE_PERM_SET':
                print(f"Updating Permission Set '{diff['name']}'...")
                cfg = diff['config']
                self.sdk.update_permission_set(
                    permission_set_id=diff['id'],
                    body=models.PermissionSet(
                        permissions=cfg['permissions']
                    )
                )

        # 2. Apply Model Sets
        for diff in diffs:
            if diff['action'] == 'CREATE_MODEL_SET':
                print(f"Creating Model Set '{diff['name']}'...")
                cfg = diff['config']
                new_ms = self.sdk.create_model_set(
                    body=models.ModelSet(
                        name=cfg['name'],
                        models=cfg['models']
                    )
                )
                self.model_set_map[new_ms.name] = new_ms.id # Update map
                
            elif diff['action'] == 'UPDATE_MODEL_SET':
                print(f"Updating Model Set '{diff['name']}'...")
                cfg = diff['config']
                self.sdk.update_model_set(
                    model_set_id=diff['id'],
                    body=models.ModelSet(
                        models=cfg['models']
                    )
                )

        # 3. Apply Roles
        for diff in diffs:
            if diff['action'] in ['CREATE_ROLE', 'UPDATE_ROLE']:
                cfg = diff['config']
                # Resolve IDs now that Sets assume created/updated
                try:
                    ps_id, ms_id = self._resolve_ids(cfg)
                except ValueError as e:
                    print(f"Error resolving dependencies for Role '{cfg['name']}': {e}")
                    continue

                if diff['action'] == 'CREATE_ROLE':
                    print(f"Creating Role '{diff['name']}'...")
                    self.sdk.create_role(
                        body=models.Role(
                            name=cfg['name'],
                            permission_set_id=ps_id,
                            model_set_id=ms_id
                        )
                    )
                elif diff['action'] == 'UPDATE_ROLE':
                    print(f"Updating Role '{diff['name']}'...")
                    self.sdk.update_role(
                        role_id=diff['id'],
                        body=models.Role(
                            permission_set_id=ps_id,
                            model_set_id=ms_id
                        )
                    )
