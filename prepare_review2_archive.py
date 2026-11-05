"""Prepare a local evidence deposit and checksums; never mint a fake DOI."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
PAPER=ROOT/'result_check/paper_version_staging/versions/v07_v6_content_v5_template'


def collect():
    files=set()
    for path in PAPER.rglob('*'):
        relative=path.relative_to(PAPER)
        if not path.is_file() or 'build' in relative.parts or path.name in {'BaitFL Paper Review Fixes, Graphs, Reviewer Report and Venues.pdf'}:
            continue
        if path.suffix.lower() in {'.tex','.bib','.pdf','.csv','.dat','.json','.md','.ps1','.py','.svg','.png'}:
            files.add(path)
    with (PAPER/'generated/multiseed/per_run.csv').open(newline='',encoding='utf-8-sig') as handle:
        sources=[ROOT/r['source'] for r in csv.DictReader(handle)]
    for source in sources:
        for path in source.rglob('*'):
            if path.is_file() and '.runtime' not in path.parts and path.suffix in {'.csv','.json','.log'} and not path.name.startswith('.'):
                files.add(path)
    provenance=json.loads((PAPER/'generated/comparison/provenance.json').read_text(encoding='utf-8-sig'))
    for entry in provenance['inputs']:
        path=ROOT/entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Changed completed baseline evidence: {path}')
        files.add(path)
    for folder in ['clients','server','data','models','comparison','tests','configs']:
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json'} and '__pycache__' not in p.parts)
    files.update(p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py','.ps1'})
    for name in ['requirements.txt','README.md','.gitattributes','.gitignore']:
        if (ROOT/name).is_file():
            files.add(ROOT/name)
    return sorted(files)


def prepare(output):
    output.mkdir(parents=True,exist_ok=True)
    archive=output/'baitfl_v7_review2_evidence.zip'
    if archive.exists():
        raise FileExistsError('Choose a new output directory; existing deposit bundles are preserved')
    records=[]
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in collect():
            payload=path.read_bytes()
            name=path.relative_to(ROOT).as_posix()
            records.append(dict(path=name,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
            bundle.writestr(name,payload)
        bundle.writestr('DEPOSIT_MANIFEST.json',json.dumps(records,indent=2))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n')
    (output/'deposit_manifest.json').write_text(json.dumps(dict(files=records,archive_sha256=digest,
        deposit_status='local preparation only; no public immutable deposit or DOI yet',
        completed_primary_runs=96,queued_review_runs_are_not_evidence=True),indent=2))
    (output/'DEPOSIT_README.md').write_text('# BaitFL evidence deposit preparation\n\n'
        'This local archive is ready for inspection and authenticated deposit. It is not an immutable public archive and has no DOI. '
        'Check author metadata, applicable redistribution rights and the intended manuscript version before publication. '
        'New review experiments are queued; no uncompleted results are included as evidence.\n')
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('Archive verification failed')
    print(json.dumps(dict(archive=str(archive),files=len(records),bytes=archive.stat().st_size,sha256=digest)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.output)
