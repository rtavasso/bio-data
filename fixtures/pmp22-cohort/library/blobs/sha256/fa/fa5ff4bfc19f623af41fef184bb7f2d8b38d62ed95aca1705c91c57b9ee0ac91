"""Inspect only local catalog schema relevant to transport receipts (read-only)."""
from pathlib import Path
import sqlite3
Q=Path(__file__).resolve().parents[1];W=Q.parents[1]
c=sqlite3.connect('file:'+str(W/'catalog.sqlite')+'?mode=ro',uri=True)
for name,sql in c.execute("select name,sql from sqlite_master where type='table'"):
 if any(t in name for t in ['run','transport','snapshot','receipt','question','event']):print(name,sql)
