import json,uuid,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def node(name,typ,pos,params,version=1):
    return {'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'iisc-demo:'+name)),'name':name,'type':'n8n-nodes-base.'+typ,'typeVersion':version,'position':pos,'parameters':params}
def http(name,pos,url,body):
    n=node(name,'httpRequest',pos,{'method':'POST','url':url,'sendBody':True,'specifyBody':'json','jsonBody':body,'options':{'timeout':180000}},4.4);n['onError']='continueRegularOutput';return n

def switch(name,pos,left,values):
    return node(name,'switch',pos,{'rules':{'values':[{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':str(uuid.uuid4()),'leftValue':left,'rightValue':v,'operator':{'type':'string','operation':'equals'}}],'combinator':'and'},'renameOutput':True,'outputKey':v} for v in values]},'options':{'fallbackOutput':'extra'}},3.3)

def complete(name,pos,title,message):
    return node(name,'form',pos,{'operation':'completion','respondWith':'text','completionTitle':title,'completionMessage':message,'options':{}},2.5)
VALIDATE=r'''const data=$input.first().json; const errors=[];
let req=$('Shopping Request').first().json['Shopping request'];
const m=String(req).replaceAll(',','').match(/(?:under|below|budget|up to)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(k)?/i);
const budget=m?Number(m[1])*(m[2]?1000:1):NaN;
if(!Number.isFinite(budget)||budget<=0)errors.push('Missing numeric budget');
if(data.error)errors.push('Adapter error');
if(data.provider!=='codex_cli')errors.push('Unexpected provider');
if(data.evidence_mode!=='live_browser')errors.push('Live evidence required');
if(!data.deterministic_validation?.passed)errors.push('Adapter validation did not pass');
if(data.parsed_request?.budget_inr!==budget)errors.push('Budget changed during interpretation');
if(data.parsed_request?.approval_required!==true)errors.push('Approval invariant missing');
if(typeof data.confidence!=='number'||data.confidence<0||data.confidence>1)errors.push('Invalid confidence');
if(data.status==='READY_FOR_APPROVAL'){
 const o=data.selected_offer;
 if(!o)errors.push('Missing candidate');else{
  const match=String(o.source_url||'').match(/^https:\/\/([^/?#]+)/i);let host=match?match[1].toLowerCase():'';if(!host)errors.push('Invalid URL');
  const domain={Amazon:'amazon.in',Flipkart:'flipkart.com',Myntra:'myntra.com'}[o.marketplace];
  if(!domain||!(host===domain||host.endsWith('.'+domain)))errors.push('Source host mismatch');
  if(!(o.observed_price_inr>0&&o.observed_price_inr<budget))errors.push('Observed price fails budget');
  const age=Date.now()-Date.parse(o.observed_at);if(!Number.isFinite(age)||age>900000||age< -60000)errors.push('Evidence expired');
  const candidates=$('Browser Agent — Search Marketplaces').first().json.candidates||[];
  if(!candidates.some(c=>c.offer_id===o.offer_id&&c.source_url===o.source_url&&c.observed_price_inr===o.observed_price_inr))errors.push('Candidate not in collected evidence');
 }
}
return [{json:{...data,lane:errors.length===0&&data.status==='READY_FOR_APPROVAL'?'approval':'no_match',validation_errors:errors,validation_checked_at:new Date().toISOString()}}];'''

def build():
    trigger=node('Shopping Request','formTrigger',[0,0],{'formTitle':'Live marketplace research agent','formDescription':'A visible browser gathers public evidence. Codex ranks the observations. You approve only a simulated action.','formFields':{'values':[{'fieldLabel':'Shopping request','fieldType':'textarea','defaultValue':'Find black running shoes under ₹1,000. Ask me before ordering.','requiredField':True}]},'options':{'path':'live-browser-codex-shopping','buttonLabel':'Search live marketplaces'},'responseMode':'onReceived'},2.2);trigger['webhookId']='live-browser-codex-shopping'
    nodes=[trigger,http('Browser Agent — Search Marketplaces',[260,0],'http://127.0.0.1:8002/search',"={{ {request: $json['Shopping request']} }}"),http('Codex Agent — Normalize & Rank',[520,0],'http://127.0.0.1:8002/recommend-live',"={{ {request: $('Shopping Request').first().json['Shopping request'], search_results: $json} }}"),node('Validate Live Evidence','code',[780,0],{'jsCode':VALIDATE},2),switch('Route Recommendation',[1040,0],'={{ $json.lane }}',['approval'])]
    description="={{ (() => { const p=$('Validate Live Evidence').first().json; const o=p.selected_offer; const esc=s=>String(s).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); return '<h3>Review live browser evidence</h3><p><strong>'+esc(o.product_name)+'</strong> on '+esc(o.marketplace)+'</p><p>Observed item price: ₹'+o.observed_price_inr+' · Budget: ₹'+p.parsed_request.budget_inr+'</p><p><a href=\"'+esc(o.source_url)+'\" target=\"_blank\">Open source evidence</a></p><p>Observed: '+esc(o.observed_at)+'</p><p>Evidence: '+esc(o.evidence_mode)+'</p><p>Unverified: '+esc(o.unverified_fields.join(', '))+'</p><strong>Approval authorizes only a simulated action. No marketplace order or payment occurs. Checkout total is unverified.</strong>'; })() }}"
    form=node('Human Approval','form',[1300,-160],{'operation':'page','defineForm':'json','jsonOutput':json.dumps([{'fieldLabel':'Your decision','fieldType':'radio','fieldOptions':{'values':[{'option':'Approve simulated order'},{'option':'Cancel'}]},'requiredField':True}]),'options':{'formTitle':'Human approval gate','formDescription':description,'buttonLabel':'Continue'},'limitWaitTime':True,'limitType':'afterTimeInterval','resumeAmount':15,'resumeUnit':'minutes'},2.5)
    nodes += [form,switch('Route Human Decision',[1560,-160],"={{ $json['Your decision'] || 'Cancel' }}",['Approve simulated order']),http('Create Simulated Order',[1820,-160],'http://127.0.0.1:8001/order-live',"={{ {approved: true, proposal_id: $('Validate Live Evidence').first().json.proposal_id, selected_offer: $('Validate Live Evidence').first().json.selected_offer} }}"),complete('Order Confirmation',[2080,-160],"={{ $json.status === 'SIMULATED' ? 'Simulated action completed' : 'Action stopped' }}","={{ $json.status === 'SIMULATED' ? 'Reference: '+$json.order_id+' · Payment taken: false · Marketplace contacted: false. Freshness and proposal identity were rechecked.' : 'No simulated action completed. '+JSON.stringify($json.error || $json) }}"),complete('No Match',[1300,180],'No eligible recommendation',"={{ 'No action performed. '+(($('Validate Live Evidence').first().json.validation_errors || []).join('. '))+' '+($('Validate Live Evidence').first().json.reasons || []).join(' ') }}"),complete('Cancelled',[1820,100],'Cancelled or timed out','The simulated action did not run. No payment or marketplace order occurred.')]
    con={}
    def link(a,b,out=0):
        arr=con.setdefault(a,{'main':[]})['main']
        while len(arr)<=out:arr.append([])
        arr[out].append({'node':b,'type':'main','index':0})
    for a,b in [('Shopping Request','Browser Agent — Search Marketplaces'),('Browser Agent — Search Marketplaces','Codex Agent — Normalize & Rank'),('Codex Agent — Normalize & Rank','Validate Live Evidence'),('Validate Live Evidence','Route Recommendation'),('Route Recommendation','Human Approval'),('Human Approval','Route Human Decision'),('Route Human Decision','Create Simulated Order'),('Create Simulated Order','Order Confirmation')]:link(a,b)
    link('Route Recommendation','No Match',1);link('Route Human Decision','Cancelled',1)
    flow={'id':'IISCLiveBrowserCodex','name':'LIVE — Browser search + Codex + human approval','nodes':nodes,'connections':con,'active':False,'settings':{'executionOrder':'v1','saveExecutionProgress':True,'executionTimeout':1200,'timezone':'Asia/Kolkata'},'versionId':str(uuid.uuid4())}
    (ROOT/'live-browser-codex-hitl-workflow.json').write_text(json.dumps(flow,indent=2,ensure_ascii=False))
    starter=copy.deepcopy(flow);starter['id']='IISCStarterBrowser';starter['name']='STARTER — Add the live browser search node';starter['nodes']=[n for n in starter['nodes'] if n['name']!='Browser Agent — Search Marketplaces'];starter['connections'].pop('Browser Agent — Search Marketplaces');starter['connections']['Shopping Request']={'main':[[{'node':'Codex Agent — Normalize & Rank','type':'main','index':0}]]};starter['nodes'][0]['parameters']['options']['path']='live-browser-codex-shopping-starter';starter['nodes'][0]['webhookId']='live-browser-codex-shopping-starter';(ROOT/'live-browser-codex-hitl-starter.json').write_text(json.dumps(starter,indent=2,ensure_ascii=False))
    # Verify the side-effect node has exactly one approved incoming edge.
    incoming=[(src,i) for src,v in con.items() for i,edges in enumerate(v['main']) for edge in edges if edge['node']=='Create Simulated Order']
    assert incoming==[('Route Human Decision',0)]
    print('Built live workflow: 11 nodes; starter: 10 nodes; one approved action edge')
if __name__=='__main__':build()
