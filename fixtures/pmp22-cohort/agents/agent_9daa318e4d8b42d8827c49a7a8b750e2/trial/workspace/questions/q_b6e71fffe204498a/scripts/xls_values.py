"""Narrow read-only CFB/BIFF8 value extractor for preserved public XLS tables.

No formulas, macros, links or serializations are executed. Formula/error records
are reported and never used as abundance. Supports the numeric/string record
types needed by the two SNAT supplementary workbooks, not a general Excel engine.
"""
from pathlib import Path
import struct

END = 0xFFFFFFFE
FREE = 0xFFFFFFFF

def u16(b, offset=0):
    return struct.unpack_from('<H', b, offset)[0]

def u32(b, offset=0):
    return struct.unpack_from('<I', b, offset)[0]

def workbook_stream(path):
    b = Path(path).read_bytes()
    assert b[:8] == bytes.fromhex('D0CF11E0A1B11AE1')
    assert u16(b,28) == 0xFFFE
    sector_size = 1 << u16(b,30)
    def sector(sid):
        assert sid < len(b)//sector_size-1
        return b[(sid+1)*sector_size:(sid+2)*sector_size]
    difat = list(struct.unpack_from('<109I',b,76))
    sid = u32(b,68)
    for _ in range(u32(b,72)):
        d = sector(sid)
        words = struct.unpack('<'+'I'*(sector_size//4),d)
        difat.extend(words[:-1])
        sid = words[-1]
    fat_sectors = [s for s in difat if s != FREE]
    assert len(fat_sectors) == u32(b,44)
    fat = []
    for s in fat_sectors:
        fat.extend(struct.unpack('<'+'I'*(sector_size//4),sector(s)))
    def chain(start):
        seen = set()
        parts = []
        while start != END:
            assert start not in seen and start < len(fat)
            seen.add(start)
            parts.append(sector(start))
            start = fat[start]
        return b''.join(parts)
    directory = chain(u32(b,48))
    for off in range(0,len(directory),128):
        d=directory[off:off+128]
        n=u16(d,64)
        if n < 2:
            continue
        name=d[:n-2].decode('utf-16le')
        if name in ['Workbook','Book']:
            size=struct.unpack_from('<Q',d,120)[0]
            assert size>=u32(b,56), 'Mini-stream workbooks unsupported'
            data=chain(u32(d,116))[:size]
            assert len(data)==size
            return data
    raise ValueError('No Workbook stream')

class Segments:
    def __init__(self, chunks):
        self.chunks=chunks
        self.i=0
        self.pos=0
    def available(self):
        return len(self.chunks[self.i])-self.pos
    def advance(self):
        self.i+=1
        self.pos=0
        assert self.i<len(self.chunks), 'Unexpected SST end'
    def read(self,n):
        parts=[]
        while n:
            if not self.available():
                self.advance()
            take=min(n,self.available())
            parts.append(self.chunks[self.i][self.pos:self.pos+take])
            self.pos+=take
            n-=take
        return b''.join(parts)
    def chars(self,n,wide):
        parts=[]
        while n:
            if not self.available():
                self.advance()
                wide=bool(self.read(1)[0]&1)
            width=2 if wide else 1
            take=min(n,self.available()//width)
            assert take>0, 'Partial Unicode code unit'
            parts.append(self.read(take*width).decode('utf-16le' if wide else 'latin1'))
            n-=take
        return ''.join(parts)

def shared_strings(chunks):
    r=Segments(chunks)
    total,unique=struct.unpack('<II',r.read(8))
    strings=[]
    for _ in range(unique):
        n=u16(r.read(2))
        flags=r.read(1)[0]
        runs=u16(r.read(2)) if flags&8 else 0
        extra=u32(r.read(4)) if flags&4 else 0
        strings.append(r.chars(n,bool(flags&1)))
        r.read(runs*4+extra)
    assert r.i==len(chunks)-1 and r.available()==0, (r.i,r.available())
    return strings,total

def rk_number(value):
    if value&2:
        signed=struct.unpack('<i',struct.pack('<I',value))[0]
        n=signed>>2
    else:
        n=struct.unpack('<d',struct.pack('<II',0,value&0xFFFFFFFC))[0]
    return n/100 if value&1 else n

def read_xls(path):
    data=workbook_stream(path)
    records=[]
    pos=0
    while pos+4<=len(data):
        code,length=struct.unpack_from('<HH',data,pos)
        if code==0 and length==0:
            assert not any(data[pos:]), 'Unexpected nonzero trailing bytes'
            break
        assert pos+4+length<=len(data)
        records.append((pos,code,data[pos+4:pos+4+length]))
        pos+=4+length
    sheets=[]
    strings=[]
    for i,(offset,code,d) in enumerate(records):
        if code==0x0085:
            n=d[6]
            wide=bool(d[7]&1)
            name=d[8:8+n*(2 if wide else 1)].decode('utf-16le' if wide else 'latin1')
            assert d[5]==0, 'Nonworksheet sheet in workbook'
            sheets.append((u32(d),name))
        if code==0x00FC:
            chunks=[d]
            j=i+1
            while j<len(records) and records[j][1]==0x003C:
                chunks.append(records[j][2])
                j+=1
            strings,_=shared_strings(chunks)
    result={}
    for start,name in sheets:
        cells={}
        formulas=[]
        errors=[]
        counts={}
        started=False
        def put(row,col,value):
            assert (row,col) not in cells, (name,row,col)
            cells[row,col]=value
        for offset,code,d in records:
            if offset<start:
                continue
            if code==0x0809:
                assert not started
                started=True
            if code==0x000A:
                break
            counts[hex(code)]=counts.get(hex(code),0)+1
            if code==0x00FD:
                row,col,_xf,index=struct.unpack('<HHHI',d)
                put(row,col,strings[index])
            elif code==0x0203:
                row,col=u16(d),u16(d,2)
                put(row,col,struct.unpack_from('<d',d,6)[0])
            elif code==0x027E:
                put(u16(d),u16(d,2),rk_number(u32(d,6)))
            elif code==0x00BD:
                row,first=u16(d),u16(d,2)
                last=u16(d,len(d)-2)
                assert len(d)==6+(last-first+1)*6
                for k,col in enumerate(range(first,last+1)):
                    put(row,col,rk_number(u32(d,6+k*6)))
            elif code==0x0006:
                formulas.append((u16(d),u16(d,2)))
                put(u16(d),u16(d,2),None)
            elif code==0x0205:
                row,col=u16(d),u16(d,2)
                if d[7]:
                    errors.append((row,col,d[6]))
                    put(row,col,None)
                else:
                    put(row,col,bool(d[6]))
            elif code in [0x0204,0x00D6]:
                raise ValueError(f'Unsupported inline string {code}')
        assert started and cells
        nr=max(r for r,c in cells)+1
        nc=max(c for r,c in cells)+1
        rows=[[cells.get((r,c)) for c in range(nc)] for r in range(nr)]
        result[name]=dict(rows=rows,formulas=formulas,errors=errors,record_counts=counts,nonblank_cells=len(cells))
    return result

if __name__=='__main__':
    # Unit tests of signed/integer/scaled and double encodings and SST continuation.
    assert rk_number((123<<2)|2)==123
    assert rk_number((123<<2)|3)==1.23
    assert rk_number(0xFFFFFFFE)==-1
    assert rk_number(0x3FF00000)==1.0
    assert rk_number(0x3FF00001)==0.01
    chunks=[struct.pack('<IIHB',1,1,5,0)+b'ab',b'\x00cde']
    assert shared_strings(chunks)[0]==['abcde']
    chunks=[struct.pack('<IIHB',1,1,4,1)+'\u03b1b'.encode('utf-16le'),b'\x01'+'\u03b3d'.encode('utf-16le')]
    assert shared_strings(chunks)[0]==['\u03b1b\u03b3d']
    print('CFB/BIFF scalar and continued-string unit checks passed')
