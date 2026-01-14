import unittest
from unittest.mock import MagicMock
import sys
import os

# Fix path
sys.path.append(os.getcwd())

# Mock looker_sdk
try:
    import looker_sdk
except ImportError:
    sys.modules['looker_sdk'] = MagicMock()
    import looker_sdk

from lib.project_manager import ProjectManager

class TestProjectManager(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.mgr = ProjectManager(self.sdk)

    def test_get_diff_create_project_and_model(self):
        # Setup
        self.sdk.all_projects.return_value = []
        self.sdk.all_lookml_models.return_value = []
        # Mock update_session to avoid errors
        self.sdk.update_session = MagicMock()
        
        config = [{
            'name': 'Finance',
            'models': [{
                'model_name': 'thelook',
                'connection_names': ['snowflake']
            }]
        }]
        
        # Action
        diffs = self.mgr.get_diff(config)
        
        # Assert
        self.assertEqual(len(diffs), 2)
        
        # 1. Project Creation
        self.assertEqual(diffs[0]['action'], 'CREATE_PROJECT')
        self.assertEqual(diffs[0]['name'], 'Finance')
        
        # 2. Model Creation
        self.assertEqual(diffs[1]['action'], 'CREATE_MODEL')
        self.assertEqual(diffs[1]['name'], 'thelook')
        self.assertEqual(diffs[0]['config']['name'], 'Finance')
        self.assertEqual(diffs[1]['config']['allowed_db_connection_names'], ['snowflake'])

    def test_get_diff_no_changes(self):
        # Setup
        # Existing Project
        mock_proj = MagicMock()
        mock_proj.id = 'Finance'
        mock_proj.name = 'Finance'
        
        # Existing Model
        mock_model = MagicMock()
        mock_model.name = 'thelook'
        mock_model.project_name = 'Finance'
        mock_model.allowed_db_connection_names = ['snowflake']
        
        self.sdk.all_projects.return_value = [mock_proj]
        self.sdk.all_lookml_models.return_value = [mock_model]
        
        config = [{
            'name': 'Finance',
            'models': [{
                'model_name': 'thelook',
                'connection_names': ['snowflake']
            }]
        }]
        
        # Action
        diffs = self.mgr.get_diff(config)
        
        # Assert
        self.assertEqual(len(diffs), 0)

    def test_get_diff_update_model(self):
        # Setup
        # Existing Project
        mock_proj = MagicMock()
        mock_proj.id = 'Finance'
        
        # Existing Model with DIFFERENT connection
        mock_model = MagicMock()
        mock_model.name = 'thelook'
        mock_model.project_name = 'Finance'
        mock_model.allowed_db_connection_names = ['old_connection']
        
        self.sdk.all_projects.return_value = [mock_proj]
        self.sdk.all_lookml_models.return_value = [mock_model]
        
        config = [{
            'name': 'Finance',
            'models': [{
                'model_name': 'thelook',
                'connection_names': ['new_connection']
            }]
        }]
        
        # Action
        diffs = self.mgr.get_diff(config)
        
        # Assert
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]['action'], 'UPDATE_MODEL')
        self.assertEqual(diffs[0]['name'], 'thelook')
        self.assertIn("allowed_db_connection_names", diffs[0]['changes'][0])
        self.assertIn("new_connection", diffs[0]['changes'][0])

    def test_apply_changes(self):
        diffs = [
            {'action': 'CREATE_PROJECT', 'name': 'p1', 'config': {'name': 'p1'}},
            {'action': 'CREATE_MODEL', 'name': 'm1', 'config': {'name': 'm1'}},
            {'action': 'UPDATE_MODEL', 'name': 'm2', 'config': {'name': 'm2'}}
        ]
        
        self.mgr.apply_changes(diffs)
        
        self.sdk.create_project.assert_called_once()
        self.sdk.create_lookml_model.assert_called_once()
        self.sdk.update_lookml_model.assert_called_once()

if __name__ == '__main__':
    unittest.main()
