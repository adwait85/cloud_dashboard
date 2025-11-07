# agent.py - Local bridge
import os, time, json, math, random
from typing import Dict, Any
import requests

BASE_URL    = os.getenv("CLOUD_URL", "https://YOUR-RENDER-URL.onrender.com")
PROJECT_KEY = os.getenv("PROJECT_KEY", "demo-project-key")

USE_MOCK    = True          # change to False for real serial
SERIAL_PORT = "COM6"
BAUD        = 115200

session = requests.Session()

class BridgeBase:
    def setfreq(self, hz: float) -> Dict[str,Any]: ...
    def single(self) -> Dict[str,Any]: ...
    def sweep(self) -> Dict[str,Any]: ...
    def analysis(self) -> Dict[str,Any]: ...
    def cal(self, r_known: float) -> Dict[str,Any]: ...
    def status(self) -> Dict[str,Any]: ...

class MockBridge(BridgeBase):
    def __init__(self):
        self.freq=250.0; self.mag_cal=1.0; self.phase_cal=0.0; random.seed(1)
    def _n(self,v,rel=0.02,absn=0.0): return v*(1+random.uniform(-rel,rel))+random.uniform(-absn,absn)
    def setfreq(self,hz:float): self.freq=max(10,min(5000,hz)); return {"type":"setfreq","ok":True,"freq":self.freq}
    def single(self):
        mag=self._n(470000,0.03); phase=self._n(0.0,0.0,0.5)
        return {"type":"single","freq":self.freq,"mag":mag,"phase":phase,"valid":True}
    def sweep(self):
        pts=[]; R=470000.0; C=1e-9
        for f in [100,250,500,1000,2000,5000]:
            w=2*math.pi*f; denom=math.sqrt(1+(w*R*C)**2)
            mag=self._n(R/denom,0.03); phase=self._n(-math.degrees(math.atan(w*R*C)),0,1.0)
            pts.append({"f":f,"mag":mag,"phase":phase,"valid":True})
        return {"type":"sweep","points":pts}
    def analysis(self):
        pts=[]; R=470000.0; C=1e-9
        for f in [100,500,1000,5000]:
            w=2*math.pi*f; denom=math.sqrt(1+(w*R*C)**2)
            mag=self._n(R/denom,0.03); phase=self._n(-math.degrees(math.atan(w*R*C)),0,1.0)
            pts.append({"f":f,"mag":mag,"phase":phase,"valid":True})
        return {"type":"analysis","points":pts}
    def cal(self,r_known:float):
        self.mag_cal=1.0; self.phase_cal=0.0
        return {"type":"cal","ok":True,"mag_cal":self.mag_cal,"phase_cal":self.phase_cal}
    def status(self): return {"ok":True,"freq":self.freq,"mag_cal":self.mag_cal,"phase_cal":self.phase_cal}

bridge: BridgeBase = MockBridge()

def post(path, data):
    return session.post(BASE_URL+path, data=data, timeout=30).json()

def main():
    try: post("/agent/hello", {"key":PROJECT_KEY})
    except Exception as e: print("Connect error:", e)
    while True:
        try:
            cmd = post("/agent/next", {"key":PROJECT_KEY})
        except Exception as e:
            print("Poll error:", e); time.sleep(2); continue
        ctype = cmd.get("type")
        if ctype in (None, "noop"):
            time.sleep(0.5); continue
        try:
            if ctype=="setfreq":
                out = bridge.setfreq(float(cmd["hz"]))
                stat= bridge.status()
                post("/agent/result", {"key":PROJECT_KEY,"kind":"status","payload":json.dumps(stat)})
            elif ctype=="single":
                out = bridge.single()
                post("/agent/result", {"key":PROJECT_KEY,"kind":"single","payload":json.dumps(out)})
            elif ctype=="sweep":
                out = bridge.sweep()
                post("/agent/result", {"key":PROJECT_KEY,"kind":"sweep","payload":json.dumps(out)})
            elif ctype=="analysis":
                out = bridge.analysis()
                post("/agent/result", {"key":PROJECT_KEY,"kind":"analysis","payload":json.dumps(out)})
            elif ctype=="cal":
                out = bridge.cal(float(cmd["r_known"]))
                post("/agent/result", {"key":PROJECT_KEY,"kind":"cal","payload":json.dumps(out)})
            else:
                print("Unknown cmd:", cmd)
        except Exception as e:
            print("Exec error:", e)
            try:
                post("/agent/result", {"key":PROJECT_KEY,"kind":ctype or "error","payload":json.dumps({"error":str(e)})})
            except: pass
        time.sleep(0.1)

if __name__=="__main__":
    main()
