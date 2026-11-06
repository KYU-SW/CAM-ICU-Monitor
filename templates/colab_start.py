"""Colab 셀에서 `%run /content/cam_icu_rass_v10/colab_start.py`로 실행."""
import os, re, subprocess, sys, time, threading
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
PORT = 8000

# ── Google Drive 연동 (DB 영구 보존) ──────────────────
try:
    from google.colab import drive
    drive.mount('/content/drive', force_remount=False)
    DB_DIR = Path("/content/drive/MyDrive/KY_CAM_ICU_v10")
    DB_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["CAM_ICU_DB_PATH"] = str(DB_DIR / "cam_icu.db")
    print(f"✅ Google Drive 연동 → {os.environ['CAM_ICU_DB_PATH']}")
except Exception as e:
    print(f"⚠️  Drive 연동 실패 ({e}) → 로컬 임시 저장으로 진행")

# 프로젝트 디렉터리를 임포트 경로 최상위에 추가
sys.path.insert(0, str(PROJECT))
os.chdir(str(PROJECT))

# 패키지 설치
print("📦 패키지 설치 중...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "Flask>=3.0.0", "Werkzeug>=3.0.0", "requests>=2.28.0"],
    check=True,
)
print("✅ 설치 완료")

# 앱 로드 — 실패 시 traceback 출력
print("🔍 앱 초기화 중...")
try:
    from app import app as flask_app
    print("✅ 앱 초기화 성공")
except Exception:
    import traceback
    print("❌ 앱 초기화 실패 — traceback:")
    traceback.print_exc()
    raise

# Flask 내장 서버(threaded)를 백그라운드 스레드로 실행
# → 오류 발생 시 traceback이 이 셀에 바로 출력됨
def _run():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False,
                  use_reloader=False, threaded=True)

threading.Thread(target=_run, daemon=True).start()

# 서버 준비 대기
import requests as _req
print("🚀 서버 시작 중...")
for _ in range(30):
    try:
        if _req.get(f"http://127.0.0.1:{PORT}/login", timeout=2).status_code == 200:
            break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("서버 시작 실패 — 위 traceback을 확인하세요.")

print("✅ 서버 준비 완료")

# cloudflared 공개 링크 생성
binary = Path("/usr/local/bin/cloudflared")
if not binary.exists():
    print("🌐 cloudflared 다운로드 중...")
    subprocess.run(
        ["wget", "-q",
         "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
         "-O", str(binary)],
        check=True,
    )
    binary.chmod(0o755)

tunnel = subprocess.Popen(
    [str(binary), "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
for line in tunnel.stdout:
    m = re.search(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", line)
    if m:
        time.sleep(3)
        print("\n✅ 접속 링크:", m.group(0))
        print("   계정: nurse01 / 1234  또는  nurse02 / 1234")
        break
else:
    raise RuntimeError("공개 링크 생성 실패")
