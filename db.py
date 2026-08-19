import os
import queue
import threading
import time
import pyodbc
from contextvars import ContextVar
from dotenv import load_dotenv

load_dotenv(override=True)

_current_database: ContextVar[str] = ContextVar(
    'current_database',
    default=os.environ.get('FABRIC_DATABASE', 'contract-warehouse')
)

def set_current_database(db_name: str):
    """Set the target Fabric warehouse database for the current async context."""
    _current_database.set(db_name)

def get_current_database() -> str:
    try:
        return _current_database.get()
    except LookupError:
        return os.environ.get('FABRIC_DATABASE', 'contract-warehouse')


# ---------------------------------------------------------------------------
# Connection pooling
#
# The Azure AD (service principal) handshake pyodbc.connect() performs
# against Fabric takes ~2.5-3s. Doing that on every single run_sql/
# get_table_schema/etc. call made every tool call pay that cost. Instead we
# keep a small pool of already-authenticated connections per database (the
# contracts and aviation warehouses each get their own pool) and hand them
# out to callers; when a caller calls .close() (every existing call site
# already does this in a finally block) the connection is returned to the
# pool instead of actually being torn down, so the next tool call reuses the
# live session for ~0ms instead of re-authenticating.
# ---------------------------------------------------------------------------

POOL_MAX_SIZE = int(os.environ.get('FABRIC_POOL_MAX_SIZE', '5'))
POOL_WARMUP_SIZE = int(os.environ.get('FABRIC_POOL_WARMUP_SIZE', '2'))
# Recycle pooled connections past this total age rather than trusting an
# idle connection to still be alive on the server side indefinitely.
POOL_MAX_CONN_AGE_SECONDS = int(os.environ.get('FABRIC_POOL_MAX_CONN_AGE_SECONDS', str(30 * 60)))
# Azure's network path (load balancer/NAT/firewall) and Fabric itself can
# silently kill a TCP connection that's sat idle for just a few minutes —
# well before POOL_MAX_CONN_AGE_SECONDS would ever catch it. Evict anything
# that's been sitting unused in the pool longer than this instead. This is a
# best-effort proactive check; run_with_connection() below is the real
# safety net for connections that still go stale in between.
POOL_MAX_IDLE_SECONDS = int(os.environ.get('FABRIC_POOL_MAX_IDLE_SECONDS', str(4 * 60)))

# SQLSTATEs / message fragments that mean the TCP connection itself died out
# from under us (idle network drop, server-side reset, etc.) rather than
# anything wrong with the query — safe to blindly retry on a new connection.
_TRANSIENT_SQLSTATES = {"08S01", "08003", "08001", "08004", "HYT00", "HYT01"}
_TRANSIENT_MESSAGE_FRAGMENTS = (
    "communication link failure",
    "established connection was aborted",
    "tcp provider",
    "connection is busy",
    "connection was forcibly closed",
)


def _is_transient_connection_error(exc: BaseException) -> bool:
    args = getattr(exc, "args", None)
    sqlstate = args[0] if args else None
    if sqlstate in _TRANSIENT_SQLSTATES:
        return True
    msg = str(exc).lower()
    return any(fragment in msg for fragment in _TRANSIENT_MESSAGE_FRAGMENTS)

_pools: dict[str, "queue.Queue"] = {}
_pools_lock = threading.Lock()


def _get_pool(db_name: str) -> "queue.Queue":
    pool = _pools.get(db_name)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(db_name)
        if pool is None:
            pool = queue.Queue(maxsize=POOL_MAX_SIZE)
            _pools[db_name] = pool
        return pool


def _raw_connect(db_name: str):
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={os.environ['FABRIC_SERVER']};"
        f"Database={db_name};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.environ['FABRIC_CLIENT_ID']};"
        f"PWD={os.environ['FABRIC_CLIENT_SECRET']};"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


class _PooledCursor:
    """Thin proxy around a pyodbc cursor that flags its parent connection as
    unhealthy if a query raises, so a broken/stale connection gets closed
    for real on release instead of being handed back to the pool for the
    next caller to fail on too."""

    __slots__ = ("_cursor", "_parent")

    def __init__(self, cursor, parent: "_PooledConn"):
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_parent", parent)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __setattr__(self, name, value):
        setattr(self._cursor, name, value)

    def execute(self, *args, **kwargs):
        try:
            return self._cursor.execute(*args, **kwargs)
        except Exception:
            object.__setattr__(self._parent, "_healthy", False)
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            object.__setattr__(self._parent, "_healthy", False)
        try:
            self._cursor.close()
        except Exception:
            pass


class _PooledConn:
    """Wraps a pyodbc connection so calling .close() on it returns it to its
    database's pool instead of tearing down the AAD-authenticated session.
    Everything else (cursor(), .timeout, .commit(), etc.) proxies straight
    through to the underlying pyodbc connection, so it's a drop-in
    replacement wherever the raw connection used to be returned."""

    __slots__ = ("_conn", "_db_name", "_created_at", "_released_at", "_closed", "_healthy")

    def __init__(self, conn, db_name: str):
        now = time.monotonic()
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_db_name", db_name)
        object.__setattr__(self, "_created_at", now)
        object.__setattr__(self, "_released_at", now)
        object.__setattr__(self, "_closed", False)
        object.__setattr__(self, "_healthy", True)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def cursor(self):
        return _PooledCursor(self._conn.cursor(), self)

    def _is_stale(self) -> bool:
        now = time.monotonic()
        return (
            now - self._created_at > POOL_MAX_CONN_AGE_SECONDS
            or now - self._released_at > POOL_MAX_IDLE_SECONDS
        )

    def _hard_close(self) -> None:
        if not self._closed:
            object.__setattr__(self, "_closed", True)
            try:
                self._conn.close()
            except Exception:
                pass

    def close(self) -> None:
        """Return this connection to its pool instead of closing it — unless
        it errored during use, is past its max lifetime, or the pool is
        already full, in which case it's actually closed."""
        if self._closed:
            return
        if not self._healthy or self._is_stale():
            self._hard_close()
            return
        object.__setattr__(self, "_released_at", time.monotonic())
        pool = _get_pool(self._db_name)
        try:
            pool.put_nowait(self)
        except queue.Full:
            self._hard_close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            object.__setattr__(self, "_healthy", False)
        self.close()


def get_connection(database: str | None = None):
    """Connection to Fabric warehouse (contract-warehouse or
    aviation-warehouse). Reuses an already-authenticated, idle connection
    from that database's pool when one is available and still fresh, rather
    than paying the ~2.5-3s AAD service-principal handshake again. Callers
    should call .close() when done (existing call sites already do) — that
    returns the connection to the pool instead of closing it for real."""
    db_name = database or get_current_database()
    pool = _get_pool(db_name)
    while True:
        try:
            pooled = pool.get_nowait()
        except queue.Empty:
            return _PooledConn(_raw_connect(db_name), db_name)
        if pooled._is_stale():
            pooled._hard_close()
            continue
        return pooled


def get_aviation_connection():
    """Connection to Fabric Aviation Data Warehouse (aviation-warehouse)."""
    aviation_db = os.environ.get('FABRIC_AVIATION_DATABASE', 'aviation-warehouse')
    return get_connection(database=aviation_db)


def run_with_connection(fn, database: str | None = None):
    """Run fn(conn) against a pooled connection, handling checkout/release
    automatically. If the connection turns out to be dead — e.g. silently
    dropped by the network while it sat idle, which can happen well before
    our own idle/age recycling catches it — transparently retry exactly
    once on a brand-new connection instead of surfacing the failure to the
    caller. Any other kind of error (bad SQL, missing table, etc.) is not
    retried and propagates immediately."""
    db_name = database or get_current_database()
    conn = get_connection(db_name)
    try:
        result = fn(conn)
    except Exception as e:
        conn.close()
        if not _is_transient_connection_error(e):
            raise
        fresh = _PooledConn(_raw_connect(db_name), db_name)
        try:
            result = fn(fresh)
        finally:
            fresh.close()
        return result
    else:
        conn.close()
        return result


def warmup_connections(databases: list[str] | None = None, per_db: int | None = None) -> None:
    """Pre-open and pool `per_db` connections for each database so the AAD
    handshake happens once at startup rather than on a user's first query.
    Meant to be kicked off in a background thread (see api.py) so it never
    blocks server startup — any request that arrives before warmup finishes
    just falls back to an on-demand connect in get_connection() as usual."""
    dbs = databases or [
        os.environ.get('FABRIC_DATABASE', 'contract-warehouse'),
        os.environ.get('FABRIC_AVIATION_DATABASE', 'aviation-warehouse'),
    ]
    n = per_db if per_db is not None else POOL_WARMUP_SIZE

    def _warm_one(db_name: str) -> None:
        for _ in range(n):
            try:
                conn = _PooledConn(_raw_connect(db_name), db_name)
            except Exception as e:
                print(f"[db] warmup connection failed for '{db_name}': {e}")
                break
            pool = _get_pool(db_name)
            try:
                pool.put_nowait(conn)
            except queue.Full:
                conn._hard_close()
                break

    threads = [
        threading.Thread(target=_warm_one, args=(name,), name=f"db-warmup-{name}", daemon=True)
        for name in dbs
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
