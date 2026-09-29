"""Standalone read-only quote collector and persistent forward paper monitor."""
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from broker.kis.client import KisReadOnlyClient
from broker.kis.session import KisSession
from broker.kis.current_price import KisCurrentPriceProvider
from research.paper_reversal import empty_state,observe,event,RULES
from config.settings import settings

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/paper_reversal_live'
STATE=OUT/'state.json'
START_DATE='2026-09-08'
TZ=ZoneInfo('Asia/Seoul')
LOCK=threading.Lock()
CONTROL={'enabled':True}


def save(state):
    tmp=STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(STATE)


def read():
    if not STATE.exists():
        return empty_state()
    return json.loads(STATE.read_text(encoding='utf-8'))


def worker():
    state=read()
    session=KisSession(KisReadOnlyClient())
    provider=KisCurrentPriceProvider(session)
    last_fetch=None
    raw_minutes={}
    day=None
    while True:
        now=datetime.now(TZ)
        state.update(heartbeat=now.isoformat(),pid=os.getpid(),start_date=START_DATE,
                     source=f'KIS_{settings.kis_mode.upper()}_QUOTES',enabled=CONTROL['enabled'])
        try:
            active=(now.date().isoformat()>=START_DATE and now.weekday()<5 and
                    (9,0)<=(now.hour,now.minute)<=(15,35))
            if not CONTROL['enabled']:
                # Pausing blocks entry, but continue protecting an existing position.
                active=active and bool(state['position'])
            if not active:
                state['status']=('REVIEW_OVERNIGHT' if state['position']
                                 else 'ARMED' if CONTROL['enabled'] else 'PAUSED')
            else:
                stamp=now.strftime('%Y%m%d')
                if day!=stamp:
                    raw_minutes={}; last_fetch=None; day=stamp
                minute=now.strftime('%H%M')
                if last_fetch!=minute:
                    payload=session.get('/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice',
                        'FHKST03010200',dict(FID_COND_MRKT_DIV_CODE='J',FID_INPUT_ISCD='233740',
                        FID_INPUT_HOUR_1=now.strftime('%H%M%S'),FID_PW_DATA_INCU_YN='Y',FID_ETC_CLS_CODE='')).json()
                    if payload.get('rt_cd')!='0':
                        raise ValueError(payload.get('msg1','Minute request failed'))
                    directory=OUT/stamp; directory.mkdir(exist_ok=True)
                    (directory/f'raw_{now.strftime("%H%M%S")}.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                    for r in payload.get('output2',[]):
                        if r.get('stck_bsop_date')!=stamp or r['stck_cntg_hour']>=now.strftime('%H%M00'):
                            continue
                        row=dict(date=stamp,time=r['stck_cntg_hour'])
                        for k,f in dict(open='stck_oprc',high='stck_hgpr',low='stck_lwpr',close='stck_prpr',volume='cntg_vol').items():
                            row[k]=float(r[f])
                        raw_minutes[row['time']]=row
                    (directory/'minutes.json').write_text(json.dumps(sorted(raw_minutes.values(),key=lambda r:r['time']),indent=2))
                    last_fetch=minute
                quote=provider.get_prices(['233740'])['233740']
                observed=datetime.now(TZ)
                if (observed-now).total_seconds()>10:
                    raise ValueError('Quote cycle exceeded 10 seconds; no fill')
                with (OUT/stamp/'quotes.jsonl').open('a',encoding='utf-8') as h:
                    h.write(json.dumps(dict(observed_at=observed.isoformat(),quote=quote),ensure_ascii=False)+'\n')
                if not CONTROL['enabled'] and not state['position']:
                    state['status']='PAUSED'
                else:
                    observe(state,list(raw_minutes.values()),quote,observed)
                state['last_error']=None
            with LOCK:
                save(state)
        except Exception as error:
            message=f'{type(error).__name__}: {error}'
            if message!=state.get('last_error'):
                event(state,now,'ERROR',message=message)
            state.update(last_error=message,status='DATA_ERROR')
            with LOCK:
                save(state)
        time.sleep(5 if active else 15)


HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>233740 실시간 모의테스트</title>
<style>body{font:16px system-ui;max-width:1050px;margin:35px auto;padding:20px;background:#f6f8fb;color:#172238}h1{font-size:25px}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:12px}button{padding:10px;margin:5px}</style>
<h1>233740 · 5분봉 신호 + 1분봉 확인</h1><p>100주 · 목표 +50원 · 손절 −80원 · 수수료 각 0.015% · 체결 불이익 각 5원 · 실제 주문 없음</p>
<p>9월 8일부터 평일 자동 관찰. 완성 봉으로 판단하고 조회된 현재가로 가상 체결합니다. 데이터가 누락되거나 5원 호가 단위 밖 가격이 있으면 해당 진입은 건너뜁니다.</p>
<button onclick="control(false)">신규 진입 일시중지</button><button onclick="control(true)">신규 진입 재개</button>
<p id="summary">연결 중</p><pre id="position"></pre><h2>체결 기록</h2><pre id="trades"></pre><h2>판정·오류 기록</h2><pre id="events"></pre>
<script>async function refresh(){try{const r=await fetch('/state');if(!r.ok)throw Error('조회 실패');const s=await r.json();
const age=(Date.now()-Date.parse(s.heartbeat))/1000;document.querySelector('#summary').textContent=`상태: ${s.status} · 서버 기록 ${s.heartbeat} ${age>30?'[갱신 지연]':''} · 현재가 ${s.current_price??'—'} · 실현 순손익 ${Number(s.realized_net).toLocaleString()}원 · ${s.last_error??''}`;
document.querySelector('#position').textContent='가상 보유: '+JSON.stringify(s.position,null,2);
document.querySelector('#trades').textContent=JSON.stringify(s.trades.slice(-30).reverse(),null,2);
document.querySelector('#events').textContent=JSON.stringify(s.events.slice(-20).reverse(),null,2);
}catch(e){document.querySelector('#summary').textContent='서버 연결 실패: '+e.message}}
async function control(enabled){await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});refresh()}
refresh();setInterval(refresh,5000)</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def do_GET(self):
        if self.path not in ('/','/state'):
            self.send_error(404);return
        with LOCK:
            data=read() if self.path=='/state' else HTML
        content=(json.dumps(data,ensure_ascii=False) if isinstance(data,dict) else data).encode('utf-8')
        self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8' if self.path=='/state' else 'text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
    def do_POST(self):
        if self.path!='/control' or self.headers.get('Origin') not in ('http://127.0.0.1:8766','http://localhost:8766'):
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<100:
                raise ValueError()
            value=json.loads(self.rfile.read(length))['enabled']
            if not isinstance(value,bool):
                raise ValueError()
            CONTROL['enabled']=value
            (OUT/'control.json').write_text(json.dumps(CONTROL))
        except (ValueError,KeyError):
            self.send_error(400);return
        self.send_response(204);self.end_headers()


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'control.json').exists():
        CONTROL.update(json.loads((OUT/'control.json').read_text()))
    # Bind before starting collector: a second instance must never trade concurrently.
    server=ThreadingHTTPServer(('127.0.0.1',8766),Handler)
    with LOCK:
        state=read();state.update(status='STARTING',heartbeat=datetime.now(TZ).isoformat(),start_date=START_DATE)
        save(state)
    threading.Thread(target=worker,daemon=True).start()
    server.serve_forever()


if __name__=='__main__':
    main()
