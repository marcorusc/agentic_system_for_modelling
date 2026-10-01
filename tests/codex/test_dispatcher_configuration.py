from __future__ import annotations
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock
from scripts.codex.dispatcher.launch import launch_configuration
from scripts.codex.launcher_config import mcp_config_arguments, SPECIALISTS

class ConfigurationTests(unittest.TestCase):
    def test_root_dispatcher_and_child_recursive_delegation_disabled(self):
        root=Path(__file__).resolve().parents[2]
        config=tomllib.loads((root/'.codex/config.toml').read_text())['mcp_servers']
        self.assertTrue(config['specialist_dispatcher']['enabled'])
        self.assertTrue(config['specialist_dispatcher']['required'])
        for role in SPECIALISTS:
            overrides=mcp_config_arguments(role)
            self.assertIn("features.apps=false",overrides)
            dispatcher=[v for v in overrides if v.startswith('mcp_servers.specialist_dispatcher=')]
            parsed=tomllib.loads(dispatcher[0])['mcp_servers']['specialist_dispatcher']
            self.assertFalse(parsed['enabled'])
        for name in ('neko','maboss','physicell','biomass'): self.assertFalse(config[name]['enabled'])

    def test_explicit_workstation_settings_and_rejected_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'.setup').mkdir()
            local=root/'.setup/dispatcher.local.json'
            local.write_text(json.dumps({'python_executable':sys.executable,'codex_home':str(root)}))
            python,environment=launch_configuration(root)
            self.assertEqual(python,sys.executable)
            self.assertEqual(environment['CODEX_HOME'],str(root))
            local.write_text(json.dumps({'command':'arbitrary'}))
            with self.assertRaises(ValueError): launch_configuration(root)
            local.write_text(json.dumps({'python_executable':'relative'}))
            with self.assertRaises(ValueError): launch_configuration(root)
