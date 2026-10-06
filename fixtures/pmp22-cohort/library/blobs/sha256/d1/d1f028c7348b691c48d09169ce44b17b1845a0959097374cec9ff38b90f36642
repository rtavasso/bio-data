"""Read native XLSX cells as XML data, never evaluate formulas or execute macros."""
import hashlib,json,zipfile
from pathlib import Path
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1];W=Q.parents[1]
sha='98071053e11e1b5a7feaf41d5b76e30cba8e1a7cb2aefdd2287557429054a6b0'
p=W/'blobs/sha256'/sha[:2]/sha
assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
out={'source_blob':sha,'sheets':[]}
with zipfile.ZipFile(p) as z:
    assert not any('vbaproject' in n.lower() for n in z.namelist())
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    for sh in wb.find('s:sheets',ns):
        target=rels[sh.get('{'+ns['r']+'}id')]
        name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        root=ET.fromstring(z.read(name));header=[];selected=[];formulas=0;nrows=0
        for row in root.findall('s:sheetData/s:row',ns):
            vals=[]
            for c in row.findall('s:c',ns):
                if c.find('s:f',ns) is not None:formulas+=1;v='[FORMULA_NOT_EVALUATED]'
                else:
                    e=c.find('s:v',ns);v='' if e is None else e.text
                    if c.get('t')=='s':v=strings[int(v)]
                    if c.get('t')=='inlineStr':v=''.join(c.find('s:is',ns).itertext())
                vals.append({'cell':c.get('r'),'value':v})
            nrows+=1
            if nrows<=3:header.append(vals)
            if any(v['value'] in ['PMP22','EGR2','SOX10','CTGF','CYR61','JUN'] for v in vals):selected.append(vals)
        result={'name':sh.get('name'),'native_path':name,'rows':nrows,'formula_cells_not_evaluated':formulas,'header_rows':header,'selected_rows':selected}
        out['sheets'].append(result)
        print(json.dumps(result,indent=2))
(Q/'outputs/author-workbook-inspection.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
