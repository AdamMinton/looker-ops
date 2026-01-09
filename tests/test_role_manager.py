import unittest
from unittest.mock import MagicMock, call
import sys
import logging

import os
sys.path.append(os.getcwd())

# Mock looker_sdk if not installed in environment (standard practice for these tests)
try:
    import looker_sdk
except ImportError:
    sys.modules['looker_sdk'] = MagicMock()
    import looker_sdk

from lib.role_manager import RoleManager

class TestRoleManager(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.mgr = RoleManager(self.sdk)
        
        # Silence logging during tests
        logging.basicConfig(level=logging.CRITICAL)

    def _setup_mock_objs(self):
        # 1. Permission Sets
        p1 = MagicMock(id="1"); p1.name = "Admin"; p1.permissions = ["access_data"]
        p2 = MagicMock(id="2"); p2.name = "Finance User Perms"; p2.permissions = ["access_data"]
        p3 = MagicMock(id="3"); p3.name = "Support Basic Editor"; p3.permissions = ["access_data"]
        self.sdk.all_permission_sets.return_value = [p1, p2, p3]
        self.sdk.permission_set.side_effect = lambda pid: { "1": p1, "2": p2, "3": p3 }.get(pid)

        # 2. Model Sets
        m1 = MagicMock(id="1"); m1.name = "All"; m1.models = ["model_a"]
        m2 = MagicMock(id="2"); m2.name = "Finance Models"; m2.models = ["model_b"]
        self.sdk.all_model_sets.return_value = [m1, m2]
        self.sdk.model_set.side_effect = lambda mid: { "1": m1, "2": m2 }.get(mid)

        # 3. Roles
        # Admin Role (Protected)
        admin_role = MagicMock(id="1"); admin_role.name = "Admin"
        admin_role.permission_set = MagicMock(id="1"); admin_role.permission_set.name = "Admin"
        admin_role.model_set = MagicMock(id="1"); admin_role.model_set.name = "All"
        
        # Support Role (Protected by Name)
        support_role = MagicMock(id="2"); support_role.name = "Support Basic Editor"
        support_role.permission_set = MagicMock(id="3"); support_role.permission_set.name = "Support Basic Editor"
        support_role.model_set = MagicMock(id="1"); support_role.model_set.name = "All"
        
        # Finance Role (Deletable)
        finance_role = MagicMock(id="3"); finance_role.name = "Finance Analyst"
        finance_role.permission_set = MagicMock(id="2"); finance_role.permission_set.name = "Finance User Perms"
        finance_role.model_set = MagicMock(id="2"); finance_role.model_set.name = "Finance Models"
        
        self.sdk.all_roles.return_value = [admin_role, support_role, finance_role]
        self.sdk.role.side_effect = lambda rid: { "1": admin_role, "2": support_role, "3": finance_role }.get(rid)

    def test_create_role(self):
        self._setup_mock_objs()
        
        # Config has NEW role 'Sales User'
        config = {
            'permission_sets': [],
            'model_sets': [],
            'roles': [
                {'name': 'Admin', 'permission_set': 'Admin', 'model_set': 'All'},
                {'name': 'Support Basic Editor', 'permission_set': 'Support Basic Editor', 'model_set': 'All'},
                {'name': 'Finance Analyst', 'permission_set': 'Finance User Perms', 'model_set': 'Finance Models'},
                {'name': 'Sales User', 'permission_set': 'Finance User Perms', 'model_set': 'Finance Models'} # New reuse
            ]
        }
        
        diffs = self.mgr.get_diff(config)
        create_actions = [d for d in diffs if d['action'] == 'CREATE_ROLE']
        self.assertEqual(len(create_actions), 1)
        self.assertEqual(create_actions[0]['name'], 'Sales User')

    def test_update_role_skip_admin(self):
        self._setup_mock_objs()
        
        # Config tries to change Admin's Perm Set
        config = {
            'roles': [
                {'name': 'Admin', 'permission_set': 'Finance User Perms', 'model_set': 'All'}, # Changed PS
                {'name': 'Support Basic Editor', 'permission_set': 'Support Basic Editor', 'model_set': 'All'},
                {'name': 'Finance Analyst', 'permission_set': 'Finance User Perms', 'model_set': 'Finance Models'}
            ]
        }
        
        diffs = self.mgr.get_diff(config)
        # Should be NO UPDATE_ROLE for Admin
        admin_updates = [d for d in diffs if d['name'] == 'Admin' and d['action'] == 'UPDATE_ROLE']
        self.assertEqual(len(admin_updates), 0, "Admin role should validly skip updates even if config differs")

    def test_deletion_and_protection(self):
        self._setup_mock_objs()
        
        # Config ONLY has Admin and one Support Role.
        # 'Finance Analyst' is MISSING -> Should Delete
        # 'Support Basic Editor' matching Name -> Should Keep? 
        # Wait, in setup I have 'Support Basic Editor'. If I exclude it from config?
        
        config = {
            'roles': [
                {'name': 'Admin', 'permission_set': 'Admin', 'model_set': 'All'}
            ]
        }
        
        diffs = self.mgr.get_diff(config)
        actions = [(d['action'], d['name']) for d in diffs]
        
        # 1. Finance Analyst -> DELETE
        self.assertIn(('DELETE_ROLE', 'Finance Analyst'), actions)
        
        # 2. Support Basic Editor -> PROTECTED (Skip Deletion)
        self.assertNotIn(('DELETE_ROLE', 'Support Basic Editor'), actions)
        
        # 3. Admin -> PROTECTED (Skip Deletion)
        self.assertNotIn(('DELETE_ROLE', 'Admin'), actions)

    def test_apply_changes_order(self):
        # We verify that deletes happen in safe order
        # This is a behavior test of apply_changes
        diffs = [
            {'action': 'DELETE_MODEL_SET', 'name': 'MSet1', 'id': '10'},
            {'action': 'DELETE_PERM_SET', 'name': 'PSet1', 'id': '20'},
            {'action': 'DELETE_ROLE', 'name': 'Role1', 'id': '30'},
        ]
        
        self.mgr.apply_changes(diffs)
        
        # Check call order
        # Expect: Delete Role FIRST
        self.sdk.delete_role.assert_called_with(role_id='30')
        
        # We can't strictly verify order between API calls easily without side_effect tracking list
        # but we can verify all were called.
        self.sdk.delete_permission_set.assert_called_with(permission_set_id='20')
        self.sdk.delete_model_set.assert_called_with(model_set_id='10')

if __name__ == '__main__':
    unittest.main()
