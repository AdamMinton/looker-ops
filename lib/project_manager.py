from looker_sdk import models40 as models
import logging
import copy

class ProjectManager:
    def __init__(self, sdk):
        self.sdk = sdk

    def get_diff(self, config_list):
        """
        Returns a list of diffs for Projects and LOOKML Models.
        config_list is expected to be a list of project dicts from YAML.
        """
        diffs = []
        if not config_list:
            return diffs

        # Ensure we are in developer mode to see all projects (especially those not pushed to prod)
        try:
            self.sdk.update_session(body=models.WriteApiSession(workspace_id="dev"))
        except Exception as e:
            logging.warning(f"Failed to switch to 'dev' workspace in get_diff: {e}")

        # Fetch all existing resources once
        try:
            # We need minimal fields for existence checks
            all_projects = self.sdk.all_projects(fields="id, name")
            all_models = self.sdk.all_lookml_models(fields="name, project_name, allowed_db_connection_names")
        except Exception as e:
            logging.error(f"Failed to fetch existing projects or models: {e}")
            return []

        existing_projects_map = {p.id: p for p in all_projects}
        existing_models_map = {m.name: m for m in all_models}

        for proj_cfg in config_list:
            project_name = proj_cfg.get('name')
            if not project_name:
                continue

            # 1. Project Diff
            if project_name not in existing_projects_map:
                diffs.append({
                    'action': 'CREATE_PROJECT',
                    'name': project_name,
                    'changes': ['New Project'],
                    'config': {'name': project_name}
                })
            else:
                # We strictly only manage creation of projects, not updates to settings
                # per requirements ("ignoring all other admin settings")
                pass

            # 2. Models Diff
            models_cfg = proj_cfg.get('models', [])
            for model_cfg in models_cfg:
                model_name = model_cfg.get('model_name')
                if not model_name:
                    continue

                target_connections = model_cfg.get('connection_names', [])
                # Sort for stable comparison
                target_connections.sort()

                target_model_data = {
                    "name": model_name,
                    "project_name": project_name,
                    "allowed_db_connection_names": target_connections
                }

                if model_name not in existing_models_map:
                    diffs.append({
                        'action': 'CREATE_MODEL',
                        'name': model_name,
                        'changes': ['New Model'],
                        'config': target_model_data
                    })
                else:
                    existing_model = existing_models_map[model_name]
                    changes = []
                    
                    # Check project linkage
                    if existing_model.project_name != project_name:
                        changes.append(f"project_name: '{existing_model.project_name}' -> '{project_name}'")

                    # Check connections
                    current_conns = existing_model.allowed_db_connection_names or []
                    current_conns.sort()
                    
                    if current_conns != target_connections:
                        changes.append(f"allowed_db_connection_names: {current_conns} -> {target_connections}")

                    if changes:
                        diffs.append({
                            'action': 'UPDATE_MODEL',
                            'name': model_name,
                            'changes': changes,
                            'config': target_model_data,
                            'original': existing_model
                        })

        # Revert to production workspace to leave SDK in clean state
        try:
             self.sdk.update_session(body=models.WriteApiSession(workspace_id="production"))
        except:
             pass

        return diffs

    def apply_changes(self, diffs):
        # Ensure we are in developer mode to create/edit projects
        try:
            self.sdk.update_session(body=models.WriteApiSession(workspace_id="dev"))
            logging.info("Switched to 'dev' workspace.")
        except Exception as e:
            logging.warning(f"Failed to switch to 'dev' workspace: {e}")

        for diff in diffs:
            action = diff['action']
            name = diff['name']
            cfg = diff['config']
            
            clean_cfg = {k: v for k, v in cfg.items() if v is not None}

            if action == 'CREATE_PROJECT':
                logging.info(f"Creating Project '{name}'...")
                try:
                    # Looker API create_project uses 'id' as the Project ID.
                    # Per spec: "id": Use the name from the YAML
                    project = models.WriteProject(**clean_cfg)
                    self.sdk.create_project(body=project)
                    logging.info(f"Success: Created Project '{name}'")
                except Exception as e:
                    logging.error(f"Failed to create Project '{name}': {e}")

            elif action == 'CREATE_MODEL':
                logging.info(f"Creating Model '{name}'...")
                try:
                    model = models.WriteLookmlModel(**clean_cfg)
                    self.sdk.create_lookml_model(body=model)
                    logging.info(f"Success: Created Model '{name}'")
                except Exception as e:
                    logging.error(f"Failed to create Model '{name}': {e}")
            
            elif action == 'UPDATE_MODEL':
                logging.info(f"Updating Model '{name}'...")
                try:
                    # update_lookml_model updates the existing model
                    model = models.WriteLookmlModel(**clean_cfg)
                    self.sdk.update_lookml_model(lookml_model_name=name, body=model)
                    logging.info(f"Success: Updated Model '{name}'")
                except Exception as e:
                    logging.error(f"Failed to update Model '{name}': {e}")
        
        # Revert to production workspace
        try:
             self.sdk.update_session(body=models.WriteApiSession(workspace_id="production"))
             logging.info("Reverted to 'production' workspace.")
        except Exception as e:
             logging.warning(f"Failed to revert to 'production' workspace: {e}")
