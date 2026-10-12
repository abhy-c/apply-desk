"""Atomic private files and a reentrant, interprocess workspace transaction lock."""
from contextlib import contextmanager
from functools import wraps
from inspect import signature
from pathlib import Path
import csv, io, json, os, tempfile, threading, time

_LOCKS = {}
_GUARD = threading.Lock()
_DEPTH = threading.local()

@contextmanager
def transaction(data_dir: Path):
    directory = Path(data_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt': directory.chmod(0o700)
    key = str(directory)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        depths = getattr(_DEPTH, 'values', {})
        _DEPTH.values = depths
        if depths.get(key, 0):
            depths[key] += 1
            try: yield
            finally: depths[key] -= 1
            return
        with (directory / '.storage.lock').open('a+b') as handle:
            if os.name != 'nt':
                os.chmod(handle.name, 0o600)
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            else:
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b'0'); handle.flush()
                deadline = time.monotonic() + 30
                while True:
                    try:
                        handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1); break
                    except OSError:
                        if time.monotonic() >= deadline: raise TimeoutError('Workspace is busy')
                        time.sleep(0.05)
            depths[key] = 1
            try: yield
            finally:
                depths.pop(key)
                if os.name != 'nt': fcntl.flock(handle, fcntl.LOCK_UN)
                else:
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

def transactional(argument, kind='data'):
    def decorate(function):
        sig = signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            bound = sig.bind(*args, **kwargs); bound.apply_defaults()
            path = Path(bound.arguments[argument])
            directory = path / 'data' if kind == 'project' else path.parent if kind == 'file' else path.parent / 'data' if kind == 'out' else path
            with transaction(directory): return function(*args, **kwargs)
        return wrapped
    return decorate

def atomic_text(path: Path, text: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def atomic_json(path: Path, payload):
    atomic_text(path, json.dumps(payload, indent=2) + '\n')

def csv_cell(value):
    if isinstance(value, str) and value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value

def atomic_csv(path: Path, rows, fields, spreadsheet_safe=False):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: csv_cell(v) for k,v in row.items()} if spreadsheet_safe else row)
    atomic_text(path, buffer.getvalue())


@contextmanager
def instance_lock(directory: Path):
    """Only one HTTP server may own a workspace code at a time."""
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (directory / '.server.lock').open('a+b') as handle:
        locked=False
        try:
            if os.name!='nt':
                import fcntl
                os.chmod(handle.name,0o600)
                fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                handle.seek(0,os.SEEK_END)
                if handle.tell()==0: handle.write(b'0');handle.flush()
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            locked=True
        except OSError:
            raise ValueError('A server already owns this workspace. Stop it before starting another.') from None
        try: yield
        finally:
            if locked:
                if os.name!='nt': fcntl.flock(handle,fcntl.LOCK_UN)
                else:
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
