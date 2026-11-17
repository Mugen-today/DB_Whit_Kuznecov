"""Cross-platform importer launcher. Existing .env/volumes are preserved."""
import argparse
from pathlib import Path
import subprocess
import sys
import manage

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--namespace',default='test-dataset-a')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--sheet')
    parser.add_argument('--format',choices=('records','collections'),default='records')
    parser.add_argument('--historical',action='store_true')
    parser.add_argument('--mode',choices=('bundle','entities'),default='bundle')
    parser.add_argument('--error-policy',choices=('strict','partial'),default='strict')
    args=parser.parse_args(); source=args.file.resolve(strict=True)
    command=['run','--rm','--no-deps','-T','--volume',str(source)+':/input/source.xlsx:ro',
             'excel-import','python','-m','app.modules.import_excel','/input/source.xlsx','--namespace',args.namespace]
    command += ['--format',args.format,'--mode',args.mode,'--error-policy',args.error_policy]
    if args.sheet:command += ['--sheet',args.sheet]
    if args.historical:command.append('--historical')
    if args.apply: command.append('--apply')
    environment=manage.compose_environment()
    subprocess.run(manage.command(["--profile","import","build","excel-import"]),cwd=manage.ROOT,env=environment,stdout=sys.stderr,check=True)
    subprocess.run(manage.command(command),cwd=manage.ROOT,env=environment,check=True)
if __name__=='__main__': main()
