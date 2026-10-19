import sys,json,os,time,uuid,secrets,hashlib,threading,subprocess,re,shutil
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_bridge import infer
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'runs').mkdir(exist_ok=True)
NODE=os.environ.get('NODE_BIN') or shutil.which('node') or 'node'
ALLOWED={'Amazon':'amazon.in','Flipkart':'flipkart.com','Myntra':'myntra.com'}
STATE=ROOT/'runs/proposal-store.json'
try:
    stored=json.loads(STATE.read_text()) if STATE.exists() else {}
except ValueError: stored={}
PROPOSALS=stored.get('proposals',{});ORDERS=stored.get('orders',{});LOCK=threading.Lock()
def persist():
    temp=STATE.with_suffix('.tmp');temp.write_text(json.dumps({'proposals':PROPOSALS,'orders':ORDERS},ensure_ascii=False));temp.chmod(0o600);temp.replace(STATE)

def budget(request):
    m=re.search(r'(?:under|below|budget|up to)\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(k)?',request.lower())
    if not m:raise ValueError('A numeric budget is required')
    v=float(m.group(1).replace(',',''))*(1000 if m.group(2) else 1)
    if v<=0:raise ValueError('Budget must be positive')
    return v

def check(offer,limit):
    errors=[]
    try:
        u=urlparse(offer['source_url']);host=u.hostname or '';expected=ALLOWED[offer['marketplace']]
        if u.scheme!='https' or not(host==expected or host.endswith('.'+expected)):errors.append('Source host mismatch')
        price=float(offer['observed_price_inr'])
        if not 0<price<limit:errors.append('Observed item price is not below budget')
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(offer['observed_at'].replace('Z','+00:00'))).total_seconds()
        if age< -60 or age>900:errors.append('Evidence expired or has an invalid timestamp')
        evidence=(offer.get('product_name','')+' '+offer.get('source_excerpt','')).lower()
        if 'black' not in evidence or 'running' not in evidence:errors.append('Missing required color/category evidence')
    except (KeyError,ValueError,TypeError):errors.append('Malformed evidence')
    return errors

def search(request):
    budget(request)
    if 'black' not in request.lower() or 'running shoes' not in request.lower():raise ValueError('This demo supports black running shoes')
    env=os.environ.copy();env.setdefault('MARKETPLACE_BROWSER_HEADLESS','0')
    proc=subprocess.run([NODE,str(ROOT/'marketplace_service/browser_search.cjs'),request],capture_output=True,text=True,timeout=145,env=env)
    if proc.returncode:raise RuntimeError('Browser collector failed; no evidence was substituted')
    data=json.loads(proc.stdout);(ROOT/'runs/live-browser-search.json').write_text(json.dumps(data,indent=2,ensure_ascii=False));return data

RANK_SCHEMA={'type':'object','properties':{'selected_offer_id':{'type':['string','null']},'status':{'type':'string','enum':['READY_FOR_APPROVAL','NO_MATCH','MANUAL_REVIEW']},'reasons':{'type':'array','items':{'type':'string'}},'confidence':{'type':'number'}},'required':['selected_offer_id','status','reasons','confidence'],'additionalProperties':False}

def recommend(request,evidence):
    limit=budget(request);candidates=evidence.get('candidates',[])
    valid=[o for o in candidates if not check(o,limit)]
    prompt='Rank these supplied candidates only. Request: '+request+'\nBudget strictly below INR '+str(limit)+'. Choose the cheapest eligible item, never invent evidence. Missing required color/category or an over-budget price is ineligible. No eligible candidate means NO_MATCH and null. This is a simulated-action demonstration, so optional unknown size/stock/delivery/returns/shipping remain explicit for the human. Do not claim a real purchase is possible.\nCandidates: '+json.dumps(candidates,ensure_ascii=False)+'\nDeterministically eligible IDs: '+json.dumps([o['offer_id'] for o in valid])
    answer,meta=infer(prompt,RANK_SCHEMA);rank=json.loads(answer)
    if not 0<=rank['confidence']<=1:raise ValueError('Invalid model confidence')
    selected=next((o for o in candidates if o['offer_id']==rank['selected_offer_id']),None)
    errors=check(selected,limit) if selected else []
    if rank['selected_offer_id'] and not selected:errors.append('Model selected an unknown candidate')
    if rank['status']=='READY_FOR_APPROVAL' and selected is None:errors.append('Ready result has no selected candidate')
    if selected and rank['status']!='READY_FOR_APPROVAL':errors.append('Selected candidate with non-ready status')
    if not selected and valid and rank['status']=='NO_MATCH':errors.append('Model missed eligible candidates')
    if selected and valid and selected['observed_price_inr']!=min(o['observed_price_inr'] for o in valid):errors.append('Model did not choose the cheapest eligible candidate')
    status=rank['status'] if not errors else 'MANUAL_REVIEW';pid=secrets.token_urlsafe(24)
    result={'provider':'codex_cli','model':'account-default','evidence_mode':'live_browser','parsed_request':{'request_id':str(uuid.uuid4()),'request':request,'category':'running shoes','color':'black','budget_inr':limit,'approval_required':True},'status':status,'selected_offer':selected,'reasons':rank['reasons'],'confidence':rank['confidence'],'unverified_fields':selected.get('unverified_fields',[]) if selected else [],'codex_trace':meta,'deterministic_validation':{'passed':not errors,'errors':errors},'proposal_id':pid,'lane':'approval' if status=='READY_FOR_APPROVAL' else 'no_match','sources':evidence.get('sources',[]),'simulation_only':True,'created_at':time.time()}
    if result['lane']=='approval':
        with LOCK:
            PROPOSALS[pid]=json.loads(json.dumps(result));persist()
    (ROOT/'runs/live-browser-ranked.json').write_text(json.dumps(result,indent=2,ensure_ascii=False));return result

def order(body):
    if body.get('approved') is not True:raise ValueError('Explicit simulated-action approval is required')
    pid=body.get('proposal_id')
    with LOCK:
        prop=PROPOSALS.get(pid)
        if not prop:raise ValueError('Unknown proposal; run validation again')
        if pid in ORDERS:return ORDERS[pid]
        if prop['lane']!='approval' or not prop['deterministic_validation']['passed']:raise ValueError('Proposal is not eligible')
        offer=prop['selected_offer']
        if body.get('selected_offer')!=offer:raise ValueError('Proposal identity changed after approval')
        errors=check(offer,prop['parsed_request']['budget_inr'])
        if errors:raise ValueError('Recheck failed: '+', '.join(errors))
        result={'status':'SIMULATED','order_id':'DEMO-LIVE-'+str(int(time.time()*1000)),'selected_offer':offer,'payment_taken':False,'marketplace_contacted':False,'proposal_id':pid,'approved':True,'rechecked_at':datetime.now(timezone.utc).isoformat()}
        ORDERS[pid]=result;persist()
        (ROOT/'runs/live-browser-approved.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
        return result

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data,code=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path in ['/health','/api/health']:
            self.reply({'status':'ok','provider':'codex_cli','authentication':'existing ChatGPT login','api_key_required':False,'browser_automation':{'available':True,'visible':os.getenv('MARKETPLACE_BROWSER_HEADLESS','0')!='1'},'mode':'simulation_only','proposal_count':len(PROPOSALS),'simulated_order_count':len(ORDERS)})
        else:self.reply({'error':'Not found'},404)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<2000000:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(size))
            if self.path=='/search':data=search(body['request'])
            elif self.path=='/recommend-live':data=recommend(body['request'],body.get('search_results',{}))
            elif self.path=='/order-live':data=order(body)
            elif self.path=='/recheck':
                prop=PROPOSALS.get(body.get('proposal_id'))
                if not prop:raise ValueError('Proposal no longer exists')
                errors=check(prop['selected_offer'],prop['parsed_request']['budget_inr']);data={'passed':not errors,'errors':errors}
            else:self.reply({'error':'Not found'},404);return
            self.reply(data)
        except (ValueError,KeyError,TypeError) as e:self.reply({'error':str(e)},400)
        except subprocess.TimeoutExpired:self.reply({'error':'Upstream operation timed out; no action performed'},504)
        except Exception as e:self.reply({'error':str(e)},502)

def serve(port):ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
if __name__=='__main__':
    threading.Thread(target=serve,args=(8001,),daemon=True).start();print('Marketplace adapter :8002, simulated action :8001',flush=True);serve(8002)
