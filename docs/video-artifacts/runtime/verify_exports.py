#!/usr/bin/env python3
"""Compare actual ClaimCoach service exports with the stored operator-edited text."""
import argparse
import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from pypdf import PdfReader

parser=argparse.ArgumentParser()
parser.add_argument('--confirm-visual-review', action='store_true', help='Set only after inspecting every freshly rendered page')
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'docs/video-artifacts/outputs'
source=OUT/'appeal-reviewed-demo.txt'
normalize=lambda value: ' '.join(unicodedata.normalize('NFKC',value).split())
expected=normalize(source.read_text())
files=[]
pdf=OUT/'claimcoach-demo-appeal.pdf'
reader=PdfReader(pdf)
pdftext='\n'.join(page.extract_text() for page in reader.pages)
assert normalize(pdftext.replace('Draft for human review', '', 1)) == expected, 'PDF differs from the edited text'
assert len(reader.pages)==1, 'PDF pagination changed; render again'
assert 'Draft for human review' in pdftext
path=OUT/'claimcoach-demo-appeal.docx'
with ZipFile(path) as archive:
 root=ET.fromstring(archive.read('word/document.xml'))
 ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
 text='\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
assert normalize(text).endswith(expected), 'DOCX differs from the edited text'
assert 'Draft for human review' in text
for path in (pdf,OUT/'claimcoach-demo-appeal.docx'):
 files.append({'file':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'content_matches_operator_edited_text':True})
receipt={
 'case_id':'case_ef4492f90f971935',
 'method':'actual ClaimCoach worker export endpoint via workspace.py make case-export',
 'source_text':str(source.relative_to(ROOT)),
 'source_text_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'files':files,
 'pdf_pages':len(reader.pages),
 'docx_render_pages':len(list((OUT/'qa/final-docx').glob('page-*.png'))),
 'visual_inspection':({'pdf':'pass: one page, legible, no clipping, no orphan signature','docx':'pass: one page, legible, no clipping or overlap'} if args.confirm_visual_review else {'status':'not claimed; inspect every freshly rendered page'}),
 'docx_renderer':'packaged render_docx.py with bundled LibreOffice at ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice',
 'case_outcome':'not recorded; draft remains for human review',
 'initial_exports':'qa/initial-export preserves the first exported revision with orphan signature pagination',
}
(OUT/'export-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
