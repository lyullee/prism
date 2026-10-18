from pathlib import Path
import argparse,json,hashlib
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/20261008/prism_qra_function_inventory'
parser=argparse.ArgumentParser(description='Extract a locally supplied reference PDF; no source PDF is bundled.')
parser.add_argument('--book',type=Path,required=True,help='path to the legally available reference PDF')
BOOK=parser.parse_args().book.expanduser().resolve()
if not BOOK.is_file():
    raise SystemExit(f'reference PDF not found: {BOOK}')
reader=PdfReader(BOOK)
pages=[]
for i,page in enumerate(reader.pages):
    pages.append(f'\n\n=== PDF PAGE {i+1} ===\n'+(page.extract_text() or ''))
(OUT/'PurpleBook_extracted.txt').write_text(''.join(pages),encoding='utf-8')
(OUT/'book_extraction_record.json').write_text(json.dumps({'path':str(BOOK),'sha256':hashlib.sha256(BOOK.read_bytes()).hexdigest(),
    'pages':len(pages),'extraction':'pypdf text; original page images required for table-layout verification'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages':len(pages),'text_characters':sum(map(len,pages))},indent=2))
