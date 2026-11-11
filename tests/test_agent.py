#!/usr/bin/env python3
"""Agent 多轮工具调用回归脚本（仅用标准库）

覆盖评分点 9%（Task Planning / Function Calling / Multi-Agent 路由）：
  A1 工具清单           GET  /api/agent/tools
  A2 健康检查           GET  /api/agent/health
  A3 单工具规划         RAG 类问题 → 应命中 rag_qa
  A4 多工具串联         引用网络 + 未来方向 → 应串联 ≥2 个工具
  A5 多轮会话记忆       同一 session_id 连续两问，均正常返回
  A6 外部检索工具       arXiv 类问题 → 应命中 arxiv_search

用法：
  python tests/test_agent.py --user demo --password <密码>
  也可用环境变量 APP_PASSWORD 提供密码
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request


class Api:
    def __init__(self, base_url, user, password, timeout=300):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = f"Basic {token}"

    def _send(self, req):
        req.add_header("Authorization", self.auth)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, {"_raw": e.read().decode("utf-8", "replace")[:300]}
        except Exception as e:
            return 0, {"_raw": str(e)[:300]}

    def get(self, path):
        return self._send(urllib.request.Request(self.base + path))

    def chat(self, message, session_id="default"):
        req = urllib.request.Request(
            self.base + "/api/agent/chat",
            data=json.dumps({"message": message, "session_id": session_id}).encode(),
            headers={"Content-Type": "application/json"},
        )
        return self._send(req)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--password", default=os.environ.get("APP_PASSWORD", ""))
    ap.add_argument("--report", default="tests/agent_report.json")
    args = ap.parse_args()

    api = Api(args.base_url, args.user, args.password)
    results = []

    def add(name, state, detail):
        results.append({"case": name, "state": state, "detail": detail})
        print(f"[{state:4}] {name:<22} {detail}")

    # A1 工具清单
    status, res = api.get("/api/agent/tools")
    tools = res.get("tools") or res.get("all_tools") or []
    add("A1 工具清单", "PASS" if status == 200 and len(tools) else "FAIL",
        f"{len(tools)} 个工具" if status == 200 else f"HTTP {status}")

    # A2 健康检查
    status, res = api.get("/api/agent/health")
    ok = status == 200 and res.get("status") == "ok"
    add("A2 健康检查", "PASS" if ok else "FAIL", str(res)[:100])

    # A3 单工具规划
    t0 = time.time()
    status, res = api.chat("总结库中 Attention 论文的核心贡献", session_id="a3")
    used = res.get("all_tools") or []
    ok = status == 200 and "rag_qa" in used and res.get("answer")
    add("A3 单工具规划", "PASS" if ok else "FAIL",
        f"工具={used} / {res.get('iterations')} 轮 / {time.time()-t0:.0f}s")

    # A4 多工具串联
    t0 = time.time()
    status, res = api.chat(
        "分析库中 Attention 论文在引用网络中的位置，并给出该领域未来的研究方向",
        session_id="a4",
    )
    used = res.get("all_tools") or []
    ok = status == 200 and len(used) >= 2 and res.get("answer")
    add("A4 多工具串联", "PASS" if ok else "FAIL",
        f"工具={used} / {res.get('iterations')} 轮 / {time.time()-t0:.0f}s")

    # A5 多轮会话记忆
    status1, res1 = api.chat("Transformer 里多头注意力有什么作用？", session_id="a5")
    status2, res2 = api.chat("那它和单头注意力相比主要优势是什么？", session_id="a5")
    ok = status1 == 200 and status2 == 200 and res1.get("answer") and res2.get("answer")
    add("A5 多轮会话记忆", "PASS" if ok else "FAIL",
        f"第一轮 {len(res1.get('answer', ''))} 字 / 第二轮 {len(res2.get('answer', ''))} 字")

    # A6 外部检索工具
    t0 = time.time()
    status, res = api.chat("帮我检索最近关于长上下文 Transformer 的论文", session_id="a6")
    used = res.get("all_tools") or []
    ok = status == 200 and "arxiv_search" in used and res.get("answer")
    add("A6 外部检索工具", "PASS" if ok else "FAIL",
        f"工具={used} / {res.get('iterations')} 轮 / {time.time()-t0:.0f}s")

    total = len(results)
    passed = len([r for r in results if r["state"] == "PASS"])
    print("\n" + "=" * 60)
    print(f"Agent 通过率: {passed}/{total} = {passed/total*100:.1f}%")
    print("=" * 60)

    report = {"base_url": args.base_url, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
              "passed": passed, "total": total, "cases": results}
    try:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已写入 {args.report}")
    except Exception as e:
        print(f"报告写入失败: {e}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
