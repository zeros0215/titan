"""Frozen 233740 forward-paper rules. No brokerage calls or order submission."""
import math
from datetime import timedelta

RULES = dict(code='233740',quantity=100,target=50,stop=80,fee_rate=.00015,
             slippage=5,version='233740-5M-HL-1M-MA5-20260907',max_positions=1)


def empty_state():
    return dict(paper_only=True,real_orders=0,rules=RULES.copy(),position=None,
                realized_net=0.,fees=0.,trades=[],events=[],last_boundary=None,
                status='WAITING',last_error=None,current_price=None,heartbeat=None)


def event(state,now,kind,**data):
    state['events']=(state['events']+[dict(time=now.isoformat(),kind=kind,**data)])[-1000:]


def signal(minutes,now):
    """Require complete, tick-valid last 20 minutes, ending on a 5m boundary."""
    boundary=now.replace(second=0,microsecond=0)-timedelta(minutes=now.minute%5)
    first=boundary-timedelta(minutes=20)
    if first.hour<9 or first.date()!=now.date():
        return boundary,'WARMUP',False
    expected=[(first+timedelta(minutes=i)).strftime('%H%M%S') for i in range(20)]
    bytime={r['time']:r for r in minutes if r['date']==now.strftime('%Y%m%d')}
    if any(t not in bytime for t in expected):
        return boundary,'MISSING_MINUTES',False
    rows=[bytime[t] for t in expected]
    for r in rows:
        values=[r[k] for k in ('open','high','low','close')]
        if (any(not math.isfinite(v) or v<=0 or v%5 for v in values)
                or not r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']):
            return boundary,'INVALID_PRICE',False
    bars=[]
    for i in range(0,20,5):
        chunk=rows[i:i+5]
        bars.append(dict(open=chunk[0]['open'],close=chunk[-1]['close'],low=min(r['low'] for r in chunk)))
    current,prior=bars[-1],bars[-2]
    higher_low=(prior['low']<=min(b['low'] for b in bars[:-1])
                and current['low']>prior['low'] and current['close']>prior['close']
                and current['close']>current['open'])
    ma=sum(r['close'] for r in rows[-5:])/5
    previous_ma=sum(r['close'] for r in rows[-6:-1])/5
    good=higher_low and rows[-1]['close']>ma and ma>previous_ma
    return boundary,('SIGNAL' if good else 'NO_SIGNAL'),good


def observe(state,minutes,quote,now):
    if state['rules']!=RULES:
        raise ValueError('Frozen rule mismatch')
    price=float(quote['close'])
    if not math.isfinite(price) or price<=0 or price%5:
        raise ValueError('Current quote is not a valid five-won price')
    qdate=str(quote.get('date','')).replace('-','')
    if qdate!=now.strftime('%Y%m%d'):
        raise ValueError('Stale quote date')
    state.update(current_price=price,last_quote_at=now.isoformat())
    pos=state['position']
    # A position surviving a day boundary requires review; never invent yesterday's exit.
    if pos and pos['date']!=now.date().isoformat():
        state['status']='REVIEW_OVERNIGHT'
        return
    if pos:
        reason=('STOP' if price<=pos['stop'] else 'TARGET' if price>=pos['target']
                else 'END_OF_DAY' if (now.hour,now.minute)>=(15,30) else None)
        if reason:
            sell=price-RULES['slippage']
            fee=sell*100*RULES['fee_rate']
            net=(sell-pos['entry'])*100-pos['entry_fee']-fee
            state['fees']+=fee
            state['realized_net']+=net
            trade=dict(**pos,exit=sell,exit_time=now.isoformat(),net=net,reason=reason)
            state['trades'].append(trade)
            state['position']=None
            event(state,now,'SELL',**trade)
        # Never process a late entry signal on the same observation as an exit.
        if now.minute%5==0:
            state['last_boundary']=now.replace(second=0,microsecond=0).isoformat()
        state['status']='HOLDING' if state['position'] else 'WAITING_SIGNAL'
        return
    if not (9<=now.hour and (now.hour,now.minute)<(15,20)):
        state['status']='OUTSIDE_ENTRY_HOURS'
        return
    boundary,reason,hit=signal(minutes,now)
    key=boundary.isoformat()
    if key==state['last_boundary']:
        return
    age=(now-boundary).total_seconds()
    # Allow up to 60 seconds for the final minute to arrive. Never replay old buys.
    if reason=='MISSING_MINUTES' and age<=60:
        state['status']=reason
        return
    state['last_boundary']=key
    if age>60:
        reason,hit='MISSED_BOUNDARY',False
    state['status']=reason
    event(state,now,'DECISION',boundary=key,reason=reason,delay_seconds=age)
    if hit:
        entry=price+RULES['slippage']
        fee=entry*100*RULES['fee_rate']
        state['position']=dict(date=now.date().isoformat(),entry=entry,
            target=entry+50,stop=entry-80,entry_fee=fee,quantity=100,
            entry_time=now.isoformat(),signal_boundary=key)
        state['fees']+=fee
        state['status']='HOLDING'
        event(state,now,'BUY',**state['position'])
