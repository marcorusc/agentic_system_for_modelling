"""Reject recursive plugin-cache layouts before any install or config write."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import setup
from scripts.setup_support import configure_codex
from scripts.setup_support.state import SetupError


class PluginPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'project'; self.root.mkdir()

    def test_nested_equal_and_cache_containing_source_are_rejected(self):
        pairs = [(self.root, self.root), (self.root, self.root/'temporary/home'),
                 (self.root/'plugins', self.root), (self.root/'plugins/cache/plugin', self.root)]
        for root, home in pairs:
            with self.subTest(root=root,home=home), self.assertRaises(SetupError):
                configure_codex.validate_plugin_paths(root,home)

    def test_symlink_alias_cannot_hide_overlap(self):
        alias = self.base/'alias'; alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(SetupError): configure_codex.validate_plugin_paths(self.root,alias/'home')

    def test_separate_home_or_noncache_sibling_source_is_allowed(self):
        configure_codex.validate_plugin_paths(self.root,self.base/'home')
        configure_codex.validate_plugin_paths(self.root/'projects/source',self.root)

    def test_direct_plugin_install_fails_before_cli_calls(self):
        with mock.patch.dict(os.environ,{'CODEX_HOME':str(self.root/'home')}), mock.patch('scripts.setup_support.detect.run') as run:
            with self.assertRaises(SetupError): configure_codex.ensure_plugin(self.root,'codex')
            run.assert_not_called()

    def test_plan_rejects_layout_before_rendering_or_installation(self):
        (self.root/'setup').mkdir()
        (self.root/'setup/dependencies.toml').write_text('supported_systems=["Linux"]\npackage="x"\nversion="1"\n')
        args=setup.parser().parse_args(['--client','codex','--environment-mode','reuse','--codex-home',str(self.root/'home')])
        with mock.patch.object(setup.detect,'system_info',return_value={'system':'Linux'}), \
             mock.patch.object(setup.detect,'discover',return_value='/fixture/tool'), \
             mock.patch.object(setup.detect,'client_version',return_value='1.0.0'), \
             mock.patch.object(configure_codex,'render') as render, \
             mock.patch.object(setup.environment,'install') as install:
            result=setup.execute(args,self.root)
            self.assertFalse(result['passed']); self.assertIn('overlaps',str(result['errors']))
            render.assert_not_called(); install.assert_not_called()


if __name__=='__main__': unittest.main()
