import unittest
from unittest.mock import MagicMock, patch, ANY
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

from lib.connection_manager import ConnectionManager

class TestConnectionManager(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.mgr = ConnectionManager(self.sdk)

    @patch('lib.connection_manager.resolve_secret')
    def test_get_diff_create(self, mock_resolve):
        # Setup
        mock_resolve.side_effect = lambda x: f"resolved_{x}"
        self.sdk.all_connections.return_value = []
        
        config = [{
            'name': 'conn_a',
            'host': 'host_a',
            'dialect_name': 'bigquery',
            'password_env_var': 'MY_PWD'
        }]
        
        # Action
        diffs = self.mgr.get_diff(config)
        
        # Assert
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]['action'], 'CREATE')
        self.assertEqual(diffs[0]['name'], 'conn_a')
        # Check secret resolution
        self.assertEqual(diffs[0]['config']['password'], 'resolved_MY_PWD')
        # Check original env key removal
        self.assertNotIn('password_env_var', diffs[0]['config'])

    def test_get_diff_update(self):
        # Setup
        existing = MagicMock()
        existing.name = 'conn_a'
        existing.host = 'old_host'
        existing.port = 123
        self.sdk.all_connections.return_value = [existing]
        
        config = [{
            'name': 'conn_a',
            'host': 'new_host', # Changed
            'port': 123 # Same
        }]
        
        # Action
        diffs = self.mgr.get_diff(config)
        
        # Assert
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]['action'], 'UPDATE')
        self.assertEqual(diffs[0]['name'], 'conn_a')
        self.assertIn("host: 'old_host' -> 'new_host'", diffs[0]['changes'])
        
    def test_apply_changes(self):
        diffs = [
            {'action': 'CREATE', 'name': 'c1', 'config': {'name': 'c1', 'host': 'h1'}},
            {'action': 'UPDATE', 'name': 'c2', 'config': {'name': 'c2', 'host': 'h2'}, 'original': MagicMock(name='c2')}
        ]
        
        self.mgr.apply_changes(diffs)
        
        # Assert checks
        self.sdk.create_connection.assert_called_once()
        self.sdk.update_connection.assert_called_once()

if __name__ == '__main__':
    unittest.main()
