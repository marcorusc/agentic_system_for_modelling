#!/usr/bin/env python3
"""Inspect registrations without starting MCPs; explicitly migrate unsafe globals.

Default: read-only check. --apply removes only recognized modelling registrations
and optionally adds the isolated literature PubMed transport, after private backups.
No check of configuration can prove a running desktop's already-granted inventory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.codex.launcher_config import MODELLING_SERVERS, PUBMED_TOOLS, toml_literal
from scripts.setup_support.configure_codex import PUBMED_URL
from scripts.setup_support.state import SetupError, read_json, write_config


def modelling(name: str, config: dict | None = None) -> bool:
    if any(re.search(rf'(^|[-_]){server}($|[-_])', name.lower()) for server in MODELLING_SERVERS):
        return True
    transport = ' '.join(str((config or {}).get(k, '')) for k in ('command', 'args', 'url'))
    return any(f'mcp-{server}-server' in transport or f'mcp_biomodelling_servers.{server}'.lower() in transport.lower()
               for server in MODELLING_SERVERS)


def registrations(path: Path, root: Path) -> list[tuple[str, dict]]:
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text()) if path.suffix == '.toml' else read_json(path)
    groups = [('global', data.get('mcpServers', data.get('mcp_servers', {})))]
    groups += [(f'project:{key}', value.get('mcpServers', {})) for key, value in data.get('projects', {}).items()
               if Path(key).resolve() == root.resolve()]
    return [(f'{scope}/{name}', config) for scope, servers in groups for name, config in servers.items()
            if modelling(name, config) and config.get('enabled', True)]


def check(root: Path, *, user_config: Path | None = None, codex_configs: tuple[Path, ...] = ()) -> dict:
    errors = []
    paths = [root/'.mcp.json', root/'.codex/config.toml']
    if user_config is not None:
        paths.append(user_config)
    paths.extend(codex_configs)
    for path in paths:
        for name, _ in registrations(path, root):
            errors.append(f'{path}: enabled modelling registration {name}; use isolated agent/profile transports')
    for path in (root/'.claude/settings.json', root/'.claude/settings.local.json'):
        data = read_json(path)
        for rule in data.get('permissions', {}).get('allow', []):
            if any(re.search(rf'mcp__{server}(?:[-_]agent)?__', rule) for server in MODELLING_SERVERS):
                errors.append(f'{path}: project-wide modelling allow rule {rule}')
        if data.get('mcpServers'):
            for name, config in data['mcpServers'].items():
                if modelling(name, config):
                    errors.append(f'{path}: modelling registration {name}')
    for server, role in [('neko','network-curator'),('maboss','boolean-dynamics-modeler'),
                         ('physicell','multicellular-configurator'),('biomass','ode-modeler')]:
        path = root/f'.claude/agents/{role}.md'
        if path.exists():
            header = path.read_text().split('---', 2)[1]
            if f'  - {server}-agent:\n' not in header or f'mcp__{server}-agent__*' not in header:
                errors.append(f'{path}: expected isolated {server}-agent transport and tool selector')
    return {'passed': not errors, 'errors': errors, 'live_inventory_verified': False}


def snapshot_errors(root: Path, expected: str) -> list[str]:
    errors = []
    for name in ('neko', 'maboss', 'physicell'):
        path = root/f'.claude/skills/{name}-workflow/SKILL.md'
        match = re.search(r'Operational snapshot for `mcp-biomodelling-servers` (\d+\.\d+\.\d+)', path.read_text()) if path.exists() else None
        if not match or match[1] != expected:
            errors.append(f'{path}: operational snapshot must match installed/pinned server {expected}')
    return errors


def migration(user_config: Path | None, codex_configs: tuple[Path, ...], profile: Path | None, root: Path | None = None) -> dict[Path, str]:
    outputs = {}
    if root is not None:
        path = root/'.claude/settings.local.json'
        if path.exists():
            data = read_json(path)
            permissions = data.get('permissions', {})
            if 'allow' in permissions:
                permissions['allow'] = [rule for rule in permissions['allow'] if not any(
                    re.search(rf'mcp__{server}(?:[-_]agent)?__', rule) for server in MODELLING_SERVERS)]
            outputs[path] = json.dumps(data, indent=2) + '\n'
    if user_config and user_config.exists():
        data = read_json(user_config)
        groups = [data.get('mcpServers', {})] + [v.get('mcpServers', {}) for key,v in data.get('projects', {}).items()
                  if root is not None and Path(key).resolve() == root.resolve()]
        for servers in groups:
            for name in list(servers):
                if modelling(name, servers[name]):
                    del servers[name]
        outputs[user_config] = json.dumps(data, indent=2) + '\n'
    for path in codex_configs:
        if not path.exists():
            continue
        data = tomllib.loads(path.read_text())
        servers = data.get('mcp_servers', {})
        for name in list(servers):
            if modelling(name, servers[name]):
                del servers[name]
        outputs[path] = '\n'.join(f'{toml_literal(k)} = {toml_literal(v)}' for k,v in data.items()) + '\n'
    if profile:
        if not profile.is_file():
            raise SetupError('Run setup for the selected Codex home before migrating its literature profile')
        data = tomllib.loads(profile.read_text())
        data.setdefault('mcp_servers', {}).setdefault('pubmed', {
            'url': PUBMED_URL, 'enabled': True, 'required': True, 'enabled_tools': list(PUBMED_TOOLS)})
        data['web_search'] = 'disabled'
        outputs[profile] = '\n'.join(f'{toml_literal(k)} = {toml_literal(v)}' for k,v in data.items()) + '\n'
    return {path:text for path,text in outputs.items() if path.read_text() != text}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--repository-only', action='store_true')
    p.add_argument('--user-config', type=Path, default=Path.home()/'.claude.json')
    p.add_argument('--codex-config', type=Path, action='append', default=[])
    p.add_argument('--literature-profile', type=Path)
    p.add_argument('--preview', action='store_true')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    try:
        user = None if args.repository_only else args.user_config
        if args.repository_only and (args.apply or args.preview):
            raise SetupError('Migration requires explicit user configuration scope')
        result = check(args.root, user_config=user, codex_configs=tuple(args.codex_config))
        if args.preview or args.apply:
            outputs = migration(user, tuple(args.codex_config), args.literature_profile, args.root)
            result['planned_files'] = [str(path) for path in outputs]
            if args.apply:
                backups = args.root/'.setup/backups/isolation'
                result['writes'] = [write_config(path, text, backups) for path,text in outputs.items()]
                result.update(check(args.root, user_config=user, codex_configs=tuple(args.codex_config)))
        print(json.dumps(result, indent=2))
        return 0 if result['passed'] else 2
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'passed':False, 'errors':[str(error)]}, indent=2))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
