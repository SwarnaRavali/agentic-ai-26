#!/usr/bin/env python3
"""Start/stop only this workspace's demo services. Binds to loopback."""
import os,sys,json,subprocess,socket,time,signal,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PY=ROOT/'.venv/bin/python'
NODE_BIN=os.environ.get('NODE_BIN') or shutil.which('node')
if not NODE_BIN:raise SystemExit('Install Node.js and add node to PATH, or set NODE_BIN.')
NODE=Path(NODE_BIN).resolve().parent
PIDFILE=ROOT/'service-pids.json'
SERVICES=[('marketplace',8002,[str(PY),str(ROOT/'marketplace_service/service.py')]),('crewai',8765,[str(PY),str(ROOT/'crewai_hands_on/server.py')]),('n8n',5678,[str(NODE/'node'),str(ROOT/'runtime/node_modules/n8n/bin/n8n'),'start'])]
def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.4):return True
    except OSError:return False

def main():
    action=sys.argv[1] if len(sys.argv)>1 else 'start'
    for directory in ['logs','runs','llm-work']:(ROOT/directory).mkdir(exist_ok=True)
    pids=json.loads(PIDFILE.read_text()) if PIDFILE.exists() else {}
    if action=='stop':
        for name,pid in pids.items():
            try:
                cmd=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
                cwd=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True)
                owned=str(ROOT) in cmd or ('n'+str(ROOT)+'\n' in cwd and cmd.strip().startswith('n8n'))
                if owned:os.killpg(pid,signal.SIGTERM);print('Stopped',name)
            except (ProcessLookupError,subprocess.CalledProcessError):pass
        for _ in range(50):
            if not any(listening(port) for _,port,_ in SERVICES):break
            time.sleep(.1)
        PIDFILE.write_text('{}');return
    if action not in ['start','status']:raise SystemExit('Usage: manage.py start|status|stop')
    env=os.environ.copy();env['PATH']=str(NODE)+os.pathsep+env.get('PATH','');env.update({'N8N_USER_FOLDER':str(ROOT/'.n8n-live'),'N8N_LISTEN_ADDRESS':'127.0.0.1','N8N_HOST':'127.0.0.1','N8N_PROTOCOL':'http','N8N_SECURE_COOKIE':'false','N8N_DIAGNOSTICS_ENABLED':'false','N8N_PERSONALIZATION_ENABLED':'false','N8N_VERSION_NOTIFICATIONS_ENABLED':'false','OTEL_SDK_DISABLED':'true','CREWAI_TELEMETRY_OPT_OUT':'true','CREWAI_TRACING_ENABLED':'false'})
    for name,port,args in SERVICES:
        if action=='start' and not listening(port):
            log=(ROOT/'logs'/f'{name}-server.log').open('a');proc=subprocess.Popen(args,cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);pids[name]=proc.pid;log.close()
            for _ in range(100):
                if listening(port) or proc.poll() is not None:break
                time.sleep(.2)
        print(name,('RUNNING' if listening(port) else 'STOPPED'),f'http://127.0.0.1:{port}')
    if action=='start':PIDFILE.write_text(json.dumps(pids,indent=2))
if __name__=='__main__':main()
