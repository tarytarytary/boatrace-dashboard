import csv, json, subprocess, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

root = Path(__file__).parent
out = root / "site"
out.mkdir(exist_ok=True)

day = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")

cmd = [
    sys.executable,
    str(root / "boatrace_batch.py"),
    "--date", day,
    "--out", str(root / "results"),
    "--delay", "0.25"
]

try:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=root)
    log = (p.stdout + "\n" + p.stderr)[-8000:]
    status = "実行完了" if p.returncode == 0 else "取得・処理エラー（未判定）"
except Exception as e:
    log = str(e)
    status = "実行エラー（未判定）"

rows = []
path = root / "results" / "race_status.csv"
if path.exists():
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

summary = {
    "date": day,
    "status": status,
    "races": len(rows),
    "scored": sum(x.get("採点") == "完了" for x in rows),
    "passed": sum(x.get("一次通過") == "通過" for x in rows),
    "pending": sum(x.get("採点") != "完了" for x in rows),
    "updated_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="minutes"),
    "log": log[-1200:]
}
(out / "data.json").write_text(json.dumps({"summary": summary, "races": rows}, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
# Copy dashboard HTML to GitHub Pages
source = root / "index.html"
if source.exists():
    (out / "index.html").write_bytes(source.read_bytes())
