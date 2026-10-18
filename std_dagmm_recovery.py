"""Small recovery helpers; no detector inputs, thresholds or training changes."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil

from atomic_io import atomic_write_json, flush_file_to_disk


@contextmanager
def exclusive_lock(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b')
    handle.seek(0,os.SEEK_END)
    if handle.tell()==0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    acquired=False
    try:
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            raise BlockingIOError('Another process owns the runner lock') from error
        acquired=True
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()


def checkpoint(path,value):
    import torch
    path=Path(path)
    temporary=path.with_name('.latest_checkpoint.pt.tmp')
    torch.save(value,temporary)
    flush_file_to_disk(temporary)
    if path.exists():
        backup=path.with_name('.previous_checkpoint.pt.tmp')
        shutil.copyfile(path,backup)
        flush_file_to_disk(backup)
        os.replace(backup,path.with_name('previous_checkpoint.pt'))
    os.replace(temporary,path)


def load_checkpoint(path,protocol):
    import torch
    errors=[]
    for candidate in (Path(path),Path(path).with_name('previous_checkpoint.pt')):
        if not candidate.is_file():
            continue
        try:
            saved=torch.load(candidate,weights_only=False,map_location='cpu')
        except Exception as error:
            errors.append(f'{candidate.name}: {error}')
            continue
        if saved['protocol']!=protocol:
            raise ValueError('Checkpoint protocol/source mismatch; refusing mixed evidence')
        round_index=saved['round']
        if [r['round'] for r in saved['rows']]!=list(range(1,round_index+1)):
            errors.append(f'{candidate.name}: invalid checkpoint round sequence')
            continue
        if candidate.name!='latest_checkpoint.pt':
            print(f'Recovering from backup checkpoint at round {round_index}',flush=True)
            restore=Path(path).with_name('.recovered_checkpoint.pt.tmp')
            shutil.copyfile(candidate,restore)
            flush_file_to_disk(restore)
            os.replace(restore,path)
        return saved
    if errors:
        raise ValueError('No readable checkpoint: '+'; '.join(errors))
    return None


def publish_status(output,**value):
    atomic_write_json(Path(output)/'status.json',dict(
        updated_at_utc=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),**value))
