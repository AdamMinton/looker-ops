import unittest
from unittest.mock import MagicMock, call
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

from lib.oidc_manager import OIDCManager

class TestOIDCManager(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.mgr = OIDCManager(self.sdk)

    def test_get_diff_no_change(self):
        # Setup current
        current = MagicMock()
        current.identifier = 'client_123'
        current.secret = 'secret_xxx' # Ignored
        current.scopes = ['email', 'profile']
        self.sdk.oidc_config.return_value = current
        
        config = {
            'client_id': 'client_123',
            'scopes': ['profile', 'email'] # Different order, should resolve
        }
        
        diffs = self.mgr.get_diff(config)
        self.assertEqual(len(diffs), 0)

    def test_get_diff_update_simple(self):
        current = MagicMock()
        current.identifier = 'client_123'
        self.sdk.oidc_config.return_value = current
        
        config = {
            'client_id': 'client_NEW' # Changed
        }
        
        diffs = self.mgr.get_diff(config)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]['action'], 'UPDATE')
        self.assertIn("identifier: 'client_123' -> 'client_NEW'", diffs[0]['changes'])

    def test_group_mirroring_diff(self):
        # Setup roles for resolution
        r1 = MagicMock(id='r1'); r1.name = 'Admin'
        r2 = MagicMock(id='r2'); r2.name = 'User'
        self.sdk.all_roles.return_value = [r1, r2]
        
        # Setup Current
        g1 = MagicMock(id='g1')
        g1.name = 'Okta_Admins'
        g1.role_ids = ['r1'] # Has Admin
        
        current = MagicMock()
        current.groups_with_role_ids = [g1]
        self.sdk.oidc_config.return_value = current
        
        # Scenario: YAML adds 'User' role to Okta_Admins
        config = {
            'mirrored_groups': [
                {'name': 'Okta_Admins', 'roles': ['Admin', 'User']}
            ]
        }
        
        diffs = self.mgr.get_diff(config)
        
        self.assertEqual(len(diffs), 1)
        # Verify changes text roughly matches expected list format
        # changes: groups_with_role_ids: [...] -> [...]
        self.assertIn('groups_with_role_ids', diffs[0]['changes'][0])
        
    def test_apply_changes_oidc(self):
        # Setup existing groups for ID resolution
        current_g = MagicMock(id='existing_g_id')
        current_g.name = 'MyGroup'
        current_g.role_ids = []
        
        current_conf = MagicMock()
        current_conf.groups_with_role_ids = [current_g]
        self.sdk.oidc_config.return_value = current_conf
        
        # Setup Roles
        r1 = MagicMock(id='r100'); r1.name = 'Viewer'
        self.sdk.all_roles.return_value = [r1]

        diffs = [{
            'action': 'UPDATE',
            'name': 'OIDC Configuration',
            'config': {
                'groups_with_role_ids': [
                    {'name': 'MyGroup', 'roles': ['Viewer']}
                ]
            }
        }]
        
        self.mgr.apply_changes(diffs)
        
        # Verify update call
        self.sdk.update_oidc_config.assert_called_once()
        # Verify the body passed has correct role_ids and group ID
        call_args = self.sdk.update_oidc_config.call_args
        body = call_args.kwargs['body']
        
        # The list of groups should be processed
        groups = body.groups_with_role_ids
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, 'MyGroup')
        self.assertEqual(groups[0].id, 'existing_g_id') # Should preserve ID
        self.assertEqual(groups[0].role_ids, ['r100']) # Should resolve Viewer -> r100

if __name__ == '__main__':
    unittest.main()
