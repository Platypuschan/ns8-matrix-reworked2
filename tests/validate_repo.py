# SPDX-License-Identifier: AGPL-3.0-or-later
import ast
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
files = []
for directory, folders, names in os.walk(root):
    folders[:] = [d for d in folders if d not in {'.git','node_modules','dist','.yarn','__pycache__'}]
    files.extend(Path(directory) / name for name in names)
for path in files:
    if not path.is_file() or set(path.relative_to(root).parts) & {'.git','node_modules','dist','.yarn','__pycache__'}:
        continue
    try:
        source = path.read_text()
    except UnicodeDecodeError:
        continue
    if path.suffix == '.json':
        json.loads(source)
    if path.suffix == '.py' or (source.startswith('#!') and 'python' in source.splitlines()[0]):
        ast.parse(source,filename=str(path))
    if source.startswith('#!') and any(s in source.splitlines()[0] for s in ('bash','/sh')):
        subprocess.run(['bash','-n',str(path)],check=True)
    if path.is_relative_to(root/'imageroot') and '%S/state' in source:
        raise ValueError(str(path)+': use current NS8 %E paths')
print('Python, JSON, shell and NS8 paths are valid')
