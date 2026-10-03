#!/usr/bin/env python3
"""后羿 HOUYI Web 应用 —— Flask 后端。

提供：
  GET  /              前端页面
  POST /api/run       启动 pipeline（后台线程）
  GET  /api/stream    实时进度（SSE 推送）
  GET  /api/results   获取结果（Top binder + 靶点）
  GET  /api/status    当前任务状态

用法：
  python webapp.py              # 默认 http://127.0.0.1:5000
  python webapp.py --port 8080  # 指定端口
"""
import os
import sys
import json
import threading
import queue
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from flask import Flask, request, jsonify, Response, send_from_directory
from hoyi.config import Config
from hoyi import run_pipeline
from hoyi.utils import on_event, load_json

app = Flask(__name__)
cfg = Config()

# ============ 全局任务状态 ============
_task_lock = threading.Lock()
_task = {
    "running": False,
    "events": [],       # 已完成的事件列表
    "result": None,
    "error": None,
    "started_at": None,
}


def _reset_task():
    """重置任务状态。调用者需持有 _task_lock。"""
    global _task
    _task = {"running": False, "events": [], "result": None,
             "error": None, "started_at": None}


def _run_pipeline_thread(organism, targets, scorer, mic_map, dry_run, top_n):
    """后台线程跑 pipeline。事件通过全局监听器（模块加载时已注册）推送到 _task["events"]。"""
    global _task
    try:
        result = run_pipeline(
            cfg, organism, targets=targets, scorer=scorer,
            mic_map=mic_map, dry_run=dry_run, top_n=top_n)
        with _task_lock:
            _task["result"] = result
            _task["running"] = False
    except Exception as e:
        with _task_lock:
            _task["error"] = str(e)
            _task["running"] = False


# 全局事件监听器：模块加载时注册一次，把事件追加到当前任务的事件列表
# （放在 _reset_task 后、任何任务启动前，避免重复注册）
def _global_event_listener(event):
    with _task_lock:
        _task["events"].append(event)


on_event(_global_event_listener)


@app.route("/")
def index():
    return send_from_directory(os.path.join(HERE, "webapp_static"), "index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    global _task
    body = request.get_json(force=True, silent=True) or {}
    organism = body.get("organism", "Staphylococcus aureus")
    targets = body.get("targets") or None
    scorer = body.get("scorer", "length")
    mic_map = body.get("mic_map") or None
    dry_run = body.get("dry_run", False)
    top_n = body.get("top_n", 3)

    with _task_lock:
        if _task["running"]:
            return jsonify({"ok": False, "error": "已有任务在运行中"}), 409
        _reset_task()
        _task["running"] = True
        _task["started_at"] = json.dumps({"organism": organism})

    # 按细菌名切换数据源（与 run_pipeline 内同步，确保 /api/results 也读到正确数据）
    cfg.set_organism(organism)

    t = threading.Thread(target=_run_pipeline_thread,
                         args=(organism, targets, scorer, mic_map, dry_run, top_n),
                         daemon=True)
    t.start()
    return jsonify({"ok": True, "message": f"任务已启动：{organism}"})


@app.route("/api/stream")
def api_stream():
    """SSE 实时进度推送。"""
    def gen():
        last = 0
        # 先推送已有事件
        while True:
            with _task_lock:
                events = list(_task["events"])
                running = _task["running"]
                error = _task["error"]
            if len(events) > last:
                for e in events[last:]:
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                last = len(events)
            if not running:
                # 任务结束，推送终态
                final = {"ring": -2, "status": "error" if error else "finish_all",
                         "message": error or "完成", "error": error}
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                break
            import time
            time.sleep(0.3)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/status")
def api_status():
    with _task_lock:
        return jsonify({"running": _task["running"],
                        "events": _task["events"],
                        "error": _task["error"]})


@app.route("/api/results")
def api_results():
    """返回 Top binder + 载荷 + 靶点知识库（前端展示用）。"""
    top = load_json(cfg.ring5_json, default=[])
    payloads = load_json(cfg.ring6_json, default=[])
    kb = load_json(cfg.kb_path, default={"targets": {}})
    mic = load_json(os.path.join(cfg.data_dir, "wetlab", "mic_results.json"), default={})
    return jsonify({"top_binders": top, "payloads": payloads,
                    "targets": kb.get("targets", {}), "mic": mic})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="后羿 HOUYI Web 应用")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    print(f"\n  🏹 后羿 HOUYI Web 应用已启动")
    print(f"  浏览器打开: http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
