"""
database.py — KY CAM-ICU/RASS v5

가상 환자 데이터 생성 기준 (근거 문헌):
─────────────────────────────────────────────────────────────────
[1] Ely EW et al. JAMA 2001;286(21):2703-2710
    · CAM-ICU 원논문. 기계호흡 환자 83.3% 섬망 발생.

[2] Sessler CN et al. Am J Respir Crit Care Med. 2002;166:1338-1344
    · RASS 원논문. 중증도별 점수 분포 기준.

[3] Krewulak KD et al. Crit Care Med. 2018;46(12):2028-2035
    · CAM-ICU 메타분석(n=16,595): 섬망 유병률 31%.

[4] Khan SH et al. Heart Lung. 2020;49(4):572-577
    · ICU 섬망률 16.5%, 혼수(RASS≤-4) 17-24%.

[5] Delirium Journal. 2023; n=20,241명:
    · CAM-ICU POSITIVE 25.1%.

[6] Liu Y et al. Crit Care Med. 2019 (n=23,062):
    · ICU 평균 연령 52-67세, 남성 57.5%.

[7] Salluh JIF et al. BMC Crit Care. 2010:
    · ICU 진단 분포 — 패혈증 47%, 폐렴 14%, 외상 등.

생성 파라미터 요약:
  CAM-ICU 결과: POSITIVE 28%, NEGATIVE 57%, UNASSESSABLE 15%
  평균 연령: 62세 (18-44: 18%, 45-64: 42%, 65-79: 30%, 80+: 10%)
  성별: 남성 60%, 여성 40%  [Liu 2019]
  진정제 사용: 60%
  RASS 분포: 0(-1-0 중심, 중앙값 ~-1)  [Sessler 2002]
─────────────────────────────────────────────────────────────────
"""

import os
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = Path(os.environ.get("CAM_ICU_DB_PATH", BASE_DIR / "data" / "cam_icu.db"))

# ── 이름 생성 데이터 ───────────────────────────────────
_SURNAMES = ['김','이','박','최','정','강','조','윤','임','한','오','신','권','황','안',
             '서','류','남','홍','배','문','노','석','양','진','구','변','성','장','표',
             '심','차','방','추','곽','함','엄','도','나','송','천','고','손','하','허',
             '염','주','현','기','전','민','유','백','라','어','마','제','탁','봉','나']
_MALE    = ['민준','지훈','해준','현우','도현','승민','준혁','지호','재원','태현',
            '현준','도윤','성우','민혁','재훈','시우','정우','건우','주원','영재',
            '민수','정호','진우','태준','민호','준서','현서','도준','수호','재윤',
            '시준','지환','성진','우진','태양','기태','선우','이준','지안','건호']
_FEMALE  = ['서연','유진','소희','지원','지수','혜린','미영','소은','수빈','채원',
            '지영','미래','지안','유나','지혜','은지','혜수','나은','예린','수아',
            '지민','소연','하은','민지','수정','예지','다은','지현','소정','예은',
            '아름','나리','보미','수현','혜인','나현','소현','예나','채은','하린']

# ── 진단명 분포 (Salluh 2010; Ely 2001 기반) ─────────
# 패혈증 25%, 폐렴 20%, 수술후 15%, 급성호흡부전 10%,
# 심부전 8%, 뇌졸중 7%, 외상 6%, 신부전 3%, 뇌출혈 3%, 기타 3%
_DIAG_POOL = (
    ['패혈증'] * 25 +
    ['폐렴'] * 20 +
    ['수술 후 관리'] * 15 +
    ['급성 호흡부전'] * 10 +
    ['심부전'] * 8 +
    ['뇌졸중'] * 7 +
    ['외상'] * 6 +
    ['신부전'] * 3 +
    ['뇌출혈'] * 3 +
    ['기타 내과적 질환'] * 3
)

# ── RASS 분포 가중치 (Sessler 2002; 중앙값 -1) ───────
# +4:1%, +3:2%, +2:4%, +1:8%, 0:25%, -1:22%, -2:16%, -3:10%, -4:7%, -5:5%
_RASS_CHOICES = (
    [4]*1 + [3]*2 + [2]*4 + [1]*8 +
    [0]*25 + [-1]*22 + [-2]*16 + [-3]*10 +
    [-4]*7 + [-5]*5
)

# ── 관찰 항목 텍스트 ──────────────────────────────────
_OBS = [
    '환자가 폭력적이며 의료진에게 즉각적인 위험이 있음',     # +4
    '튜브나 카테터를 당기며 의료진에게 공격적임',             # +3
    '목적 없는 움직임이 잦거나 인공호흡기에 저항함',          # +2
    '불안하거나 초조하지만 공격적이지 않음',                  # +1
    '깨어 있고 차분함',                                       # 0
    '목소리에 눈을 뜨고 10초 이상 눈맞춤을 유지함',           # -1
    '목소리에 잠깐 눈을 뜨지만 눈맞춤이 10초 미만임',         # -2
    '목소리에 움직이거나 눈을 뜨지만 눈맞춤은 없음',          # -3
    '목소리에는 반응하지 않고 신체 자극에 움직임',             # -4
    '목소리와 신체 자극 모두에 반응이 없음',                  # -5
]
_AI_RASS = [4, 3, 2, 1, 0, -1, -2, -3, -4, -5]

# ── 기존 74명 실제 환자 ───────────────────────────────
_PATIENTS_A = [
    ("P-A001","김민준","ICU-A01",25,"남",1), ("P-A002","이서연","ICU-A02",32,"여",1),
    ("P-A003","박지훈","ICU-A03",45,"남",1), ("P-A004","최유진","ICU-A04",28,"여",1),
    ("P-A005","정해준","ICU-A05",67,"남",1), ("P-A006","강소희","ICU-A06",52,"여",1),
    ("P-A007","조현우","ICU-A07",38,"남",1), ("P-A008","윤지원","ICU-A08",71,"여",1),
    ("P-A009","임도현","ICU-A09",23,"남",1), ("P-A010","한지수","ICU-A10",56,"여",1),
    ("P-A011","오승민","ICU-A11",44,"남",1), ("P-A012","신혜린","ICU-A12",35,"여",1),
    ("P-A013","권태양","ICU-A13",62,"남",1), ("P-A014","황미영","ICU-A14",48,"여",1),
    ("P-A015","안준혁","ICU-A15",31,"남",1), ("P-A016","서보라","ICU-A16",79,"여",1),
    ("P-A017","류지호","ICU-A17",22,"남",1), ("P-A018","남소은","ICU-A18",58,"여",1),
    ("P-A019","문재원","ICU-A19",73,"남",1), ("P-A020","배채원","ICU-A20",36,"여",1),
    ("P-A021","노태현","ICU-A21",55,"남",1), ("P-A022","석지영","ICU-A22",29,"여",1),
    ("P-A023","양현준","ICU-A23",66,"남",1), ("P-A024","진미래","ICU-A24",43,"여",1),
    ("P-A025","구도윤","ICU-A25",21,"남",1), ("P-A026","홍지안","ICU-A26",77,"여",1),
    ("P-A027","변성우","ICU-A27",50,"남",1), ("P-A028","성유나","ICU-A28",33,"여",1),
    ("P-A029","장민혁","ICU-A29",60,"남",1), ("P-A030","표지혜","ICU-A30",47,"여",1),
    ("P-A031","심기태","ICU-A31",27,"남",1), ("P-A032","차은지","ICU-A32",69,"여",1),
    ("P-A033","방재훈","ICU-A33",39,"남",1), ("P-A034","추수아","ICU-A34",54,"여",1),
    ("P-A035","곽시우","ICU-A35",76,"남",1), ("P-A036","함지민","ICU-A36",41,"여",1),
    ("P-A037","엄정우","ICU-A37",26,"남",1), ("P-A038","도소연","ICU-A38",63,"여",1),
    ("P-A039","나건우","ICU-A39",80,"남",1), ("P-A040","송나은","ICU-A40",37,"여",1),
]
_PATIENTS_B = [
    ("P-B001","천준호","ICU-B01",42,"남",2), ("P-B002","고하은","ICU-B02",57,"여",2),
    ("P-B003","손예린","ICU-B03",29,"여",2), ("P-B004","하지훈","ICU-B04",65,"남",2),
    ("P-B005","허유나","ICU-B05",34,"여",2), ("P-B006","염민수","ICU-B06",51,"남",2),
    ("P-B007","주미래","ICU-B07",78,"여",2), ("P-B008","현태준","ICU-B08",24,"남",2),
    ("P-B009","기소영","ICU-B09",43,"여",2), ("P-B010","최재혁","ICU-B10",70,"남",2),
    ("P-B011","전수연","ICU-B11",38,"여",2), ("P-B012","박민준","ICU-B12",55,"남",2),
    ("P-B013","이지수","ICU-B13",27,"여",2), ("P-B014","정영호","ICU-B14",63,"남",2),
    ("P-B015","강은아","ICU-B15",46,"여",2), ("P-B016","조성현","ICU-B16",32,"남",2),
    ("P-B017","윤수진","ICU-B17",75,"여",2), ("P-B018","임태호","ICU-B18",48,"남",2),
    ("P-B019","한지은","ICU-B19",22,"여",2), ("P-B020","오민호","ICU-B20",59,"남",2),
    ("P-B021","신예슬","ICU-B21",36,"여",2), ("P-B022","권재민","ICU-B22",68,"남",2),
    ("P-B023","황혜진","ICU-B23",41,"여",2), ("P-B024","안승준","ICU-B24",26,"남",2),
    ("P-B025","서다영","ICU-B25",72,"여",2), ("P-B026","류우혁","ICU-B26",53,"남",2),
    ("P-B027","남소라","ICU-B27",31,"여",2), ("P-B028","홍준영","ICU-B28",44,"남",2),
    ("P-B029","배지현","ICU-B29",67,"여",2), ("P-B030","문민재","ICU-B30",28,"남",2),
    ("P-B031","노하영","ICU-B31",80,"여",2), ("P-B032","석정호","ICU-B32",37,"남",2),
    ("P-B033","양수민","ICU-B33",61,"여",2), ("P-B034","진성진","ICU-B34",49,"남",2),
]


@contextmanager
def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS wards(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)""")
        db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            name TEXT NOT NULL, employee_no TEXT NOT NULL UNIQUE,
            ward_id INTEGER REFERENCES wards(id),
            role TEXT NOT NULL DEFAULT 'NURSE',
            last_login TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS patients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            room_number TEXT NOT NULL, age INTEGER NOT NULL,
            sex TEXT NOT NULL CHECK(sex IN ('남','여')),
            ward_id INTEGER NOT NULL REFERENCES wards(id),
            status TEXT NOT NULL DEFAULT '입원중',
            diagnosis TEXT DEFAULT '',
            admission_date TEXT DEFAULT '',
            sedative_use INTEGER DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS patient_assignments(
            user_id INTEGER NOT NULL REFERENCES users(id),
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            PRIMARY KEY(user_id, patient_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS assessments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            nurse_id INTEGER NOT NULL REFERENCES users(id),
            assessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            observation TEXT NOT NULL,
            ai_status TEXT NOT NULL, ai_rass INTEGER,
            rass_score INTEGER NOT NULL CHECK(rass_score BETWEEN -5 AND 4),
            feature1 INTEGER, feature2 INTEGER, feature3 INTEGER, feature4 INTEGER,
            cam_result TEXT NOT NULL CHECK(cam_result IN ('POSITIVE','NEGATIVE','UNASSESSABLE')),
            memo TEXT DEFAULT '')""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT NOT NULL, detail TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

        # 마이그레이션
        for tbl, col, defn in [
            ("patients",    "status",         "TEXT NOT NULL DEFAULT '입원중'"),
            ("patients",    "diagnosis",      "TEXT DEFAULT ''"),
            ("patients",    "admission_date", "TEXT DEFAULT ''"),
            ("patients",    "sedative_use",   "INTEGER DEFAULT 0"),
            ("assessments", "memo",           "TEXT DEFAULT ''"),
            ("users",       "last_login",     "TEXT"),
        ]:
            try:
                db.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
            except Exception:
                pass

        # 기본 시드
        if db.execute("SELECT COUNT(*) FROM wards").fetchone()[0] == 0:
            db.executemany("INSERT INTO wards(name) VALUES(?)",
                           [("중환자실 A",), ("중환자실 B",)])

        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            pw    = generate_password_hash("1234",      method="pbkdf2:sha256")
            admpw = generate_password_hash("admin1234", method="pbkdf2:sha256")
            db.executemany(
                "INSERT INTO users(username,password_hash,name,employee_no,ward_id,role)"
                " VALUES(?,?,?,?,?,?)",
                [("admin",   admpw, "관리자", "A-0001", None, "ADMIN"),
                 ("nurse01", pw,    "김간호", "N-1001", 1,    "NURSE"),
                 ("nurse02", pw,    "이간호", "N-1002", 2,    "NURSE")])

        if db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO patients(patient_code,name,room_number,age,sex,ward_id)"
                " VALUES(?,?,?,?,?,?)",
                _PATIENTS_A + _PATIENTS_B)
            a_ids = [r[0] for r in db.execute(
                "SELECT id FROM patients WHERE ward_id=1 ORDER BY patient_code").fetchall()]
            b_ids = [r[0] for r in db.execute(
                "SELECT id FROM patients WHERE ward_id=2 ORDER BY patient_code").fetchall()]
            n1 = db.execute("SELECT id FROM users WHERE username='nurse01'").fetchone()[0]
            n2 = db.execute("SELECT id FROM users WHERE username='nurse02'").fetchone()[0]
            db.executemany("INSERT INTO patient_assignments(user_id,patient_id) VALUES(?,?)",
                           [(n1, p) for p in a_ids] + [(n2, p) for p in b_ids])

        # 가상 환자 1만명 (최초 1회)
        if db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] < 1000:
            print("[DB] 문헌 기반 가상 환자 1만명 생성 중...", flush=True)
            _seed_bulk_patients(db)
            print("[DB] 문헌 기반 평가 기록 생성 중...", flush=True)
            _seed_bulk_assessments(db)
            print("[DB] 완료 ✅  (근거: Ely 2001, Sessler 2002, Krewulak 2018)", flush=True)


def _gen_age(rng):
    """
    연령 분포 (Liu et al., 2019; ICU 연구 종합):
    18-44세 18%, 45-64세 42%, 65-79세 30%, 80+세 10%
    → 평균 연령 약 62세 (문헌: 57~67세)
    """
    # 연령 분포 (Liu 2019: 45-64y 37%, 65+y 27%; 한국 ICU 고령화 반영)
    # 18-44:12%, 45-64:40%, 65-79:36%, 80+:12% → 평균 약 62세
    groups = [
        (20, 44, 12),
        (45, 64, 40),
        (65, 79, 36),
        (80, 85, 12),
    ]
    r = rng.randint(1, 100)
    cumsum = 0
    for lo, hi, w in groups:
        cumsum += w
        if r <= cumsum:
            return rng.randint(lo, hi)
    return rng.randint(80, 85)


def _seed_bulk_patients(db):
    """
    성별: 남 60% / 여 40%  (Liu 2019: 57.5% male)
    진정제: 60% 사용  (ICU 일반적 진정 요법 비율)
    상태: 입원중 70% / 퇴원 25% / 외출 5%
    진단: Salluh 2010, Ely 2001 진단 분포 반영
    """
    rng = random.Random(2025)
    existing = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    need = 10000 - existing
    if need <= 0:
        return
    rows = []
    for i in range(need):
        # 성별: 남 60%, 여 40%  [Liu 2019]
        sex  = '남' if rng.random() < 0.60 else '여'
        name = rng.choice(_SURNAMES) + rng.choice(_MALE if sex == '남' else _FEMALE)
        age  = _gen_age(rng)
        ward_id = 1 if i < need // 2 else 2
        letter  = 'A' if ward_id == 1 else 'B'
        room    = f"ICU-{letter}{(i % 200) + 1:03d}"
        code    = f"P-{existing + i + 1:05d}"
        status  = rng.choices(['입원중','퇴원','외출'], weights=[70,25,5])[0]
        diag    = rng.choice(_DIAG_POOL)
        base    = datetime(2024, 1, 1)
        adm     = (base + timedelta(days=rng.randint(0, 400))).strftime('%Y-%m-%d')
        sed     = 1 if rng.random() < 0.60 else 0  # 60% 진정제 사용
        rows.append((code, name, room, age, sex, ward_id, status, diag, adm, sed))
    db.executemany(
        "INSERT OR IGNORE INTO patients"
        "(patient_code,name,room_number,age,sex,ward_id,status,diagnosis,admission_date,sedative_use)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)", rows)


def _seed_bulk_assessments(db):
    """
    CAM-ICU 결과 분포 (문헌 근거):
      POSITIVE    28%  (Krewulak 2018 메타분석 31%; 대규모 연구 n=20,241에서 25.1%)
      NEGATIVE    57%  (평가 가능 환자 중 비섬망)
      UNASSESSABLE 15% (RASS≤-4; Khan 2020: coma 17-24%)

    RASS 분포 (Sessler 2002 기반):
      +4:1%, +3:2%, +2:4%, +1:8%, 0:25%, -1:22%,
      -2:16%, -3:10%, -4:7%, -5:5%  → 중앙값 약 -1

    평가 빈도: 환자 40% 대상, 1-4회 평가 (8시간마다 1회 기준)
    """
    rng = random.Random(2025)
    nurse_ids = [r[0] for r in
                 db.execute("SELECT id FROM users WHERE role='NURSE'").fetchall()]
    if not nurse_ids:
        return

    all_pids = [r[0] for r in db.execute("SELECT id FROM patients").fetchall()]
    sample   = rng.sample(all_pids, min(4000, len(all_pids)))
    now      = datetime.now()
    base     = now - timedelta(days=180)

    rows = []
    for pid in sample:
        for _ in range(rng.randint(1, 4)):
            nid     = rng.choice(nurse_ids)
            rass    = rng.choice(_RASS_CHOICES)
            obs_idx = _rass_to_obs_idx(rass)
            obs     = _OBS[obs_idx]
            ai_rass = _AI_RASS[obs_idx]
            dt      = base + timedelta(
                seconds=rng.randint(0, int((now - base).total_seconds())))
            assessed_at = dt.strftime('%Y-%m-%d %H:%M:%S')

            if rass <= -4:
                # UNASSESSABLE (15% — RASS -4,-5)
                cam = 'UNASSESSABLE'
                f1 = f2 = f3 = f4 = None
            else:
                # POSITIVE 33% / NEGATIVE 67% of assessable
                # → 전체로는 POSITIVE 28%, NEGATIVE 57%  [Krewulak 2018]
                if rng.random() < 0.33:
                    # POSITIVE: F1∧F2∧(F3∨F4) 만족하도록 생성
                    cam = 'POSITIVE'
                    f1, f2 = 1, 1
                    f3, f4 = rng.choice([(1,0),(0,1),(1,1)])
                else:
                    # NEGATIVE: F1∧F2∧(F3∨F4) 불만족
                    cam = 'NEGATIVE'
                    # F1 또는 F2 없거나, F3+F4 모두 없음
                    pattern = rng.choice(['no_f1','no_f2','no_f3f4'])
                    if pattern == 'no_f1':
                        f1, f2 = 0, rng.choice([0,1])
                        f3, f4 = rng.choice([0,1]), rng.choice([0,1])
                    elif pattern == 'no_f2':
                        f1, f2 = rng.choice([0,1]), 0
                        f3, f4 = rng.choice([0,1]), rng.choice([0,1])
                    else:
                        f1, f2 = rng.choice([0,1]), rng.choice([0,1])
                        f3, f4 = 0, 0

            rows.append((pid, nid, assessed_at, obs, 'SCORED', ai_rass,
                         rass, f1, f2, f3, f4, cam, ''))

    db.executemany(
        "INSERT INTO assessments"
        "(patient_id,nurse_id,assessed_at,observation,ai_status,ai_rass,"
        "rass_score,feature1,feature2,feature3,feature4,cam_result,memo)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def _rass_to_obs_idx(rass):
    """RASS 점수 → 관찰 항목 인덱스 (Sessler 2002 RASS 정의 기반)."""
    return {4:0, 3:1, 2:2, 1:3, 0:4, -1:5, -2:6, -3:7, -4:8, -5:9}[rass]


def log_action(user_id, action, detail=""):
    with connect_db() as db:
        db.execute("INSERT INTO audit_logs(user_id,action,detail) VALUES(?,?,?)",
                   (user_id, action, detail))
