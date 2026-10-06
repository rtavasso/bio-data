from pathlib import Path
p=Path(__file__).resolve().parents[1]/'inputs/public'
for name in ['PMC6754299-supp3.xlsx','PMC6754299-supp4.xlsx','PMC6754299-supplements.zip']:
    data=(p/name).read_bytes()
    text=data.decode('utf-8')
    (p/(name+'.response.txt')).write_text(text)
    print(name,text)
