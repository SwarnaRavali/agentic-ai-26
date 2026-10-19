import sys,json,threading,time,uuid,traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lab import generate,run
ROOT=Path(__file__).resolve().parents[1];JOBS={};RUN_LOCK=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,data,status=200,ctype='application/json'):
        raw=data.encode() if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/':return self.send((ROOT/'crewai_hands_on/builder.html').read_text(),ctype='text/html; charset=utf-8')
        if self.path=='/api/health':return self.send({'status':'ok','framework':'CrewAI','provider':'codex_cli','mode':'LIVE','evidence_mode':'live_browser','sources':['Amazon','Flipkart','Myntra'],'side_effect_tools':[]})
        if self.path.startswith('/api/job/'):
            j=JOBS.get(self.path.split('/')[-1]);return self.send(j or {'error':'Unknown run'},200 if j else 404)
        if self.path=='/api/runs':
            files=sorted((ROOT/'runs').glob('crew-*.json'),key=lambda p:p.stat().st_mtime)
            return self.send([{'file':p.name,'mode':'SAVED_LIVE_RUN'} for p in files if json.loads(p.read_text()).get('evidence_mode')=='live_browser'])
        self.send({'error':'Not found'},404)
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            if self.path=='/api/lab/build':return self.send(generate(body.get('spec',{})))
            if self.path=='/api/lab/run':
                if not RUN_LOCK.acquire(False):return self.send({'error':'A live crew is already running. Wait for it to finish.'},409)
                ident=uuid.uuid4().hex;job={'id':ident,'state':'running','events':[],'started_at':time.time()};JOBS[ident]=job
                def work():
                    try:
                        result=run(body.get('spec',{}),body['request'],job['events'].append);job['result']=result;job['state']='complete';(ROOT/'runs'/('crew-'+ident+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False))
                    except Exception as e:
                        job['state']='failed';job['error']=str(e);(ROOT/'logs'/('crew-'+ident+'.log')).write_text(traceback.format_exc())
                    finally:RUN_LOCK.release()
                threading.Thread(target=work,daemon=True).start();return self.send({'job_id':ident})
            if self.path=='/api/replay':
                name=body['file']
                if '/' in name or not name.startswith('crew-'):raise ValueError('Invalid run')
                result=json.loads((ROOT/'runs'/name).read_text());result['display_mode']='RECORDED_REPLAY';return self.send(result)
            self.send({'error':'Not found'},404)
        except Exception as e:self.send({'error':str(e)},400)
if __name__=='__main__':
    print('CrewAI visual builder: http://127.0.0.1:8765',flush=True);ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
