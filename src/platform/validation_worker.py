"""Disposable validation process; no database, room or match-catalog access."""
import json
import os
from pathlib import Path
import sys
import time
from .player_validation import validate


def publish(output,report):
    temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps(report),encoding='utf-8')
    # Windows readers briefly prevent replacement of an open destination.
    for attempt in range(50):
        try:os.replace(temporary,output);return
        except PermissionError:
            if attempt==49:raise
            time.sleep(.01)


def main():
    job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    report=job['report'];output=Path(sys.argv[2])
    def progress(stage,status,message,**extra):
        report['status']='running'
        report['stages'][stage].update(status=status,message=message,**extra)
        if status=='failed':
            report['status']='failed'
            report['validation_errors']=[message]
            for item in report['stages'].values():
                if item['status']=='pending': item.update(status='skipped',message='Not run because an earlier stage failed')
        publish(output,report)
    success=validate(job['code'],progress)
    report['status']='passed' if success else 'failed'
    publish(output,report)


if __name__=='__main__': main()
