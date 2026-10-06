"""Question-local read-only TDF measurement parser, based on preserved IGV TDF format specification.
No alignment processing; reads deposited signal tiles. Raw here means unzoomed TDF signal, not raw sequencing.
"""
import struct,zlib,pathlib,json,numpy as np
class Cursor:
 def __init__(self,b):self.b=b;self.p=0
 def read(self,f):
  x=struct.unpack_from('<'+f,self.b,self.p);self.p+=struct.calcsize('<'+f);return x[0] if len(x)==1 else x
 def string(self):
  e=self.b.index(b'\0',self.p);s=self.b[self.p:e].decode();self.p=e+1;return s
 def attrs(self):
  d={}
  for _ in range(self.read('i')):
   k=self.string();d[k]=self.string()
  return d
class TDF:
 def __init__(self,p):
  self.b=pathlib.Path(p).read_bytes();r=Cursor(self.b);self.magic=self.b[:4].decode();r.p=4;self.version=r.read('i');self.ip=r.read('q');self.iz=r.read('i');hs=r.read('i');self.window_functions=[r.string() for _ in range(r.read('i'))];self.track_type=r.string();self.track_line=r.string();self.tracks=[r.string() for _ in range(r.read('i'))];self.genome=r.string();self.flags=r.read('i');assert r.p==24+hs
  r=Cursor(self.b[self.ip:self.ip+self.iz]);self.datasets={};self.groups={}
  for _ in range(r.read('i')):
   name=r.string();self.datasets[name]=(r.read('q'),r.read('i'))
  for _ in range(r.read('i')):
   name=r.string();pos=r.read('q');size=r.read('i');self.groups[name]=Cursor(self.b[pos:pos+size]).attrs()
  assert r.p==self.iz
 def dataset(self,name):
  pos,size=self.datasets[name];r=Cursor(self.b[pos:pos+size]);attrs=r.attrs();typ=r.string();width=r.read('f');n=r.read('i');tiles=[(r.read('q'),r.read('i')) for _ in range(n)];assert r.p==size;return attrs,typ,width,tiles
 def tile(self,pos,size):
  if pos<0 or size<=0:return None
  b=self.b[pos:pos+size]
  if self.flags&1:b=zlib.decompress(b)
  r=Cursor(b);typ=r.string();ntracks=len(self.tracks)
  if typ in ['bed','bedWithName']:
   n=r.read('i');starts=np.array(r.read('i'*n),ndmin=1);ends=np.array(r.read('i'*n),ndmin=1);nt=r.read('i');assert nt==ntracks;values=np.array(r.read('f'*(n*ntracks)),ndmin=1).reshape(ntracks,n)
   if typ=='bedWithName':names=[r.string() for _ in range(n)]
  elif typ=='variableStep':
   tile_start=r.read('i');span=r.read('f');n=r.read('i');starts=np.array(r.read('i'*n),ndmin=1);ends=starts+span;values=np.array(r.read('f'*(n*ntracks)),ndmin=1).reshape(ntracks,n)
  elif typ=='fixedStep':
   n=r.read('i');start=r.read('i');span=r.read('f');starts=start+np.arange(n)*span;ends=starts+span;values=np.array(r.read('f'*(n*ntracks)),ndmin=1).reshape(ntracks,n)
  else:raise ValueError(typ)
  assert r.p==len(b),(typ,r.p,len(b));assert (ends>=starts).all(), (typ, starts[ends<starts][:10], ends[ends<starts][:10]);return starts,ends,values,typ
 def metadata(self):return dict(magic=self.magic,version=self.version,genome=self.genome,flags=self.flags,tracks=self.tracks,track_line=self.track_line,groups=self.groups,dataset_names=list(self.datasets))
if __name__=='__main__':
 import sys
 t=TDF(sys.argv[1]);print(json.dumps(t.metadata(),indent=2));name=next(n for n in t.datasets if n.endswith('/raw'));a,ty,w,tiles=t.dataset(name);print(name,a,ty,w,len(tiles));pos,size=next((p,s) for p,s in tiles if p>=0 and s>0);tile=t.tile(pos,size);print('tile',tile[3],len(tile[0]),tile[0][:5],tile[1][:5],tile[2][:,:5])
