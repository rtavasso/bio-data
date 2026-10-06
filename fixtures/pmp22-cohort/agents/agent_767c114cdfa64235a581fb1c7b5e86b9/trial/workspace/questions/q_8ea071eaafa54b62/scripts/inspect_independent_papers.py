"""Read primary papers for independent assay, sample design and data locators."""
from pathlib import Path
from xml.etree import ElementTree as ET
q=Path(__file__).resolve().parents[1]
for label in ['pum-cnot-paper-r001','pum-tcam-paper-r001','qki-schwann-paper-r001']:
    root=ET.parse(q/'inputs/http'/(label+'.payload')).getroot()
    lines=[]
    for el in root.iter():
        if el.tag in ['title','p','supplementary-material']:
            text=' '.join(''.join(el.itertext()).split())
            lines.append(text)
            if any(s in text for s in ['GSE','GEO','PMP22','Pmp22','HEK293','TCam','RNA-seq','RNA-Seq']):
                print(label,text[:5000])
        if el.tag in ['media','ext-link'] and ('suppl' in str(el.attrib) or 'GSE' in str(el.attrib)):
            print('LINK',el.attrib)
    (q/'inputs/views'/(label+'.txt')).write_text('\n'.join(lines))
