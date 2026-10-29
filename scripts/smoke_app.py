"""Real loopback Streamlit startup plus execution of all eight existing pages.

Does not call an external LLM or export customer records. AppTest executes widget
flows but is not a browser screenshot/visual RTL acceptance test.
"""
import json
import argparse
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def smoke():
    result = {"server": {}, "pages": [], "visual_browser_review": "not performed", "llm_api": "not called"}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = ROOT / "outputs" / "streamlit-smoke.log"
    log.parent.mkdir(exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless=true", "--server.address=127.0.0.1", f"--server.port={port}",
            "--browser.gatherUsageStats=false"], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"Streamlit exited {proc.returncode}; see {log}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as response:
                        health = response.read().decode()
                        if response.status == 200 and health == "ok":
                            break
                except OSError:
                    pass
                time.sleep(.25)
            else:
                raise TimeoutError("Streamlit health endpoint timed out")
            with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                result["server"] = {"health": health, "root_http_status": response.status}
            print("PASS real Streamlit server: health=ok, HTTP root=200", flush=True)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    if app.exception:
        raise RuntimeError([e.message for e in app.exception])
    # Options are translated display text; use the existing raw navigation values.
    pages = ["Executive Overview", "Sales Analytics", "Branch Performance", "Inventory Intelligence",
             "Demand Forecasting", "Profitability Analysis", "Customer Intelligence", "AI Business Assistant"]
    for language in ("العربية", "English"):
        app.sidebar.radio[0].set_value(language).run()
        for page in pages:
            app.sidebar.radio[1].set_value(page).run()
            errors = [e.message for e in app.exception]+[e.value for e in app.error]
            result["pages"].append({"language": language, "page": page, "exceptions": errors})
            print(f"{'FAIL' if errors else 'PASS'} page {page}, language {'Arabic' if language != 'English' else 'English'}", flush=True)
    # Exercise existing branch controls with an actual branch, no customer output.
    app.sidebar.radio[1].set_value("Executive Overview").run()
    app.sidebar.selectbox(key='filter_branch_en').select_index(1).run()
    result["branch_filter_exceptions"] = [e.message for e in app.exception]+[e.value for e in app.error]
    app.sidebar.radio[1].set_value("AI Business Assistant").run()
    app.chat_input[0].set_value("Show company sales").run()
    result["offline_chat_exceptions"] = [e.message for e in app.exception]+[e.value for e in app.error]
    result["offline_chat_has_assistant_message"] = any(m["role"] == "assistant" and m.get("reports") for m in app.session_state["dialog"])
    result["passed"] = (not any(p["exceptions"] for p in result["pages"])
                        and not result["branch_filter_exceptions"] and not result["offline_chat_exceptions"]
                        and result["offline_chat_has_assistant_message"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT/'reports'/'phase_0_smoke.json')
    args = parser.parse_args()
    result = smoke()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print("Smoke result:", "PASS" if result["passed"] else "FAIL")
    raise SystemExit(0 if result["passed"] else 1)
