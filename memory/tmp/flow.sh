#!/usr/bin/env bash
# Uji alur: reservasi (all-in EXCLUDE + add-on + promo ALL IN) → bayar BF → booking → jadikan pembeli → cek AR/kontrak
UNIT=${1:-70226946-fe7f-4477-b78b-40b837820de5}
PROMO_EXTRA=${2:-}
B=localhost:8001/api
TOKEN=$(curl -s -X POST $B/auth/login -H "Content-Type: application/json" -d '{"email":"manager@sipro.co.id","password":"Sipro#2026"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('token') or d.get('access_token') or d.get('data',{}).get('token'))")
FTOK=$(curl -s -X POST $B/auth/login -H "Content-Type: application/json" -d '{"email":"finance@sipro.co.id","password":"Sipro#2026"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('token') or d.get('access_token') or d.get('data',{}).get('token'))")
PID=$(curl -s "$B/pricing/promos" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);d=d.get('data',d);print([p['id'] for p in d if p['code']=='PROMO-ALLIN27'][0])")
LEAD=$(curl -s "$B/leads?limit=100" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json;d=json.load(sys.stdin)['data']
print([l['id'] for l in d if not l.get('unit_id') and l.get('stage') not in ('booking','won')][0])")
echo "unit=$UNIT lead=$LEAD"
curl -s -X POST $B/deals/reserve -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"unit_id\":\"$UNIT\",\"lead_id\":\"$LEAD\",\"addons\":[{\"code\":\"ADD-DAPUR\",\"qty\":1}],\"scheme_id\":\"9251d866-973f-4bc6-9bff-37549fa319ae\",\"promo_id\":\"$PID\",$PROMO_EXTRA\"allin_scheme_id\":\"5723fd86-b250-4d18-8a01-eaaed8229e90\",\"booking_fee\":5000000,\"limit_override_reason\":\"uji perhitungan booking all-in\"}" > /app/memory/tmp/deal.json
DID=$(python3 -c "
import json;d=json.load(open('/app/memory/tmp/deal.json'))
if 'detail' in d: print('ERR',d['detail']); raise SystemExit
d=d['data']; print(d['id'])
p=d['pricing']
import sys
sys.stderr.write(str({k:p.get(k) for k in ('gross_price','discount_amount','net_price','cost_discount_amount','total_discount_amount','buyer_total','booking_fee','by_target')})+'\n')
for x in d['costs']['components']: sys.stderr.write('  comp %s %s amt=%s disc=%s\n'%(x['code'],x['treatment'],x['amount'],x.get('discount')))
")
echo "deal=$DID"
[[ "$DID" == ERR* ]] && exit 1
curl -s -X POST $B/booking-fee/deals/$DID/pay -H "Authorization: Bearer $FTOK" -H "Content-Type: application/json" -d '{"amount":5000000,"method":"transfer","note":"uji"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('BF pay:', d.get('detail') or d['data']['invoice']['status'])"
curl -s -X POST $B/deals/$DID/book -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('book:', d.get('detail') or d['data']['status'])"
sleep 2
curl -s -X POST $B/deals/$DID/convert -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('convert:', d.get('detail') or d['data'].get('created'))"
sleep 2
echo "--- AR"
curl -s $B/finance/ar/$DID -H "Authorization: Bearer $FTOK" | python3 -c "
import sys,json;d=json.load(sys.stdin);i=d.get('data') or {}
print('AR price',i.get('price'),'total',i.get('total'),'paid',i.get('paid'),'outstanding',i.get('outstanding'))
b=i.get('breakdown') or {}
print('breakdown', {k:v for k,v in b.items() if k not in ('payment_breakdown','cost_components','addons','discount_lines')})
print('cost comps',[(c['code'],c['gross'],c['discount'],c['amount']) for c in b.get('cost_components',[])])
print('cost_invoices',[(c['number'],c['total'],c['outstanding'],c['status'],[(it['code'],it['amount'],it.get('discount')) for it in c['items']]) for c in d.get('cost_invoices',[])])"
echo "--- AR list"
curl -s "$B/finance/ar?limit=3" -H "Authorization: Bearer $FTOK" | python3 -c "
import sys,json;d=json.load(sys.stdin)
for r in d['data']: print(r['unit_code'],r['total'],r.get('cost_total'),r.get('cost_outstanding'),r.get('buyer_total'),r.get('cost_invoice_numbers'))"
echo "--- contract"
curl -s "$B/contracts/by-deal/$DID" -H "Authorization: Bearer $FTOK" | python3 -c "
import sys,json;d=json.load(sys.stdin);c=d.get('data')
if not c: print('NO CONTRACT', d); raise SystemExit
b=c.get('breakdown') or {}
for r in b.get('rows',[]): print('  %-16s %-40s %15s %s'%(r['code'],r['label'][:40],str(r['amount']),r['state']))
print({k:v for k,v in b.items() if k!='rows'})"
