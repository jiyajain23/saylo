# Backend diagnostics

These are manual checks only; they are not imported by the gateway or worker.
Run them from the `backend` directory so the existing backend module imports resolve:

```powershell
venv\Scripts\python.exe -m tests.check_live
venv\Scripts\python.exe -m tests.verify_supabase
venv\Scripts\python.exe -m tests.verify_phase3
venv\Scripts\python.exe -m tests.verify_phase3 --storage-smoke
```

The diagnostics avoid printing credentials or user data. The storage smoke test
creates and deletes one synthetic private object.
