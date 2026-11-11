"""Cross-platform importer launcher. Existing .env/volumes are preserved."""
import argparse
from pathlib import Path
import subprocess
import manage

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--namespace',default='test-dataset-a')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(); source=args.file.resolve(strict=True)
    command=['run','--rm','--no-deps','-T','--volume',str(source)+':/input/source.xlsx:ro',
             'excel-import','python','-m','app.modules.import_excel','/input/source.xlsx','--namespace',args.namespace]
    if args.apply: command.append('--apply')
    subprocess.run(manage.command(command),cwd=manage.ROOT,env=manage.compose_environment(),check=True)
if __name__=='__main__': main()
