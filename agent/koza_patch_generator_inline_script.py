import sys
import os
sys.path.insert(0, 'agent')
from parse_migration import parse_multi_table_migration
from patch_generator import save_patch_file

generated_any = False

for root, dirs, files in os.walk('.'):
    # Skip generated patch directories
    if 'patches' in root.split(os.sep):
        continue
    for f in files:
        if not f.endswith('.sql'):
            continue
        path = os.path.join(root, f)
        with open(path, 'r') as file:
            sql = file.read()
        table_parses = parse_multi_table_migration(sql)
        for tp in table_parses:
            table = tp.get('table')
            ops = tp.get('operations', [])
            if table and ops:
                patch_path = save_patch_file(table, ops, output_dir='patches')
                print(f"Generated patch: {patch_path}")
                generated_any = True

with open(os.environ['GITHUB_OUTPUT'], 'a') as gh_out:
    gh_out.write(f"generated_any={'true' if generated_any else 'false'}\n")
