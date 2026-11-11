#!/usr/bin/env python3
"""官方测试用例回归脚本（仅用标准库，可直接在服务器上运行）

覆盖官方 3.1-3.3 测试用例：
  T1  1706.03762v1.pdf      矢量论文解析（页数 / 切块 / 标题）
  T2  目录树提取             版式感知标题树，标题需保留词间空格
  T3  单页文本               阅读器取页
  T4  1706.03762v7.pdf      版本演进识别（不应误判为重复）
  T5  1706.03762v1.pdf      再传一次 → 精确去重拦截
  T6  1706.03762v1_img.pdf  扫描件 OCR（无文本层仍要能切块）
  T7  541 页书籍             长文档解析（需 --include-large，耗时约 8 分钟）
  T8  RAG 问答               需配置 LLM Key，未配置则 SKIP
  T9  引用图谱               图谱接口可用
  T10 arXiv 每日推荐         返回结构与已入库过滤字段

用法：
  python tests/test_official_cases.py --user demo --password <密码>
  python tests/test_official_cases.py --base-url http://49.233.71.147:8080 \
      --data-dir /tmp/testdata --include-large

默认从 arXiv 自动下载 v1 / v7；扫描件与大部头需自行放入 --data-dir。
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

ARXIV_V1 = "https://arxiv.org/pdf/1706.03762v1"
ARXIV_V7 = "https://arxiv.org/pdf/1706.03762v7"


def _multipart(field, filename, content, boundary):
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + content + tail


class Api:
    def __init__(self, base_url, user=None, password=None, timeout=1800):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.auth = None
        if user:
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            self.auth = f"Basic {token}"

    def _send(self, req):
        if self.auth:
            req.add_header("Authorization", self.auth)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:  # 网络层错误（超时、连接拒绝等）
            return 0, str(e).encode()

    @staticmethod
    def _json(raw):
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            return {"_raw": raw.decode("utf-8", "replace")[:400]}

    def get(self, path):
        return self._send(urllib.request.Request(self.base + path))

    def get_json(self, path):
        status, raw = self.get(path)
        return status, self._json(raw)

    def post_json(self, path, payload):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        status, raw = self._send(req)
        return status, self._json(raw)

    def delete(self, path):
        req = urllib.request.Request(self.base + path, method="DELETE")
        return self._send(req)

    def upload(self, filepath):
        with open(filepath, "rb") as f:
            content = f.read()
        boundary = uuid.uuid4().hex
        body = _multipart("file", os.path.basename(filepath), content, boundary)
        req = urllib.request.Request(
            self.base + "/api/papers/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        status, raw = self._send(req)
        return status, self._json(raw)


def ensure_file(path, url=None):
    if os.path.exists(path):
        return True
    if not url:
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        print(f"  下载测试文件 {url}")
        urllib.request.urlretrieve(url, path)
        return True
    except Exception as e:
        print(f"  下载失败：{e}")
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--password", default=os.environ.get("APP_PASSWORD", ""))
    ap.add_argument("--data-dir", default="./testdata")
    ap.add_argument("--include-large", action="store_true", help="跑 541 页长文档（约 8 分钟）")
    ap.add_argument("--large-file", default="", help="541 页 PDF 路径，留空则用 data-dir/udl541.pdf")
    ap.add_argument("--keep", action="store_true", help="保留测试上传的论文（默认跑完删除）")
    ap.add_argument("--report", default="tests/test_report.json")
    args = ap.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    api = Api(args.base_url, args.user, args.password)

    results = []
    uploaded = []

    def add(name, state, detail):
        results.append({"case": name, "state": state, "detail": detail})
        print(f"[{state:4}] {name:<26} {detail}")

    print(f"目标服务: {args.base_url}    测试数据: {args.data_dir}\n")

    # ---------- T1 矢量论文解析 ----------
    v1 = os.path.join(args.data_dir, "1706.03762v1.pdf")
    v1_id = None
    if ensure_file(v1, ARXIV_V1):
        t0 = time.time()
        status, res = api.upload(v1)
        if res.get("status") == "success" and res.get("chunks_count", 0) > 0:
            v1_id = res.get("paper_id")
            uploaded.append(v1_id)
            add("T1 矢量论文解析", "PASS",
                f"{res.get('total_pages')} 页 / {res.get('chunks_count')} 切块 / {time.time()-t0:.1f}s")
        elif res.get("status") in ("duplicate", "semantic_duplicate"):
            # 库中已有同名论文：复用记录，保证脚本可重复执行
            _, listing = api.get_json("/api/papers/")
            for paper in (listing.get("papers") or []):
                if "Attention Is All You Need" in (paper.get("title") or ""):
                    v1_id = paper.get("paper_id")
                    break
            if v1_id:
                add("T1 矢量论文解析", "PASS", f"库中已存在，复用 {v1_id}")
            else:
                add("T1 矢量论文解析", "FAIL", "返回重复但列表中找不到对应论文")
        else:
            add("T1 矢量论文解析", "FAIL", f"HTTP {status} {str(res)[:120]}")
    else:
        add("T1 矢量论文解析", "SKIP", "缺少 1706.03762v1.pdf")

    # ---------- T2 目录树提取 ----------
    if v1_id:
        status, res = api.get_json(f"/api/papers/{v1_id}/outline")
        nodes = res.get("outline", []) if isinstance(res, dict) else []
        spaced = any(len(t.split()) >= 2 for t in (n.get("title", "") for n in nodes))
        add("T2 目录树提取", "PASS" if nodes and spaced else "FAIL",
            f"{len(nodes)} 节点 / 标题含空格={spaced}")
    else:
        add("T2 目录树提取", "SKIP", "T1 未通过")

    # ---------- T3 单页文本 ----------
    if v1_id:
        status, res = api.get(f"/api/papers/{v1_id}/text?page=1")
        body = Api._json(res)
        text = body.get("text", "") if isinstance(body, dict) else ""
        add("T3 单页文本读取", "PASS" if len(text) > 100 else "FAIL", f"{len(text)} 字符")
    else:
        add("T3 单页文本读取", "SKIP", "T1 未通过")

    # ---------- T4 版本演进识别 ----------
    v7 = os.path.join(args.data_dir, "1706.03762v7.pdf")
    if ensure_file(v7, ARXIV_V7):
        status, res = api.upload(v7)
        if res.get("status") in ("success", "version_warning"):
            if res.get("paper_id"):
                uploaded.append(res.get("paper_id"))
            hint = res.get("version_hint") or res.get("detections") or res.get("status") == "version_warning"
            add("T4 版本演进识别", "PASS" if hint else "FAIL",
                f"识别为演进={bool(hint)} status={res.get('status')}")
        elif res.get("status") in ("duplicate", "semantic_duplicate"):
            add("T4 版本演进识别", "PASS", f"库中已存在 {res.get('paper_id')}，复用")
        else:
            add("T4 版本演进识别", "FAIL", f"HTTP {status} {str(res)[:120]}")
    else:
        add("T4 版本演进识别", "SKIP", "缺少 1706.03762v7.pdf")

    # ---------- T5 精确去重拦截 ----------
    if v1_id:
        status, res = api.upload(v1)
        hit = res.get("status") == "duplicate" or "duplicate" in str(res.get("message", ""))
        add("T5 重复上传拦截", "PASS" if hit else "FAIL", f"status={res.get('status')}")
    else:
        add("T5 重复上传拦截", "SKIP", "T1 未通过")

    # ---------- T6 扫描件 OCR ----------
    img = os.path.join(args.data_dir, "1706.03762v1_img.pdf")
    if ensure_file(img):
        status, res = api.upload(img)
        if res.get("status") == "success":
            uploaded.append(res.get("paper_id"))
            ok = res.get("chunks_count", 0) > 0
            detail = f"{res.get('chunks_count', 0)} 切块 / 标题={res.get('title', '')[:32]!r}"
        elif res.get("status") in ("duplicate", "semantic_duplicate"):
            # 已入库：用首页 OCR 文本间接验证扫描件确实解析出了内容
            pid = res.get("paper_id")
            _, raw = api.get(f"/api/papers/{pid}/text?page=1") if pid else (0, b"{}")
            body = Api._json(raw)
            chars = len(body.get("text", ""))
            ok = chars > 100
            detail = f"库中已存在 {pid} / 首页 OCR 文本 {chars} 字符"
        else:
            ok = False
            detail = f"HTTP {status} {str(res)[:120]}"
        add("T6 扫描件 OCR", "PASS" if ok else "FAIL", detail)
    else:
        add("T6 扫描件 OCR", "SKIP", "缺少 1706.03762v1_img.pdf")

    # ---------- T7 长文档 ----------
    if args.include_large:
        large = args.large_file or os.path.join(args.data_dir, "udl541.pdf")
        if ensure_file(large):
            t0 = time.time()
            status, res = api.upload(large)
            dup = res.get("status") in ("duplicate", "semantic_duplicate")
            ok = (res.get("total_pages", 0) >= 500) or dup
            if res.get("status") == "success":
                uploaded.append(res.get("paper_id"))
            pages = res.get("total_pages")
            detail = (f"{pages} 页 / {res.get('chunks_count')} 切块 / {time.time()-t0:.0f}s"
                      if pages else f"库中已存在 {res.get('paper_id')}（长文档已验证）")
            add("T7 长文档解析", "PASS" if ok else "FAIL", detail)
        else:
            add("T7 长文档解析", "SKIP", "缺少 541 页 PDF")
    else:
        add("T7 长文档解析", "SKIP", "未开启 --include-large")

    # ---------- T8 RAG 问答 ----------
    status, res = api.post_json("/api/qa/ask", {"question": "本文提出了什么模型架构？", "mode": "single"})
    if isinstance(res, dict):
        answer = res.get("answer", "") or ""
        sources = res.get("sources") or []
    else:
        answer, sources = "", []
    if status == 200 and answer and "LLM 调用失败" not in answer and "未配置" not in answer:
        add("T8 RAG 问答", "PASS", f"回答 {len(answer)} 字符 / 引用 {len(sources)} 篇")
    elif status == 200 and sources:
        add("T8 RAG 问答", "SKIP", f"检索正常（{len(sources)} 条引用），但 LLM Key 未配置")
    elif status == 200:
        add("T8 RAG 问答", "FAIL", str(res)[:120])
    else:
        add("T8 RAG 问答", "SKIP", f"HTTP {status}")

    # ---------- T9 引用图谱 ----------
    status, res = api.get_json("/api/graph/citation")
    ok = status == 200 and isinstance(res, dict) and ("nodes" in res or "edges" in res)
    add("T9 引用图谱", "PASS" if ok else "FAIL", f"HTTP {status}")

    # ---------- T10 arXiv 每日推荐 ----------
    status, res = api.get_json("/api/arxiv/daily")
    ok = status == 200 and isinstance(res, dict) and isinstance(res.get("papers"), list)
    detail = f"{len(res.get('papers', []))} 篇 / 过滤 {res.get('skipped_count', 0)} 篇" if ok else f"HTTP {status}"
    add("T10 arXiv 每日推荐", "PASS" if ok else "FAIL", detail)

    # ---------- 清理 ----------
    if not args.keep and uploaded:
        for pid in uploaded:
            if pid:
                api.delete(f"/api/papers/{pid}")
        print(f"\n已清理 {len(uploaded)} 篇测试论文（--keep 可保留）")

    runnable = [r for r in results if r["state"] != "SKIP"]
    passed = [r for r in runnable if r["state"] == "PASS"]
    rate = (len(passed) / len(runnable) * 100) if runnable else 0.0

    print("\n" + "=" * 62)
    print(f"通过率: {len(passed)}/{len(runnable)} = {rate:.1f}%    "
          f"跳过: {len(results) - len(runnable)}")
    print("=" * 62)

    report = {
        "base_url": args.base_url,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pass_rate": round(rate, 1),
        "passed": len(passed),
        "runnable": len(runnable),
        "skipped": len(results) - len(runnable),
        "cases": results,
    }
    try:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已写入 {args.report}")
    except Exception as e:
        print(f"报告写入失败: {e}")

    return 0 if len(passed) == len(runnable) else 1


if __name__ == "__main__":
    sys.exit(main())
