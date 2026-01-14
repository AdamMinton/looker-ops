import logging

class Validator:
    def __init__(self, sdk, roles_config, oidc_config, connections_config, projects_config, folders_config=None):
        self.sdk = sdk
        self.roles_config = roles_config or {}
        self.oidc_config = oidc_config or {}
        self.connections_config = connections_config or []
        self.projects_config = projects_config or {}
        self.folders_config = folders_config or []
        
        # Protected/System sets that always exist or are managed outside this tool
        self.PROTECTED_PERM_SETS = {
            'Admin', 
            'Support Basic Editor', 
            'Support Advanced Editor', 
            'Customer Engineer Advanced Editor', 
            'Gemini',
            'LookML Dashboard User', 
            'User who can\'t view LookML'
        }
        self.PROTECTED_MODEL_SETS = {'All'}
        self.PROTECTED_ROLES = {'Admin', 'Developer', 'User', 'Viewer'} # Basic Looker Roles

    def validate(self):
        """Orchestrates all validations. Raises ValueError if any fail."""
        errors = []
        
        # 1. Validate Permissions (API Check)
        errors.extend(self._validate_permissions())

        # 2. Validate Role Dependencies (Internal Referencing)
        errors.extend(self._validate_role_dependencies())
        
        # 3. Validate OIDC Groups (Role Referencing)
        errors.extend(self._validate_oidc_groups())
        
        # 4. Validate Project Connections (Connection Referencing)
        errors.extend(self._validate_project_connections())

        # 5. Validate Folder Access (User/Group Existence)
        errors.extend(self._validate_folder_access())
        
        if errors:
            error_msg = "\n".join([f"- {e}" for e in errors])
            raise ValueError(f"Configuration Validation Failed:\n{error_msg}")
            
        logging.info("Configuration validation passed.")

    def _validate_permissions(self):
        errors = []
        if not self.roles_config:
            return errors
            
        try:
            all_perms = self.sdk.all_permissions()
            valid_perm_names = {p.permission for p in all_perms}
        except Exception as e:
            logging.warning(f"Skipping permission validation due to API error: {e}")
            return []

        for ps in self.roles_config.get('permission_sets', []):
            for perm in ps.get('permissions', []):
                if perm not in valid_perm_names:
                    errors.append(f"Invalid permission '{perm}' in Permission Set '{ps.get('name')}'")
        return errors

    def _validate_role_dependencies(self):
        errors = []
        if not self.roles_config:
            return errors

        # Collect defined sets
        defined_perm_sets = {ps['name'] for ps in self.roles_config.get('permission_sets', [])}
        defined_model_sets = {ms['name'] for ms in self.roles_config.get('model_sets', [])}

        # Check Roles
        for role in self.roles_config.get('roles', []):
            role_name = role.get('name')
            target_ps = role.get('permission_set')
            target_ms = role.get('model_set')

            # Skip checking dependencies for Admin role as it's often special
            if role_name == 'Admin':
                continue

            if target_ps and target_ps not in defined_perm_sets and target_ps not in self.PROTECTED_PERM_SETS:
                errors.append(f"Role '{role_name}' references undefined Permission Set '{target_ps}'")
            
            if target_ms and target_ms not in defined_model_sets and target_ms not in self.PROTECTED_MODEL_SETS:
                errors.append(f"Role '{role_name}' references undefined Model Set '{target_ms}'")
        
        return errors

    def _validate_oidc_groups(self):
        errors = []
        if not self.oidc_config:
            return errors
            
        # Get all valid roles (YAML + System)
        # Note: We can't easily query ALL system roles without an API call, 
        # but we can check against what we know is managed.
        # Ideally, we should fetch all roles from API to be sure, but let's strictly enforce YAML definition for managed roles.
        
        # Strategy: Checks against YAML defined roles OR a fetch of all roles if strictness allows.
        # For now, let's fetch actual roles from API to be safe, as OIDC might reference existing roles not in YAML.
        
        try:
             all_looker_roles = self.sdk.all_roles()
             valid_role_names = {r.name for r in all_looker_roles}
        except Exception as e:
             logging.warning(f"Could not fetch roles for OIDC validation: {e}")
             return []

        # Also add roles defined in current YAML (in case they haven't been created yet)
        if self.roles_config:
            for r in self.roles_config.get('roles', []):
                valid_role_names.add(r['name'])

        groups = self.oidc_config.get('mirrored_groups', [])
        for g in groups:
            for role_name in g.get('roles', []):
                if role_name not in valid_role_names:
                    errors.append(f"OIDC Group '{g.get('name')}' references unknown Role '{role_name}'")

        return errors

    def _validate_project_connections(self):
        errors = []
        config_projects = self.projects_config.get('projects', [])
        if not config_projects:
            return errors

        # Gather Config Connections
        config_conn_names = set()
        if self.connections_config:
            config_conn_names = {c.get('name') for c in self.connections_config}
        
        # Gather Existing Connections
        try:
            all_conns = self.sdk.all_connections(fields="name")
            existing_conn_names = {c.name for c in all_conns}
        except Exception as e:
             logging.warning(f"Could not fetch connections for project validation: {e}")
             return []

        all_valid_conns = config_conn_names.union(existing_conn_names)

        for proj in config_projects:
            for model in proj.get('models', []):
                for conn_name in model.get('connection_names', []):
                    if conn_name not in all_valid_conns:
                        errors.append(f"Model '{model.get('model_name')}' references unknown Connection '{conn_name}'")
        
        return errors

    def _validate_folder_access(self):
        errors = []
        if not self.folders_config:
            return errors

        # Cache Groups
        try:
             all_groups = self.sdk.all_groups()
             group_map = {g.name for g in all_groups}
             
             # Also allow groups defined in OIDC Config (they might be created by login)
             if self.oidc_config:
                 for g in self.oidc_config.get('mirrored_groups', []):
                     group_map.add(g.get('name'))

        except Exception as e:
             logging.warning(f"Could not fetch groups for folder validation: {e}")
             return []

        # We can't easily cache ALL users efficiently if there are thousands.
        # But we can check individual users or skip if too many?
        # For now, let's look up users dynamically or assume validation 
        # is critical enough to pay the API cost (one search per user).
        # Actually validation happens before execution, so let's try to be smart.
        # We can collect all emails and search, but search is single.
        # Let's trust the logic: If it looks like an email, we check it.
        
        for folder in self.folders_config:
            for acc in folder.get('access', []):
                if 'group' in acc:
                    g_name = acc['group']
                    if g_name not in group_map:
                         # Also check if it's a mirrored group defined in OIDC that doesn't exist yet?
                         # Or a Role-Group? 
                         # Usually we expect Groups to exist.
                         errors.append(f"Folder '{folder.get('name')}' references unknown Group '{g_name}'")
                
                if 'user' in acc:
                    u_email = acc['user']
                    # Verify user exists
                    try:
                        found = self.sdk.search_users(email=u_email)
                        if not found:
                             errors.append(f"Folder '{folder.get('name')}' references unknown User '{u_email}'")
                    except:
                        pass
        return errors
