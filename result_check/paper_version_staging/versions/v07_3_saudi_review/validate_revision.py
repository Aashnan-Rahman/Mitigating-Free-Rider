"""Validate the built revision, frozen protocol and exported evidence."""
from pathlib import Path
import csv, hashlib, json, re, subprocess, html

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def text(p): return p.read_text(encoding='utf-8-sig',errors='replace')
registration=json.loads(text(ROOT/'configs/review2_registration.json'))
for field in ['source_sha256','plan_sha256']:
    for p,h in registration[field].items(): assert sha(ROOT/p)==h,p
preserved={}
for version,stem in [('v07_1_methodology_redesign','paper_v7_1'),('v07_2_review_revision','paper_v7_2')]:
    for name in [stem+'.tex',stem+'.pdf',stem+'_all_in_one.tex',stem+'_all_in_one.pdf','refs.bib']:
        p=HERE.parent/version/name; rel=p.relative_to(ROOT)
        assert not subprocess.check_output(['git','diff','--name-only','HEAD','--',str(rel)],cwd=ROOT),rel
        preserved[str(rel)]=sha(p)
pages={}; outputs={}
for stem,build in [('paper_v7_3','build'),('paper_v7_3_supplement','build'),('paper_v7_3_all_in_one','build/isolated')]:
    log=text(HERE/build/(stem+'.log'))
    assert not re.search(r'Overfull|Float too large|undefined references|Citation .* undefined|multiply defined|^!',log,re.M),stem
    info=subprocess.check_output(['pdfinfo',str(HERE/(stem+'.pdf'))],text=True)
    pages[stem]=int(re.search(r'^Pages:\s*(\d+)',info,re.M)[1]); outputs[stem+'.pdf']=sha(HERE/(stem+'.pdf'))
assert pages['paper_v7_3']==pages['paper_v7_3_all_in_one']
source=text(HERE/'paper_v7_3.tex'); export=text(HERE/'paper_v7_3_all_in_one.tex')
assert r'\appendices' in source and r'\input{generated/geometry_mnist.tex}' in source and r'\input{generated/geometry_cifar10.tex}' in source
assert not re.search(r'\\(?:input|include|includegraphics|bibliography)\s*\{',export)
aux=text(HERE/'build/paper_v7_3.aux')
assert len(re.findall(r'\\bibcite\{',aux))==35
for label in re.findall(r'\\label\{(eq:[^}]+)\}',source):
    assert re.search(r'\\(?:eqref|ref)\{'+re.escape(label)+r'\}',source),label
abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',source,re.S)[1]
words=len(re.findall(r'\b[A-Za-z0-9]+(?:[-][A-Za-z0-9]+)*\b',re.sub(r'\\[A-Za-z]+','',abstract)))
assert 150<=words<=250,words
with (HERE/'generated/saudi/completed_runs.csv').open(newline='',encoding='utf-8') as h: rows=list(csv.DictReader(h))
assert len(rows)==39 and sum(r['batch']=='review2_02_low_share_seed42' for r in rows)==35
subprocess.run(['pdftohtml','-xml','-i','-hidden',str(HERE/'paper_v7_3.pdf'),str(HERE/'build/links.xml')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
links=set(html.unescape(u) for u in re.findall(r'href="(https?[^\"]+)"',text(HERE/'build/links.xml')))
bib=text(HERE/'refs.bib'); allowed=set(re.findall(r'url\s*=\s*\{([^}]+)\}',bib))
allowed.add('https://github.com/Aashnan-Rahman/Mitigating-Free-Rider')
unexpected=links-allowed
assert not unexpected,unexpected
for u in ['https://arxiv.org/abs/2206.05406','https://arxiv.org/abs/2604.04611v3','https://doi.org/10.1109/TON.2026.3668944','https://doi.org/10.1109/ICPADS63350.2024.00034']:
    assert u in links,u
result=dict(date='2026-11-12',pages=pages,references=35,abstract_words=words,completed_prospective_runs=len(rows),completed_low_share=35,registered_sources_preserved=len(registration['source_sha256']),registered_plans_preserved=len(registration['plan_sha256']),previous_files_preserved=preserved,pdf_sha256=outputs,external_link_targets_checked=len(links),unexpected_link_targets=sorted(unexpected))
(HERE/'VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['previous_files_preserved','pdf_sha256']},indent=2))
