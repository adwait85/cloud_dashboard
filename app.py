# app.py (lavender UI version) - Cloud dashboard (FastAPI)
import os, time, io, threading, json
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd

# --- Config from environment ---
PROJECT_KEY = os.getenv("PROJECT_KEY", "demo-project-key")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "letmein")

# --- FastAPI & static ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- In-memory project state ---
STORE: Dict[str, Dict[str, Any]] = {}
LOCK = threading.Lock()

def project() -> Dict[str, Any]:
    with LOCK:
        p = STORE.get(PROJECT_KEY)
        if not p:
            p = {"queue": [], "last_results": {}, "last_seen": 0.0}
            STORE[PROJECT_KEY] = p
        return p

def auth_ui(password: str):
    if password != DASHBOARD_PASS:
        raise HTTPException(status_code=403, detail="Bad password")

def auth_agent(key: str):
    if key != PROJECT_KEY:
        raise HTTPException(status_code=403, detail="Bad project key")

# ---- helpers ----
def enqueue(cmd: Dict[str, Any]):
    with LOCK:
        project()["queue"].append(cmd)

def dequeue(timeout_s=25.0) -> Dict[str, Any]:
    end = time.time() + timeout_s
    while time.time() < end:
        with LOCK:
            q = project()["queue"]
            if q:
                return q.pop(0)
        time.sleep(0.3)
    return {"type":"noop"}

def set_result(kind: str, data: Dict[str, Any]):
    with LOCK:
        project()["last_results"][kind] = data

def get_result(kind: str) -> Optional[Dict[str, Any]]:
    with LOCK:
        return project()["last_results"].get(kind)

# ---- UI route ----
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---- User API (website -> cloud) ----
@app.post("/api/setfreq")
def api_setfreq(hz: float = Form(...), pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    enqueue({"type":"setfreq","hz":float(hz)})
    time.sleep(0.8)
    return {"ok": True}

@app.post("/api/single")
def api_single(pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    enqueue({"type":"single"})
    end = time.time() + 10
    while time.time() < end:
        r = get_result("single")
        if r: return r
        time.sleep(0.5)
    return {"type":"single","error":"timeout"}

@app.post("/api/sweep")
def api_sweep(pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    enqueue({"type":"sweep"})
    end = time.time() + 20
    while time.time() < end:
        r = get_result("sweep")
        if r: return r
        time.sleep(0.6)
    return {"type":"sweep","error":"timeout"}

@app.post("/api/analysis")
def api_analysis(pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    enqueue({"type":"analysis"})
    end = time.time() + 15
    while time.time() < end:
        r = get_result("analysis")
        if r: return r
        time.sleep(0.5)
    return {"type":"analysis","error":"timeout"}

@app.post("/api/cal")
def api_cal(r_known: float = Form(...), pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    enqueue({"type":"cal","r_known":float(r_known)})
    end = time.time() + 10
    while time.time() < end:
        r = get_result("cal")
        if r: return r
        time.sleep(0.5)
    return {"type":"cal","error":"timeout"}

@app.post("/api/status")
def api_status(pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    r = get_result("status")
    if not r: r = {"ok": False}
    return r

@app.get("/api/agent_heartbeat")
def api_agent_heartbeat():
    with LOCK:
        last = project()["last_seen"]
    return {"last_seen": last}

@app.post("/api/upload")
async def api_upload(file: UploadFile, pass_: str = Form("pass"), pass__alias: str = Form(None, alias="pass")):
    password = pass__alias if pass__alias is not None else pass_
    auth_ui(password)
    content = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            return RedirectResponse(url="/", status_code=303)
        def pick(df, opts):
            for c in df.columns:
                if c in opts: return c
        col_f   = pick(df, ["f","freq","frequency","Frequency"])
        col_mag = pick(df, ["mag","|Z|","Zmag","Z_mag"])
        col_ph  = pick(df, ["phase","Phase","deg","phi"])
        if not (col_f and col_mag and col_ph):
            num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if len(num) >= 3: col_f, col_mag, col_ph = num[:3]
            else: return RedirectResponse(url="/", status_code=303)
        pts = [{"f":float(row[col_f]), "mag":float(row[col_mag]), "phase":float(row[col_ph]), "valid":True} for _,row in df.iterrows()]
        res = {"type":"upload","points":pts}
        set_result("sweep", res)
        return JSONResponse(res)
    except Exception as e:
        print("upload error", e)
        return RedirectResponse(url="/", status_code=303)

# ---- Agent API ----
@app.post("/agent/hello")
def agent_hello(key: str = Form(...)):
    auth_agent(key)
    with LOCK:
        project()["last_seen"] = time.time()
    return {"ok": True}

@app.post("/agent/next")
def agent_next(key: str = Form(...)):
    auth_agent(key)
    with LOCK:
        project()["last_seen"] = time.time()
    cmd = dequeue(timeout_s=25.0)
    return JSONResponse(cmd)

@app.post("/agent/result")
def agent_result(key: str = Form(...), kind: str = Form(...), payload: str = Form(...)):
    auth_agent(key)
    with LOCK:
        project()["last_seen"] = time.time()
    try:
        data = json.loads(payload)
    except:
        data = {"error":"bad_json"}
    set_result(kind, data)
    if kind == "status":
        set_result("status", data)
    return {"ok": True}
