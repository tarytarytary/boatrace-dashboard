"""Apply minimal resumability and deadline changes to the user's existing boatrace_batch.py.
Run once at the repository root. Keeps original scoring and extraction logic.
"""
from pathlib import Path
p=Path('boatrace_batch.py')
s=p.read_text(encoding='utf-8')
assert "ap.add_argument('--html-dir'" in s, 'Original source differs; do not patch automatically'
s=s.replace("ap.add_argument('--html-dir',help=", "ap.add_argument('--max-seconds',type=int,default=850);ap.add_argument('--html-dir',help=",1)
s=s.replace("    session=requests.Session();session.headers.update(HEADERS)","    started=time.monotonic()\n    def out_of_time():return time.monotonic()-started >= args.max_seconds\n    session=requests.Session();session.headers.update(HEADERS)",1)
s=s.replace("    results=[]; boats=[]; pending=[]",'''    results=[]; boats=[]; pending=[]
    status_path=out/'race_status.csv'
    prior={}
    if status_path.exists():
        with status_path.open(encoding='utf-8-sig',newline='') as f:
            prior={(r['会場コード'],str(r['レース'])):r for r in csv.DictReader(f) if r.get('日付')==args.date}
    boat_path=out/'boat_data.csv'
    if boat_path.exists():
        with boat_path.open(encoding='utf-8-sig',newline='') as f:
            boats=[r for r in csv.DictReader(f) if r.get('日付')==args.date]
    def persist():
        if results:write_csv(status_path,results,list(results[0]))
        if boats:write_csv(boat_path,boats,['日付','会場コード','レース','艇番','登録番号','級別','全国勝率','当地勝率','モーター2連対率','得点','当地勝率備考'])
    deadline_hit=False''',1)
s=s.replace("            try:\n                html=load_page('racelist',jcd,rno)",'''            old=prior.get((jcd,str(rno)))
            if old and old.get('採点')=='完了':
                results.append(old)
                continue
            if out_of_time():
                record['理由']='実行時間制限：次回再開'
                deadline_hit=True
                results.append(record)
                continue
            try:
                html=load_page('racelist',jcd,rno)''',1)
s=s.replace("        write_csv(out/'race_status.csv',results,list(results[0]))\n        if boats:write_csv(out/'boat_data.csv',boats,['日付','会場コード','レース','艇番','登録番号','級別','全国勝率','当地勝率','モーター2連対率','得点','当地勝率備考'])", "        persist()",1)
s=s.replace("        for ix,url in pending:\n            rec=results[ix]", "        for ix,url in pending:\n            if out_of_time():\n                deadline_hit=True\n                nxt.extend((j,u) for j,u in pending if j>=ix)\n                break\n            rec=results[ix]",1)
s=s.replace("        write_csv(out/'race_status.csv',results,list(results[0]))", "        persist()",1)
s=s.replace("    if boats:write_csv(out/'boat_data.csv',boats,['日付','会場コード','レース','艇番','登録番号','級別','全国勝率','当地勝率','モーター2連対率','得点','当地勝率備考'])\n    summary=", "    persist()\n    summary=",1)
p.write_text(s,encoding='utf-8')
print('Patched boatrace_batch.py')
