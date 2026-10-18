"""Bounded, persistent upload validation reports; source is an unsaved draft."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from ..player.process import terminate_tree


class ValidationJobs:
    def __init__(self,database,save):
        self.database=database;self.save=save
        self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='catan-validation')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS player_validations (id TEXT PRIMARY KEY, owner TEXT, report TEXT NOT NULL)')
            for vid,raw in db.execute('SELECT id,report FROM player_validations'):
                report=json.loads(raw)
                if report['status'] in ('queued','running'):
                    report['status']='failed'
                    for item in report['stages'].values():
                        if item['status'] in ('pending','running'): item.update(status='failed',message='Server restarted. Upload this version again.')
                    db.execute('UPDATE player_validations SET report=? WHERE id=?',(json.dumps(report),vid))

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.database,timeout=30)
        try:
            with connection:yield connection
        finally:connection.close()

    def get(self,vid,owner):
        with self.connect() as db:
            row=db.execute('SELECT owner,report FROM player_validations WHERE id=?',(vid,)).fetchone()
        if row is None or row[0]!=owner: raise KeyError(vid)
        return json.loads(row[1])

    def write(self,report):
        with self.connect() as db:
            db.execute('UPDATE player_validations SET report=? WHERE id=?',(json.dumps(report),report['validation_id']))

    def submit(self,payload,owner):
        with self.lock,self.connect() as db:
            rows=db.execute('SELECT owner,report FROM player_validations').fetchall()
            active=[o for o,r in rows if json.loads(r)['status'] in ('queued','running')]
            if owner in active: raise ValueError('You already have an upload being validated. Wait for it to finish.')
            if len(active)>=8: raise ValueError('The validation queue is full. Try again shortly.')
            report={'validation_id':uuid.uuid4().hex,'status':'queued','validated':False,
                    'stages':{key:{'status':'pending','message':'Waiting'} for key in ('quick','scenarios','games')}}
            db.execute('INSERT INTO player_validations VALUES (?,?,?)',(report['validation_id'],owner,json.dumps(report)))
        self.pool.submit(self.execute,payload,owner,report)
        return report

    def execute(self,payload,owner,report):
        process=None
        try:
            with tempfile.TemporaryDirectory(prefix='catan_validation_') as directory:
                job=Path(directory)/'job.json';output=Path(directory)/'report.json'
                job.write_text(json.dumps({'code':payload['bot_code'],'report':report}),encoding='utf-8')
                process=subprocess.Popen([sys.executable,'-m','src.platform.validation_worker',str(job),str(output)],
                    cwd=Path(__file__).resolve().parents[2],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                deadline=time.monotonic()+600
                while process.poll() is None:
                    if time.monotonic()>deadline: raise TimeoutError('Validation exceeded its ten-minute limit. Try simplifying the player or checking it locally.')
                    if output.exists():
                        try:
                            report=json.loads(output.read_text(encoding='utf-8'))
                            if report['status']=='passed': report['status']='running'
                            self.write(report)
                        except (json.JSONDecodeError,PermissionError): pass
                    time.sleep(.2)
                if process.returncode or not output.exists(): raise RuntimeError('Validation worker stopped unexpectedly. Retry the upload; no player version was saved.')
                report=json.loads(output.read_text(encoding='utf-8'))
            if report['status']=='passed':
                package=self.save(payload,owner)
                report.update(package,validated=True)
        except Exception as error:
            if process is not None: terminate_tree(process)
            report['status']='failed';report['validated']=False
            running=next((item for item in report['stages'].values() if item['status']=='running'),report['stages']['quick'])
            running.update(status='failed',message=str(error),details={'error':str(error),'category':'infrastructure'})
        finally:
            if report['status']=='failed':
                for item in report['stages'].values():
                    if item['status']=='pending': item.update(status='skipped',message='Not run because an earlier stage failed')
                report['validation_errors']=[s['message'] for s in report['stages'].values() if s['status']=='failed']
            self.write(report)

    def wait(self,report,owner):
        while report['status'] in ('queued','running'):
            time.sleep(.1);report=self.get(report['validation_id'],owner)
        return report
