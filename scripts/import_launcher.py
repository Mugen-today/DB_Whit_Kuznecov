"""Shared explicit console import launcher. Defaults to read-only preflight."""
import argparse,subprocess,sys
from pathlib import Path
import manage

def main(extensions=None,argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=Path)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--apply',action='store_true')
    a=p.parse_args(argv);source=a.file.resolve(strict=True)
    allowed=extensions or {'.xlsx','.json','.geojson','.gpkg'}
    if not source.is_file() or source.suffix.lower() not in allowed:p.error('Select an existing file: '+', '.join(sorted(allowed)))
    env=manage.compose_environment()
    subprocess.run(manage.command(['--profile','import','build','excel-import']),cwd=manage.ROOT,env=env,stdout=sys.stderr,check=True)
    target='/input/source'+source.suffix.lower()
    subprocess.run(manage.command(['run','--rm','--no-deps','-T','--volume',str(source)+':'+target+':ro','excel-import','python','-m','app.modules.auto_import',target,'--apply' if a.apply else '--dry-run']),cwd=manage.ROOT,env=env,check=True)
if __name__=='__main__':main()
