"""Descriptive provider-industry analysis; current labels, not historical labels."""
import csv
import json
from collections import Counter
from pathlib import Path

from tools.review_observation_filters import metrics, MONTHS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/reports/observation_industry_202607_09'


def main():
    labels=json.loads((OUT/'industry_labels.json').read_text(encoding='utf-8'))
    source=ROOT/'output/reports/observation_filters_202607_09'
    rows=json.loads((source/'joined_trades.json').read_text(encoding='utf-8'))
    candidates=[]
    for path in sorted((ROOT/'output/kis_manual_tests/runs').glob('LOCAL_2026*_H20_V1_3_S80_N7_TP5_SL10_CANDIDATE_TP5_SL10.json')):
        run=json.loads(path.read_text(encoding='utf-8'))
        if run['as_of'][:7] not in MONTHS: continue
        for c in run['observation_candidates']:
            candidates.append({**c,'selection_date':run['as_of'][:10]})
    for r in [*rows,*candidates]:
        label=labels.get(r['code'],{})
        r['industry']=label.get('industry') or 'UNCLASSIFIED'
        raw_market=label.get('market','')
        r['industry_market']={'KOSPI200':'KOSPI','KSQ150':'KOSDAQ'}.get(raw_market,raw_market)
        assert r['industry_market'] in ('KOSPI','KOSDAQ'), raw_market
        # Preserve the market boundary: identical names across KOSPI/KOSDAQ
        # need not represent the same index or classification universe.
        r['industry_key']=r['industry_market']+' / '+r['industry']
    keys=sorted({r['industry_key'] for r in candidates})
    groups={key:dict(candidates=sum(r['industry_key']==key for r in candidates),
                     completed=metrics([r for r in rows if r['industry_key']==key]),
                     months={m:metrics([r for r in rows if r['industry_key']==key and r['month']==m]) for m in MONTHS}) for key in keys}
    # Pick rank 1 within each date/industry from ALL candidates, before checking
    # their future outcomes. Do not choose among winners or completed rows only.
    chosen={}
    for r in sorted(candidates,key=lambda r:(r['selection_date'],r['rank'],r['code'])):
        chosen.setdefault((r['selection_date'],r['industry_key']),r['code'])
    keep=lambda r:chosen[(r['selection_date'],r['industry_key'])]==r['code']
    concentration={m:dict(baseline=metrics([r for r in rows if m=='ALL' or r['month']==m]),
                           retained=metrics([r for r in rows if (m=='ALL' or r['month']==m) and keep(r)]),
                           removed=metrics([r for r in rows if (m=='ALL' or r['month']==m) and not keep(r)])) for m in ['ALL',*MONTHS]}
    temporal={}
    for m in MONTHS[1:]:
        train=[r for r in rows if r['selection_date']<m+'-01' and r['sell_date']<m+'-01']
        excluded=[]
        for key in keys:
            summary=metrics([r for r in train if r['industry_key']==key])
            if summary['n']>=5 and summary['average_net_return']<0:
                excluded.append(key)
        test=[r for r in rows if r['month']==m]
        temporal[m]=dict(training=metrics(train),excluded_industries=excluded,
                         baseline=metrics(test),retained=metrics([r for r in test if r['industry_key'] not in excluded]))
    result=dict(classification='KIS official provider industry label (KRX venue), current snapshot; historical membership unverified',
                groups=groups,concentration=concentration,temporal=temporal,
                total_candidates=len(candidates),mapped_candidates=sum(r['industry']!='UNCLASSIFIED' for r in candidates),
                distinct_codes=len({r['code'] for r in candidates}),completed=metrics(rows),
                classification_counts=dict(Counter(r['industry_key'] for r in candidates)))
    assert sum(g['completed']['n'] for g in groups.values())==len(rows)
    assert len({(r['selection_date'],r['code']) for r in rows})==len(rows)
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'classified_trades.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['selection_date','code','name','industry_market','industry','rank','buy_date','sell_date','net_return','win']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lines=['# 7~9월 관찰 후보: 공식 제공 업종명 기준 검토','',
      '출처: 한국투자증권 inquire-price의 bstp_kor_isnm. 조회시장 J(KRX). 업종명은 원문 그대로 사용하고 코스피·코스닥을 분리했다. 대표 시장 표기 KOSPI200은 KOSPI, KSQ150은 KOSDAQ으로 통합했다. 테마를 임의 업종으로 대체하지 않았다.',
      '', '현재 조회한 분류를 과거 거래에 붙인 탐색 분석이다. 7~9월 당시 업종 변경 이력은 확보하지 못했으므로 시점별 공식 분류를 검증한 백테스트가 아니다.',
      '',f'관찰 후보 {len(candidates)}건, 종목 {result["distinct_codes"]}개, 완료 거래 {len(rows)}건. 선정월 기준이며 9월은 18일까지 시세를 사용했다.',
      '', '| 시장 / 업종 | 후보 | 완료 | 승/패 | 승률 | 평균 순수익 |', '|---|---:|---:|---:|---:|---:|']
    for key,g in sorted(groups.items(),key=lambda kv:-kv[1]['completed']['n']):
        v=g['completed']; wr=f'{v["win_rate"]:.1%}' if v['n'] else '—'; avg=f'{v["average_net_return"]:+.2%}' if v['n'] else '—'
        lines.append(f'| {key} | {g["candidates"]} | {v["n"]} | {v["wins"]}/{v["losses"]} | {wr} | {avg} |')
    lines+=['','## 같은 선정일·같은 업종 후보를 순위 1개로 제한한 비교','',
        '모든 후보에서 먼저 순위로 선택한 뒤 완료 거래를 집계했다. 미완료 후보를 제거한 후 승자를 고르지 않았다. 서로 다른 날짜의 동시 보유 한도나 자금 배분은 시뮬레이션하지 않았다.',
        '', '| 기간 | 기존 거래/승률/평균 | 제한 후 거래/승률/평균 |','|---|---|---|']
    for m,g in concentration.items():
        def fmt(v):return f'{v["n"]} / {v["win_rate"]:.1%} / {v["average_net_return"]:+.2%}' if v['n'] else '0 / — / —'
        lines.append(f'| {m} | {fmt(g["baseline"])} | {fmt(g["retained"])} |')
    lines+=['','## 이전 기간만 사용한 제외 조건 확인','',
        '검토 규칙: 이전 달까지 청산된 표본이 5건 이상이고 평균 순수익이 음수인 업종을 다음 달 제외. 당월 또는 미래 청산 결과는 학습에 넣지 않았다. 현재 업종 라벨을 사용하므로 엄격한 시점별 검증은 아니다.']
    for m,t in temporal.items():lines.append(f'- {m}: 제외 업종 {t["excluded_industries"]}; 이전 청산 표본 {t["training"]["n"]}건.')
    lines+=['','## 해석의 한계','',
        '- 작은 표본의 승률 100%는 미래 승률 예측이 아니다. 동일 종목과 같은 선정일의 거래는 서로 연관된다.',
        '- 공식 업종 전체 구성종목과 당시 업종 지수는 확보하지 않았다. 관찰 후보만으로 업종 지수를 만들거나 업종 강도라고 부르지 않았다.',
        '- 따라서 업종 상승·하락 상태별 진입 허용/대기 검증은 아직 수행하지 못했다.',
        '- 기존 가격 데이터는 PROVISIONAL이며 거래일 누락 가능성과 미완료 거래 편향이 남아 있다.',
        '- 매매 규칙과 대시보드는 변경하지 않았다.',
        '', '재현: python -m tools.collect_observation_industries (공식 제공 분류 수집), python -m tools.review_official_industries (로컬 집계).',
        '', '공식 응답 필드 설명: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_price/chk_inquire_price.py']
    (OUT/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
