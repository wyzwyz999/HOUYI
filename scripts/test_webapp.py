"""测试 HOUYI Web 应用的完整流程。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:5000"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode())

def post(path, data):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

print("1. 启动任务...")
try:
    r = post("/api/run", {"organism": "Staphylococcus aureus", "scorer": "length", "top_n": 3})
    print("   响应:", r)
except Exception as e:
    print("   启动失败:", e)
    exit(1)

print("2. 轮询状态直到完成...")
for i in range(60):
    time.sleep(1)
    s = get("/api/status")
    if not s["running"]:
        print("   任务结束")
        break
    if i % 5 == 0:
        print(f"   ...运行中，已有 {len(s['events'])} 个事件")

s = get("/api/status")
print(f"   总事件数: {len(s['events'])}")
print("   事件流:")
for e in s["events"]:
    print(f"     环{e['ring']} [{e['status']}] {e['message']}")

print("3. 获取结果...")
res = get("/api/results")
top = res.get("top_binders", [])
print(f"   Top binder 数: {len(top)}")
if top:
    print(f"   第一条: {top[0]['target']} | {top[0]['binder_id']} | {top[0]['length']}aa")
