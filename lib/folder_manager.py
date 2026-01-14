import logging
import looker_sdk
from looker_sdk import models40 as models

class FolderManager:
    def __init__(self, sdk):
        self.sdk = sdk
        self._group_map = None

    def _get_group_map(self):
        if self._group_map is None:
            try:
                all_groups = self.sdk.all_groups()
                self._group_map = {g.name: g.id for g in all_groups}
            except Exception as e:
                logging.warning(f"Error fetching groups: {e}")
                self._group_map = {}
        return self._group_map

    def _resolve_parent_id(self, parent_name):
        """Resolves parent folder name to ID."""
        if not parent_name or parent_name == "Shared":
            return "1"
        if parent_name == "Embed":
            return "cm_embed:1" 
        
        # Search for folder
        try:
            folders = self.sdk.search_folders(name=parent_name)
            if folders:
                return folders[0].id
        except Exception as e:
            logging.warning(f"Error searching for parent folder '{parent_name}': {e}")
        
        return None

    def _get_group_id(self, group_name):
        groups = self._get_group_map()
        
        # Try exact match
        if group_name in groups:
            return groups[group_name]
            
        # Try with (OIDC) suffix
        oidc_name = f"{group_name} (OIDC)"
        if oidc_name in groups:
            return groups[oidc_name]
            
        logging.warning(f"Group '{group_name}' (or '{oidc_name}') not found.")
        return None

    def _get_user_id(self, email):
        try:
             # search_users(email=...) matches
             users = self.sdk.search_users(email=email)
             if users:
                 return users[0].id
        except:
            pass
        return None

    def _build_target_map(self, access_list, folder_name="Unknown"):
        """Converts config access list to a map of {(type, id): permission}."""
        target_map = {}
        for acc in access_list:
            perm = acc.get('permission', 'view')
            gid = self._get_group_id(acc['group']) if 'group' in acc else None
            uid = self._get_user_id(acc['user']) if 'user' in acc else None
            
            if gid:
                target_map[('group', gid)] = perm
            elif uid:
                target_map[('user', uid)] = perm
            else:
                 entity = acc.get('group', acc.get('user', 'Unknown'))
                 logging.warning(f"Entity '{entity}' not found for folder '{folder_name}'.")
        return target_map

    def _get_current_access_map(self, cm_id):
        """Fetches and maps current access rules for a content metadata ID."""
        try:
            accesses = self.sdk.all_content_metadata_accesses(content_metadata_id=cm_id)
            current_map = {}
            for ca in accesses:
                # Store permission as string for safe comparison
                perm_str = str(ca.permission_type.value if hasattr(ca.permission_type, 'value') else ca.permission_type)
                
                if ca.group_id:
                    current_map[('group', ca.group_id)] = {'perm': perm_str, 'id': ca.id}
                elif ca.user_id:
                    current_map[('user', ca.user_id)] = {'perm': perm_str, 'id': ca.id}
            return current_map
        except Exception as e:
            logging.error(f"Error fetching access map (cm_id={cm_id}): {e}")
            return {}

    def get_diff(self, config_list):
        diffs = []
        if not config_list:
            return diffs

        for folder_cfg in config_list:
            name = folder_cfg.get('name')
            
            # Root "Shared" folder special case
            if name == "Shared":
                self._diff_access("1", "Shared", folder_cfg.get('access', []), diffs)
                continue

            parent_name = folder_cfg.get('parent', 'Shared')
            parent_id = self._resolve_parent_id(parent_name)
            
            if not parent_id:
                logging.error(f"Parent '{parent_name}' not found for '{name}'. Skipping.")
                continue

            # Check existence
            folder_id = None
            try:
                # Note: Iterating children is safer than search for hierarchical exactness
                children = self.sdk.folder_children(folder_id=parent_id)
                existing = next((f for f in children if f.name == name), None)
                if existing:
                    folder_id = existing.id
            except Exception as e:
                logging.error(f"Error resolving folder '{name}': {e}")
                continue

            if not folder_id:
                diffs.append({
                    'action': 'CREATE_FOLDER',
                    'name': name,
                    'config': {'name': name, 'parent_id': parent_id},
                    'access_config': folder_cfg.get('access', [])
                })
            else:
                self._diff_access(folder_id, name, folder_cfg.get('access', []), diffs)

        return diffs

    def _diff_access(self, folder_id, folder_name, target_access_list, diffs):
        try:
            folder = self.sdk.folder(folder_id)
            cm_id = folder.content_metadata_id
            if not cm_id: return
            
            # Check Inheritance
            meta = self.sdk.content_metadata(content_metadata_id=cm_id)
            inherits = meta.inherits
            
        except Exception as e:
            logging.error(f"Error parsing folder '{folder_name}': {e}")
            return

        # Explicitly disable inheritance if we are managing access
        if target_access_list and (inherits is not False):
             diffs.append({
                 'action': 'UPDATE_FOLDER_ACCESS',
                 'name': folder_name,
                 'folder_id': folder_id,
                 'metadata_id': cm_id,
                 'changes': [
                     {'action': 'UPDATE_INHERITANCE', 'value': False},
                     {'action': 'SYNC_ACCESS', 'access_list': target_access_list}
                 ]
             })
             return

        # Normal Diff
        current_map = self._get_current_access_map(cm_id)
        target_map = self._build_target_map(target_access_list, folder_name)
        changes = []

        # Updates & Creates
        for (etype, eid), perm in target_map.items():
            key = (etype, eid)
            if key in current_map:
                curr = current_map[key]
                if curr['perm'] != perm:
                    changes.append({
                        'action': 'UPDATE_ACCESS',
                        'type': etype, 
                        'id': eid,
                        'access_id': curr['id'],
                        'from': curr['perm'], 
                        'to': perm
                    })
            else:
                changes.append({'action': 'ADD_ACCESS', 'type': etype, 'id': eid, 'perm': perm})

        # Deletes
        for key, data in current_map.items():
            if key not in target_map:
                 changes.append({
                     'action': 'REMOVE_ACCESS', 
                     'type': key[0], 
                     'id': key[1], 
                     'access_id': data['id']
                 })

        if changes:
             diffs.append({
                 'action': 'UPDATE_FOLDER_ACCESS',
                 'name': folder_name,
                 'folder_id': folder_id,
                 'metadata_id': cm_id,
                 'changes': changes
             })

    def apply_changes(self, diffs):
        for diff in diffs:
            action = diff['action']
            name = diff['name']

            if action == 'CREATE_FOLDER':
                logging.info(f"Creating Folder '{name}'...")
                try:
                    new_folder = self.sdk.create_folder(body=models.CreateFolder(**diff['config']))
                    logging.info(f"Success: Created Folder '{name}' (ID: {new_folder.id})")
                    
                    if diff.get('access_config'):
                        # Initialize access for new folder
                        self._apply_new_folder_access(new_folder.id, name, diff['access_config'])
                except Exception as e:
                    logging.error(f"Failed to create folder: {e}")

            elif action == 'UPDATE_FOLDER_ACCESS':
                logging.info(f"Updating Access for Folder '{name}'...")
                for change in diff['changes']:
                    try:
                        c_action = change['action']
                        
                        if c_action == 'UPDATE_INHERITANCE':
                             self.sdk.update_content_metadata(
                                 content_metadata_id=diff['metadata_id'],
                                 body=models.WriteContentMeta(inherits=change['value'])
                             )
                             logging.info(f"  > Updated Inheritance to {change['value']}")

                        elif c_action == 'SYNC_ACCESS':
                            logging.info(f"  Reconciling Access for '{name}'...")
                            self._reconcile_access(diff['folder_id'], name, change['access_list'])
                        
                        elif c_action == 'ADD_ACCESS':
                            body = models.ContentMetaGroupUser(
                                content_metadata_id=diff['metadata_id'],
                                permission_type=change['perm'],
                                group_id=change['id'] if change['type'] == 'group' else None,
                                user_id=change['id'] if change['type'] == 'user' else None
                            )
                            self.sdk.create_content_metadata_access(body=body)
                            logging.info(f"  + Added {change['type']} {change['id']} ({change['perm']})")
                            
                        elif c_action == 'UPDATE_ACCESS':
                            self.sdk.update_content_metadata_access(
                                content_metadata_access_id=change['access_id'],
                                body=models.ContentMetaGroupUser(permission_type=change['to'])
                            )
                            logging.info(f"  ~ Updated {change['type']} {change['id']} ({change['from']} -> {change['to']})")

                        elif c_action == 'REMOVE_ACCESS':
                             self.sdk.delete_content_metadata_access(content_metadata_access_id=change['access_id'])
                             logging.info(f"  - Removed {change['type']} {change['id']}")

                    except Exception as e:
                        logging.error(f"  ! Failed to apply access change: {e}")

    def _apply_new_folder_access(self, folder_id, folder_name, access_list):
        """Initializes access for a newly created folder."""
        try:
            folder = self.sdk.folder(folder_id)
            
            # 1. Disable Inheritance explicitly
            self.sdk.update_content_metadata(
                 content_metadata_id=folder.content_metadata_id,
                 body=models.WriteContentMeta(inherits=False)
            )
            
            # 2. Reconcile (Add specific access, remove anything copied from parent)
            self._reconcile_access(folder_id, folder_name, access_list)
            
        except Exception as e:
             logging.error(f"Error setting initial access for '{folder_name}': {e}")

    def _reconcile_access(self, folder_id, folder_name, target_access_list):
        """Reconciles access rules from a fresh state (e.g. after inherit break)."""
        try:
            folder = self.sdk.folder(folder_id)
            cm_id = folder.content_metadata_id
        except Exception as e:
            logging.error(f"  ! Error resolving metadata for '{folder_name}': {e}")
            return

        current_map = self._get_current_access_map(cm_id)
        target_map = self._build_target_map(target_access_list, folder_name)

        # Sync Logic
        # 1. Updates
        for (etype, eid), perm in target_map.items():
            if (etype, eid) in current_map:
                curr = current_map[(etype, eid)]
                if curr['perm'] != perm:
                    try:
                        self.sdk.update_content_metadata_access(
                            content_metadata_access_id=curr['id'],
                            body=models.ContentMetaGroupUser(permission_type=perm)
                        )
                        logging.info(f"  ~ Updated {etype} {eid} ({curr['perm']} -> {perm})")
                    except Exception as e:
                        logging.error(f"  ! Failed update: {e}")
            else:
                 # 2. Adds
                 try:
                     self.sdk.create_content_metadata_access(
                         body=models.ContentMetaGroupUser(
                             content_metadata_id=cm_id,
                             permission_type=perm,
                             group_id=eid if etype == 'group' else None,
                             user_id=eid if etype == 'user' else None
                         )
                     )
                     logging.info(f"  + Added {etype} {eid} ({perm})")
                 except Exception as e:
                     logging.error(f"  ! Failed add: {e}")

        # 3. Removes (Extras)
        for key, data in current_map.items():
            if key not in target_map:
                try:
                    self.sdk.delete_content_metadata_access(content_metadata_access_id=data['id'])
                    logging.info(f"  - Removed {key[0]} {key[1]}")
                except Exception as e:
                    logging.error(f"  ! Failed remove: {e}")
