#!/usr/bin/env python3
"""BOAT RACE official-site-only batch collector; refuses unverified scoring."""
import argparse,csv,json,re,time,sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin,parse_qs,urlparse
import requests
from bs4 import BeautifulSoup
BASE='https://www.boatrace.jp'
CODES={'桐生':'01','戸田':'02','江戸川':'03','平和島':'04','多摩川':'05','浜名湖':'06','蒲郡':'07','常滑':'08','津':'09','三国':'10','びわこ':'11','住之江':'12','尼崎':'13','鳴門':'14','丸亀':'15','児島':'16','宮島':'17','徳山':'18','下関':'19','若松':'20','芦屋':'21','福岡':'22','唐津':'23','大村':'24'}
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BoatRaceOfficialDataCollector/1.0)','Accept-Language':'ja-JP,ja;q=0.9'}
def fetch(session,url,tries=2):
    last=None
    for i in range(tries):
        try:
            r=session.get(url,timeout=15);r.raise_for_status()
            if 'BOAT RACE' not in r.text and 'ボートレース' not in r.text and '出走表' not in r.text:raise ValueError('公式ページ内容を確認できない')
            return r.text
        except Exception as e:last=e;time.sleep(0.5*(i+1))
    raise RuntimeError(str(last))
def discover(html):
    soup=BeautifulSoup(html,'html.parser'); venues=[]
    for a in soup.select('a[href]'):
        href=a.get('href',''); q=parse_qs(urlparse(href).query)
        if not any(x in href for x in ('racelist','raceindex')) or 'jcd' not in q:continue
        jcd=q['jcd'][0]; name=next((n for n,c in CODES.items() if c==jcd),None)
        if name and name not in [x[0] for x in venues]:venues.append((name,jcd))
    return venues

def race_data(html,jcd,rno,day):
    soup=BeautifulSoup(html,'html.parser'); full=soup.get_text(' ',strip=True)
    if '出走表' not in full or 'モーター' not in full:raise ValueError('出走表を確認できない')
    # Official page markup varies; require all six racer numbers and grade, and all metrics.
    # If parser cannot unambiguously extract fields, record as pending, NEVER infer.
    # Refuse pages carrying explicit, conflicting race identifiers.
    for key,expected in [('hd',day),('jcd',jcd),('rno',str(rno))]:
        for tag in soup.select(f'input[name={key}]'):
            actual=tag.get('value')
            if actual and actual != expected:raise ValueError(f'公式ページの{key}不一致: {actual} != {expected}')
    # Validate explicit URL identifiers on the page, not just hidden form inputs.
    for a in soup.select('link[rel=canonical], a[href]'):
        href=a.get('href','')
        if 'racelist?' not in href:continue
        q=parse_qs(urlparse(href).query)
        if not all(k in q for k in ('hd','jcd','rno')):continue
        if (q['hd'][0],q['jcd'][0],q['rno'][0]) != (day,jcd,str(rno)):
            # Other-race navigation links are normal; only canonical links identify the page.
            if a.name=='link':raise ValueError('公式ページのcanonical URLが指定レースと不一致')
    rows=[]
    for tr in soup.select('tr'):
        s=tr.get_text(' ',strip=True)
        m=re.search(r'\b(\d{4})\s*/\s*(A1|A2|B1|B2)\b',s)
        if not m:continue
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)]
        # Nationwide/local/motor columns follow racer column in the official table.
        racer_i=next((i for i,c in enumerate(cells) if re.search(r'\b'+m.group(1)+r'\s*/\s*'+m.group(2)+r'\b',c)),None)
        if racer_i is None or len(cells)<racer_i+4:continue
        # Never assign scores to the wrong lane when the table is reordered.
        boat_match=re.fullmatch(r'\s*([1-6])\s*',cells[0])
        if not boat_match:continue
        boat_no=int(boat_match.group(1))
        def nums(cell):return [float(x) for x in re.findall(r'(?<!\d)\d{1,3}\.\d{1,2}(?!\d)',cell)]
        # Some layouts have an extra F/ST cell before nationwide figures.
        after=cells[racer_i+1:]
        triplets=[nums(c) for c in after]
        candidates=[v for v in triplets if len(v)>=3 and 0<=v[0]<=10 and 0<=v[1]<=100 and 0<=v[2]<=100]
        if len(candidates)<2:continue
        national,local=candidates[:2]
        # Motor cell: integer motor number, then 2-ren-tai %, then 3-ren-tai %.
        # Never confuse the integer motor number with the percentage.
        motor_cells=[c for c in after if re.match(r'^\s*\d{1,3}\s+',c) and len(nums(c))>=2]
        motor=float(nums(motor_cells[0])[0]) if motor_cells else None
        if motor is None:continue
        rows.append({'艇番':boat_no,'登録番号':m.group(1),'級別':m.group(2),'全国勝率':national[0],'当地勝率':local[0],'モーター2連対率':motor})
    # Fail closed on ambiguous parsing, duplicate racers, or missing boats.
    if len(rows)!=6 or len(set(r['登録番号'] for r in rows))!=6 or set(r['艇番'] for r in rows)!=set(range(1,7)):raise ValueError(f'6艇の構造化抽出に失敗（{len(rows)}艇）。採点保留')
    rows.sort(key=lambda row:row['艇番'])
    for row in rows:row.update({'日付':day,'会場コード':jcd,'レース':rno})
    return rows

def score(row,config):
    # Requires explicit user-verified conversion configuration; never invent brackets.
    grade=config['grade'][row['級別']]
    local=row['当地勝率']; flag=''
    if local==0:
        local=row['全国勝率'];flag='当地勝率代替あり・実績未確認'
    weighted=0.7*row['全国勝率']+0.3*local
    def bracket(x,brackets):
        for upper,points in brackets:
            if x<=upper:return points
        raise ValueError('換算表の範囲外')
    return grade+bracket(weighted,config['win_rate_brackets'])+bracket(row['モーター2連対率'],config['motor_brackets']),flag

def validate_config(cfg):
    if set(cfg.get('grade',{})) != {'A1','A2','B1','B2'}:
        raise ValueError('級別の4区分が不足')
    if cfg['grade'] != {'A1':25,'A2':20,'B1':13,'B2':5}:
        raise ValueError('級別換算が既存基準と不一致')
    for key in ('win_rate_brackets','motor_brackets'):
        brackets=cfg.get(key)
        if not isinstance(brackets,list) or not brackets:
            raise ValueError(f'{key} の正式換算表が未設定')
        if any(not isinstance(x,list) or len(x)!=2 or not all(isinstance(v,(int,float)) for v in x) for x in brackets):
            raise ValueError(f'{key} の書式が不正')
        if any(brackets[i][0]>=brackets[i+1][0] for i in range(len(brackets)-1)):
            raise ValueError(f'{key} の上限が昇順ではない')
        if any(not 0<=points<=20 for _,points in brackets):
            raise ValueError(f'{key} の点数範囲が不正')
        if brackets[-1][0]<100:
            raise ValueError(f'{key} は全範囲をカバーする必要あり')

def write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=date.today().strftime('%Y%m%d'));ap.add_argument('--out',default='results');ap.add_argument('--config',default=str(Path(__file__).with_name('scoring_config.json')));ap.add_argument('--delay',type=float,default=.25);ap.add_argument('--html-dir',help='保存したBOAT RACE公式HTMLのフォルダ（ネット接続不要）');args=ap.parse_args()
    if not re.fullmatch(r'20\d{6}',args.date):ap.error('--date は YYYYMMDD')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    cfg=None
    if Path(args.config).exists():
        cfg=json.loads(Path(args.config).read_text(encoding='utf-8'))
        validate_config(cfg)
    session=requests.Session();session.headers.update(HEADERS)
    def load_page(kind,jcd=None,rno=None,alternative=False):
        if args.html_dir:
            root=Path(args.html_dir)
            filename=(f'index_{args.date}.html' if kind=='index' else
                      f'raceindex_{args.date}_{jcd}.html' if kind=='raceindex' else
                      f'racelist_{args.date}_{jcd}_{rno}.html')
            path=root/filename
            if not path.is_file():raise FileNotFoundError(f'公式HTML未保存: {filename}')
            return path.read_text(encoding='utf-8')
        url=(f'{BASE}/owpc/pc/race/index?hd={args.date}' if kind=='index' else
             f'{BASE}/owpc/pc/race/raceindex?hd={args.date}&jcd={jcd}' if kind=='raceindex' else
             f'{BASE}/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={args.date}' if alternative else f'{BASE}/owpc/pc/race/racelist?hd={args.date}&jcd={jcd}&rno={rno}')
        return fetch(session,url)
    homepage=load_page('index')
    venues=discover(homepage)
    if not venues:raise RuntimeError('公式開催一覧から会場を特定できない。推測で継続しない')
    # 1R closing times are parsed from race index when available; unknown times sorted last.
    info=[]
    for name,jcd in venues:
        try:
            html=load_page('raceindex',jcd)
            text=BeautifulSoup(html,'html.parser').get_text(' ',strip=True)
            mt=re.search(r'1R\s*(\d\d:\d\d)',text)
            closing=mt.group(1) if mt else ''
        except Exception:closing=''
        info.append((closing,name,jcd))
    info.sort(key=lambda x:(not bool(x[0]),x[0],x[2]))
    results=[]; boats=[]; pending=[]
    for closing,name,jcd in info:
        for rno in range(1,13):
            url=f'{BASE}/owpc/pc/race/racelist?hd={args.date}&jcd={jcd}&rno={rno}'
            record={'日付':args.date,'会場':name,'会場コード':jcd,'1R締切':closing,'レース':rno,'取得':'保留','採点':'未判定','一次通過':'未判定','上位3艇平均':'','3位4位差':'','理由':'','公式URL':url}
            try:
                html=load_page('racelist',jcd,rno)
                extracted=race_data(html,jcd,rno,args.date)
                record['取得']='6艇取得';boats.extend(extracted)
                if cfg:
                    scores=[]
                    for b in extracted:
                        val,flag=score(b,cfg);b['得点']=val;b['当地勝率備考']=flag;scores.append((val,b['艇番']))
                    scores.sort(reverse=True);avg=sum(x[0] for x in scores[:3])/3;gap=scores[2][0]-scores[3][0]
                    record.update({'採点':'完了','一次通過':'通過' if avg>=48 and gap>=6 else '不通過','上位3艇平均':round(avg,2),'3位4位差':round(gap,2)})
                else:record['理由']='正式換算表の設定がないため採点保留'
            except Exception as e:record['理由']=str(e)[:180];pending.append((len(results),url))
            results.append(record);time.sleep(args.delay)
        # Save progress after every venue to prevent losing work.
        write_csv(out/'race_status.csv',results,list(results[0]))
        if boats:write_csv(out/'boat_data.csv',boats,['日付','会場コード','レース','艇番','登録番号','級別','全国勝率','当地勝率','モーター2連対率','得点','当地勝率備考'])
    # Retry only pending races, max five total passes.
    for pass_no in range(2,2 if args.html_dir else 6):
        if not pending:break
        nxt=[]
        for ix,url in pending:
            rec=results[ix]
            try:
                # URL parameter reordering is a fallback, not a different data source.
                alt=f"{BASE}/owpc/pc/race/racelist?rno={rec['レース']}&jcd={rec['会場コード']}&hd={args.date}"
                extracted=race_data(load_page('racelist',rec['会場コード'],rec['レース'],alternative=(pass_no%2==0)),rec['会場コード'],rec['レース'],args.date)
                rec['取得']='6艇取得';boats.extend(extracted);rec['理由']=''
                if cfg:
                    ss=[]
                    for b in extracted:
                        val,flag=score(b,cfg);b['得点']=val;b['当地勝率備考']=flag;ss.append((val,b['艇番']))
                    ss.sort(reverse=True);avg=sum(x[0] for x in ss[:3])/3;gap=ss[2][0]-ss[3][0]
                    rec.update({'採点':'完了','一次通過':'通過' if avg>=48 and gap>=6 else '不通過','上位3艇平均':round(avg,2),'3位4位差':round(gap,2)})
                else:rec['理由']='正式換算表の設定がないため採点保留'
            except Exception as e:rec['理由']=f'{pass_no}周目: {str(e)[:140]}';nxt.append((ix,url))
            time.sleep(args.delay)
        pending=nxt
        write_csv(out/'race_status.csv',results,list(results[0]))
    if boats:write_csv(out/'boat_data.csv',boats,['日付','会場コード','レース','艇番','登録番号','級別','全国勝率','当地勝率','モーター2連対率','得点','当地勝率備考'])
    summary={'date':args.date,'venues':len(info),'races':len(results),'six_boats_extracted':sum(x['取得']=='6艇取得' for x in results),'scored':sum(x['採点']=='完了' for x in results),'passed':sum(x['一次通過']=='通過' for x in results),'pending':sum(x['採点']!='完了' for x in results),'config_loaded':bool(cfg),'official_live_html_verified':False,'note':'本番HTML構造での抽出検証は別途必要'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
