#!/usr/bin/env python3
"""Capture a PhysiCell XML and enabled input dependencies as a portable package.

This validates artifact integrity and relocation, not a PhysiCell simulation.
Only filename and *_filename dependency conventions are recognized; other XML
reference conventions require an explicit implementation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import staged_capture, reject_symlinks
from scripts.capture.index import register_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import safe_file, digest


class DeclarationFreeTreeBuilder(ET.TreeBuilder):
    """Reject DTDs before entity processing, after the parser decodes XML bytes."""

    def doctype(self, name, pubid, system):
        raise ValueError('XML document type and entity declarations are unsupported')


def record_physicell(project, source_root, xml_path, session_id, capture_id):
    project = project.resolve(strict=True)
    source_root = source_root.absolute()
    reject_symlinks(source_root)
    validate_session_id(session_id); validate_session_id(capture_id)
    source = safe_file(source_root, xml_path.absolute().relative_to(source_root).as_posix())
    original = source.read_bytes()
    parser = ET.XMLParser(target=DeclarationFreeTreeBuilder())
    tree = ET.fromstring(original, parser=parser)
    if tree.tag != 'PhysiCell_settings':
        raise ValueError('expected PhysiCell_settings XML root')
    target = project / 'runs/multicellular-configurator' / session_id / 'configs' / capture_id
    parents = {child: parent for parent in tree.iter() for child in parent}
    original_text = {element: element.text for element in tree.iter()}
    refs = []
    def enabled(element):
        while element is not None:
            if element.get('enabled', '').lower() in {'false', '0'}:
                return False
            element = parents.get(element)
        return True
    with staged_capture(project, target) as stage:
        (stage / 'original.xml').write_bytes(original)
        config = stage / 'package/config'
        config.mkdir(parents=True)
        copied = {}
        for element in tree.iter():
            if not enabled(element) or not (element.tag == 'filename' or element.tag.endswith('_filename')):
                continue
            if not element.text or not element.text.strip():
                raise ValueError('enabled filename is empty')
            parent = parents.get(element)
            folder = parent.find('folder') if parent is not None else None
            value = Path(element.text.strip())
            if not value.is_absolute():
                value = source_root / (original_text[folder].strip() if folder is not None and original_text[folder] else '') / value
            file = safe_file(source_root, value.relative_to(source_root).as_posix())
            if file.name == 'PhysiCell_settings.xml':
                raise ValueError('dependency conflicts with package configuration')
            if file.name in copied and copied[file.name] != file:
                raise ValueError('different input files have the same basename')
            copied[file.name] = file
            content = file.read_bytes()
            destination = config / file.name
            destination.write_bytes(content)
            refs.append({'source': str(file), 'path': 'package/config/' + file.name,
                         'sha256': digest(destination)})
            if folder is not None:
                folder.text = './config'
                element.text = file.name
            else:
                element.text = './config/' + file.name
        (config / 'PhysiCell_settings.xml').write_bytes(ET.tostring(tree, encoding='utf-8', xml_declaration=True))
        (stage / 'capture.json').write_text(json.dumps({'schema_version': 1, 'session_id': session_id,
            'capture_id': capture_id, 'source_xml': str(source), 'original_xml_sha256': digest(stage / 'original.xml'),
            'package_xml_sha256': digest(config / 'PhysiCell_settings.xml'), 'dependencies': refs,
            'validation': 'XML structure, enabled dependency containment and hashes; simulation not executed',
            'launch_directory': 'package', 'policy': 'Input paths relocated; scientific values unchanged'}, indent=2) + '\n')
    return register_capture(project, target)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--source-root', type=Path, required=True, help='Explicit root resolving relative XML input paths')
    parser.add_argument('--xml', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--capture-id', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(record_physicell(args.project, args.source_root, args.xml, args.session_id, args.capture_id), indent=2))
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        parser.exit(2, f'PhysiCell capture failed: {error}\n')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
