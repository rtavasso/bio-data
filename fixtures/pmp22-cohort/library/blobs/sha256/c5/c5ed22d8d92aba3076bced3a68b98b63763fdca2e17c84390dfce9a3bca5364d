"""List completed supplement archives and inspect tables without executing embedded content."""
import io
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
import openpyxl
q=Path(__file__).resolve().parents[1]
for label in ['pum-cnot-supp-r001','pum-tcam-supp-r001','qki-schwann-supp-r001']:
    receipt=q/'inputs/http'/(label+'.receipt.json')
    if not receipt.exists():
        print('NO COMPLETED RECEIPT',label)
        continue
    rec=json.loads(receipt.read_text())
    print('RECEIPT',label,{k:rec.get(k) for k in ['status','bytes','complete','error']})
    if not rec['complete'] or rec.get('status')!=200:
        continue
    p=q/'inputs/http'/(label+'.payload')
    if not zipfile.is_zipfile(p):
        print('NOT ZIP',p.read_bytes()[:200])
        continue
    tables={}
    def inspect(b,prefix):
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            print('ARCHIVE',prefix,[(x.filename,x.file_size) for x in z.infolist()])
            for member in z.namelist():
                if member.endswith('.zip'):
                    inspect(z.read(member),prefix+'/'+member)
                elif member.endswith('.xlsx'):
                    wb=openpyxl.load_workbook(io.BytesIO(z.read(member)),read_only=True,data_only=True)
                    for ws in wb:
                        vals=list(ws.values)
                        tables[prefix+'/'+member+'/'+ws.title]=vals
                        hits=[(i+1,r) for i,r in enumerate(vals) if any(str(v).strip().upper()=='PMP22' or str(v).startswith('ENSG00000109099') for v in r)]
                        print('TABLE',member,ws.title,ws.max_row,ws.max_column,'FIRST',repr(vals[:3])[:1400],'PMP22',repr(hits)[:7000])
                    wb.close()
                elif member.endswith('.docx'):
                    with zipfile.ZipFile(io.BytesIO(z.read(member))) as doc:
                        text='\n'.join(''.join(n.itertext()) for n in ET.fromstring(doc.read('word/document.xml')).iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
                    name=Path(member).name+'.txt'
                    (q/'inputs/views'/name).write_text(text)
                    print('DOCX VIEW',name)
    inspect(p.read_bytes(),label)
    (q/'inputs/views'/(label+'-tables.json')).write_text(json.dumps(tables,indent=2,default=str,allow_nan=False))
