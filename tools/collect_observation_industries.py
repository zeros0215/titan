"""Collect provider industry labels without inventing thematic categories."""
import json
from datetime import datetime
from pathlib import Path

from broker.kis.current_price import KisCurrentPriceProvider
from broker.kis.constants import CURRENT_PRICE_URL, TR_CURRENT_PRICE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/reports/observation_industry_202607_09'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    codes={}
    for path in (ROOT/'output/kis_manual_tests/runs').glob('LOCAL_2026*_H20_V1_3_S80_N7_TP5_SL10_CANDIDATE_TP5_SL10.json'):
        run=json.loads(path.read_text(encoding='utf-8'))
        if run['as_of'][:7] in ('2026-07','2026-08','2026-09'):
            codes.update({r['code']:r['name'] for r in run['observation_candidates']})
    path=OUT/'industry_labels.json'
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    provider=KisCurrentPriceProvider()
    try:
        for index,(code,name) in enumerate(sorted(codes.items()),1):
            if code in data and data[code].get('industry'):
                continue
            payload=provider.session.get(CURRENT_PRICE_URL,TR_CURRENT_PRICE,
                {'FID_COND_MRKT_DIV_CODE':'J','FID_INPUT_ISCD':code}).json()
            if payload.get('rt_cd')!='0':
                raise RuntimeError(f'{code}: {payload.get("msg_cd")} {payload.get("msg1")}')
            output=payload.get('output',{})
            data[code]=dict(code=code,name=name,industry=output.get('bstp_kor_isnm','').strip(),
                market=output.get('rprs_mrkt_kor_name','').strip(),
                collected_at=datetime.now().astimezone().isoformat(),
                source='KIS inquire-price, FID_COND_MRKT_DIV_CODE=J, bstp_kor_isnm',
                historical_classification_verified=False)
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'{index}/{len(codes)} {code}',flush=True)
    finally:
        provider.close()
    print('complete',len(data),flush=True)


if __name__=='__main__':
    main()
