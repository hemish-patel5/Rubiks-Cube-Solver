# Runtime architecture

The application is a modular Python program with one narrow concurrency boundary. The
main thread owns the camera, OpenCV windows, validation, solution, move guidance, and
durable local recording. The `remote-sync` daemon thread owns potentially slow HTTP
communication.

```mermaid
flowchart LR
    Camera[Camera / OpenCV] --> Main[Main workflow thread]
    Keyboard[Keyboard controls] --> Main
    Main --> Solver[Validation and Kociemba]
    Main --> SQLite[(SQLite solve history)]
    Main -. wake event .-> Worker[remote-sync worker]
    Worker --> SQLite
    Worker --> HTTP[Authenticated PHP API]
    HTTP --> MySQL[(MySQL)]
    MySQL --> Dashboard[Web dashboard]
    HTTP -. failure .-> Pending[Row remains synced = 0]
    Pending --> SQLite
```

## Synchronisation lifecycle

```mermaid
sequenceDiagram
    participant M as Main thread
    participant D as SQLite
    participant W as remote-sync thread
    participant L as LAMP API

    M->>W: start()
    W->>D: read earlier pending rows
    par responsive scan and guidance
        M->>M: scan, validate, solve, guide
    and background retry
        W->>L: upload allowlisted summary
        alt accepted
            W->>D: mark synced
        else offline, rejected, or timed out
            W-->>D: leave row pending
        end
    end
    M->>D: commit terminal result
    M-->>W: wake()
    M->>W: stop(flush=true, timeout=4 s)
    W->>D: final pending pass
```

## Concurrency rules

- SQLite is the durable queue; solve payloads are never held only in thread memory.
- `threading.Event` provides wake-up and shutdown signalling.
- A lock prevents two retry passes from running at the same time.
- Starting an already-running worker is idempotent and does not create another thread.
- Upload errors are contained by the worker and cannot abort the scanner.
- Shutdown waits for no more than four seconds. If work is unfinished, the local row
  remains pending for a future run.
- Camera threading is intentionally excluded because OpenCV GUI operations are most
  reliable on the main thread and the measured risk is network I/O, not frame capture.
