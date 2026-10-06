from pathlib import Path
import sqlite3,json
Q=Path(__file__).resolve().parents[1];W=Q.parents[1];c=sqlite3.connect('file:'+str(W/'catalog.sqlite')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
start=c.execute('select created from question where id=?',(Q.name,)).fetchone()[0];print('START',start)
for r in c.execute('select * from snapshot where retrieved>=? order by retrieved',(start,)):
 b=json.loads(r['body']);print(r['id'],r['outcome'],r['blob'],list(b));print(json.dumps({k:v for k,v in b.items() if any(t in k for t in ['byte','request','transport','receipt','attempt','url'])})[:3000])
