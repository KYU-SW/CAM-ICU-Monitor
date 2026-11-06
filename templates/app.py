import json, os, sys, traceback
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from cam_icu_logic import calculate_cam_icu, derive_f3, suggest_rass_by_index, OBSERVATION_OPTIONS
from database import connect_db, init_db, log_action

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cam-icu-rass-2025")

print("[startup] DB 초기화 중...", flush=True)
init_db()
print("[startup] 완료", flush=True)

SORT_OPTIONS = {
    "room":     ("병실 순",        "room_number ASC"),
    "risk":     ("위험 순",        "CASE last_res WHEN 'POSITIVE' THEN 0 WHEN 'NEGATIVE' THEN 1 WHEN 'UNASSESSABLE' THEN 2 ELSE 3 END"),
    "reassess": ("재평가 필요 순", "(last_at IS NOT NULL), last_at ASC"),
    "name":     ("이름 순",        "name ASC"),
    "recent":   ("최근 검사 순",   "(last_at IS NULL), last_at DESC"),
}

# ── 데코레이터 ─────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

def nurse_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = get_current_user()
        if not u or u["role"] != "NURSE":
            abort(403)
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = get_current_user()
        if not u or u["role"] != "ADMIN":
            abort(403)
        return f(*a, **k)
    return w

# ── 헬퍼 ──────────────────────────────────────────────
def get_current_user():
    if "user_id" not in session:
        return None
    with connect_db() as db:
        return db.execute(
            "SELECT u.*, COALESCE(w.name,'관리자') AS ward_name "
            "FROM users u LEFT JOIN wards w ON w.id=u.ward_id WHERE u.id=?",
            (session["user_id"],)).fetchone()

def get_assigned_patient(patient_id):
    with connect_db() as db:
        return db.execute(
            "SELECT p.*, w.name AS ward_name FROM patients p "
            "JOIN wards w ON w.id=p.ward_id "
            "JOIN patient_assignments pa ON pa.patient_id=p.id "
            "WHERE p.id=? AND pa.user_id=?",
            (patient_id, session["user_id"])).fetchone()

def get_patients_sorted(user_id, sort):
    _, sql = SORT_OPTIONS.get(sort, SORT_OPTIONS["room"])
    with connect_db() as db:
        return db.execute(
            "WITH pd AS ("
            "  SELECT p.*,"
            "    (SELECT cam_result FROM assessments a WHERE a.patient_id=p.id ORDER BY a.id DESC LIMIT 1) AS last_res,"
            "    (SELECT assessed_at FROM assessments a WHERE a.patient_id=p.id ORDER BY a.id DESC LIMIT 1) AS last_at"
            "  FROM patients p"
            "  JOIN patient_assignments pa ON pa.patient_id=p.id"
            "  WHERE pa.user_id=?"
            f") SELECT * FROM pd ORDER BY {sql}",
            (user_id,)).fetchall()

@app.context_processor
def inject_user():
    return {"current_user": get_current_user()}

# ── 인증 ──────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            with connect_db() as db:
                db.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
            log_action(user["id"], "LOGIN")
            return redirect(url_for("admin") if user["role"] == "ADMIN" else url_for("dashboard"))
        flash("아이디 또는 비밀번호를 확인해 주세요.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    uid = session.get("user_id")
    session.clear()
    if uid:
        log_action(uid, "LOGOUT")
    return redirect(url_for("login"))

# ── 관리자: 간호사 관리 ───────────────────────────────
@app.route("/admin")
@admin_required
def admin():
    with connect_db() as db:
        nurses = db.execute(
            "SELECT u.*, COALESCE(w.name,'—') AS ward_name,"
            " (SELECT COUNT(*) FROM patient_assignments pa WHERE pa.user_id=u.id) AS patient_count"
            " FROM users u LEFT JOIN wards w ON w.id=u.ward_id"
            " WHERE u.role='NURSE' ORDER BY u.id").fetchall()
        wards = db.execute("SELECT * FROM wards ORDER BY id").fetchall()
    return render_template("admin.html", nurses=nurses, wards=wards)

@app.route("/admin/nurses/new", methods=["GET", "POST"])
@admin_required
def register_nurse():
    with connect_db() as db:
        wards = db.execute("SELECT * FROM wards ORDER BY id").fetchall()
    if request.method == "POST":
        username    = request.form.get("username", "").strip()
        name        = request.form.get("name", "").strip()
        employee_no = request.form.get("employee_no", "").strip()
        ward_id     = request.form.get("ward_id", "")
        password    = request.form.get("password", "")
        confirm     = request.form.get("confirm", "")
        if not all([username, name, employee_no, ward_id, password]):
            flash("모든 항목을 입력해 주세요.", "error")
        elif password != confirm:
            flash("비밀번호가 일치하지 않습니다.", "error")
        elif len(password) < 4:
            flash("비밀번호는 4자 이상이어야 합니다.", "error")
        else:
            try:
                pw = generate_password_hash(password, method="pbkdf2:sha256")
                with connect_db() as db:
                    db.execute(
                        "INSERT INTO users(username,password_hash,name,employee_no,ward_id,role)"
                        " VALUES(?,?,?,?,?,'NURSE')",
                        (username, pw, name, employee_no, int(ward_id)))
                log_action(session["user_id"], "NURSE_REGISTERED", f"username={username}")
                flash(f"'{name}' 간호사 계정이 생성되었습니다.", "success")
                return redirect(url_for("admin"))
            except Exception as e:
                flash("이미 사용 중인 아이디 또는 사번입니다." if "UNIQUE" in str(e) else f"오류: {e}", "error")
    return render_template("nurse_register.html", wards=wards)

@app.route("/admin/nurses/<int:nurse_id>/delete", methods=["POST"])
@admin_required
def delete_nurse(nurse_id):
    with connect_db() as db:
        nurse = db.execute(
            "SELECT * FROM users WHERE id=? AND role='NURSE'", (nurse_id,)).fetchone()
    if not nurse:
        flash("존재하지 않는 계정입니다.", "error")
        return redirect(url_for("admin"))
    if request.form.get("confirm_username", "") != nurse["username"]:
        flash("아이디가 일치하지 않습니다.", "error")
        return redirect(url_for("admin"))
    if not check_password_hash(nurse["password_hash"], request.form.get("confirm_password", "")):
        flash("비밀번호가 일치하지 않습니다.", "error")
        return redirect(url_for("admin"))
    with connect_db() as db:
        db.execute("DELETE FROM patient_assignments WHERE user_id=?", (nurse_id,))
        db.execute("DELETE FROM users WHERE id=?", (nurse_id,))
    log_action(session["user_id"], "NURSE_DELETED", f"username={nurse['username']}")
    flash(f"'{nurse['name']}' 간호사 계정을 삭제했습니다.", "success")
    return redirect(url_for("admin"))

# ── 관리자: 환자 관리 ─────────────────────────────────
@app.route("/admin/patients")
@admin_required
def admin_patients():
    q           = request.args.get("q", "").strip()
    ward_filter = request.args.get("ward", "").strip()
    page        = max(1, int(request.args.get("page", 1)))
    per         = 50
    off         = (page - 1) * per

    with connect_db() as db:
        wards  = db.execute("SELECT * FROM wards ORDER BY id").fetchall()
        nurses = db.execute("SELECT * FROM users WHERE role='NURSE' ORDER BY name").fetchall()

        # 병동별 환자 수 (탭 배지용)
        ward_counts = {r[0]: r[1] for r in db.execute(
            "SELECT ward_id, COUNT(*) FROM patients GROUP BY ward_id").fetchall()}
        total_count = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]

        base_q = (
            "SELECT p.*, w.name AS ward_name,"
            " (SELECT u.name FROM patient_assignments pa JOIN users u ON u.id=pa.user_id"
            "  WHERE pa.patient_id=p.id LIMIT 1) AS nurse_name"
            " FROM patients p JOIN wards w ON w.id=p.ward_id"
        )

        conditions = []
        params     = []

        if q:
            like = f"%{q}%"
            conditions.append("(p.name LIKE ? OR p.patient_code LIKE ? OR p.room_number LIKE ?)")
            params += [like, like, like]

        if ward_filter:
            conditions.append("p.ward_id=?")
            params.append(int(ward_filter))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_q = f"SELECT COUNT(*) FROM patients p {where}"
        total   = db.execute(count_q, params).fetchone()[0]

        patients = db.execute(
            f"{base_q} {where} ORDER BY p.patient_code LIMIT ? OFFSET ?",
            params + [per, off]).fetchall()

    return render_template("admin_patients.html",
                           patients=patients, q=q, page=page,
                           ward_filter=ward_filter,
                           total=total, total_pages=(total + per - 1) // per,
                           wards=wards, nurses=nurses,
                           ward_counts=ward_counts, total_count=total_count)

@app.route("/admin/patients/new", methods=["GET", "POST"])
@admin_required
def admin_patient_new():
    with connect_db() as db:
        wards  = db.execute("SELECT * FROM wards ORDER BY id").fetchall()
        nurses = db.execute("SELECT * FROM users WHERE role='NURSE' ORDER BY name").fetchall()
        max_n  = db.execute(
            "SELECT MAX(CAST(REPLACE(patient_code,'P-','') AS INTEGER))"
            " FROM patients WHERE patient_code LIKE 'P-%'").fetchone()[0] or 0
    default_code = f"P-{max_n + 1:05d}"
    if request.method == "POST":
        f = request.form
        try:
            with connect_db() as db:
                db.execute(
                    "INSERT INTO patients(patient_code,name,room_number,age,sex,ward_id,"
                    "status,diagnosis,admission_date,sedative_use) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (f["patient_code"].strip(), f["name"].strip(), f["room_number"].strip(),
                     int(f["age"]), f["sex"], int(f["ward_id"]),
                     f.get("status", "입원중"), f.get("diagnosis", ""),
                     f.get("admission_date", ""), 1 if f.get("sedative_use") else 0))
                new_pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                nurse_id = f.get("nurse_id", "")
                if nurse_id:
                    db.execute(
                        "INSERT OR IGNORE INTO patient_assignments(user_id,patient_id) VALUES(?,?)",
                        (int(nurse_id), new_pid))
            flash("환자가 추가되었습니다.", "success")
            return redirect(url_for("admin_patients"))
        except Exception as e:
            flash(f"오류: {e}", "error")
    return render_template("admin_patient_form.html",
                           patient=None, default_code=default_code,
                           wards=wards, nurses=nurses, assigned_nurse_id=None)

@app.route("/admin/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_patient_edit(patient_id):
    with connect_db() as db:
        patient  = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not patient:
            abort(404)
        wards    = db.execute("SELECT * FROM wards ORDER BY id").fetchall()
        nurses   = db.execute("SELECT * FROM users WHERE role='NURSE' ORDER BY name").fetchall()
        assigned = db.execute(
            "SELECT user_id FROM patient_assignments WHERE patient_id=?",
            (patient_id,)).fetchone()
    if request.method == "POST":
        f = request.form
        try:
            with connect_db() as db:
                db.execute(
                    "UPDATE patients SET name=?,room_number=?,age=?,sex=?,ward_id=?,"
                    "status=?,diagnosis=?,admission_date=?,sedative_use=? WHERE id=?",
                    (f["name"].strip(), f["room_number"].strip(), int(f["age"]),
                     f["sex"], int(f["ward_id"]), f.get("status", "입원중"),
                     f.get("diagnosis", ""), f.get("admission_date", ""),
                     1 if f.get("sedative_use") else 0, patient_id))
                db.execute("DELETE FROM patient_assignments WHERE patient_id=?", (patient_id,))
                nurse_id = f.get("nurse_id", "")
                if nurse_id:
                    db.execute(
                        "INSERT INTO patient_assignments(user_id,patient_id) VALUES(?,?)",
                        (int(nurse_id), patient_id))
            flash("환자 정보가 수정되었습니다.", "success")
            return redirect(url_for("admin_patients"))
        except Exception as e:
            flash(f"오류: {e}", "error")
    return render_template("admin_patient_form.html",
                           patient=patient, default_code=None,
                           wards=wards, nurses=nurses,
                           assigned_nurse_id=assigned["user_id"] if assigned else None)

@app.route("/admin/patients/<int:patient_id>/delete", methods=["POST"])
@admin_required
def admin_patient_delete(patient_id):
    with connect_db() as db:
        patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not patient:
            abort(404)
        db.execute("DELETE FROM patient_assignments WHERE patient_id=?", (patient_id,))
        db.execute("DELETE FROM assessments WHERE patient_id=?", (patient_id,))
        db.execute("DELETE FROM patients WHERE id=?", (patient_id,))
    flash(f"'{patient['name']}' 환자를 삭제했습니다.", "success")
    return redirect(url_for("admin_patients"))

# ── 통계 ──────────────────────────────────────────────
@app.route("/stats")
@login_required
def stats():
    with connect_db() as db:
        total_p  = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        total_a  = db.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
        recent_7 = db.execute(
            "SELECT COUNT(*) FROM assessments WHERE assessed_at>=datetime('now','-7 days')"
        ).fetchone()[0]
        cam_dist = {r["cam_result"]: r["cnt"] for r in db.execute(
            "SELECT cam_result, COUNT(*) cnt FROM assessments GROUP BY cam_result").fetchall()}
        rass_d   = db.execute(
            "SELECT rass_score, COUNT(*) cnt FROM assessments"
            " GROUP BY rass_score ORDER BY rass_score").fetchall()
        weekly   = db.execute(
            "SELECT strftime('%Y-%m-%d',assessed_at,'weekday 0','-6 days') AS wk,"
            " COUNT(*) total, SUM(cam_result='POSITIVE') positive"
            " FROM assessments WHERE assessed_at>=datetime('now','-84 days')"
            " GROUP BY wk ORDER BY wk").fetchall()
        ward_s   = db.execute(
            "SELECT w.name, COUNT(DISTINCT p.id) patients,"
            " COUNT(a.id) assessments,"
            " SUM(CASE WHEN a.cam_result='POSITIVE' THEN 1 ELSE 0 END) positive"
            " FROM wards w JOIN patients p ON p.ward_id=w.id"
            " LEFT JOIN assessments a ON a.patient_id=p.id"
            " GROUP BY w.id ORDER BY w.id").fetchall()
        top_pos  = db.execute(
            "SELECT p.name, p.room_number, COUNT(*) cnt"
            " FROM assessments a JOIN patients p ON p.id=a.patient_id"
            " WHERE a.cam_result='POSITIVE'"
            " GROUP BY a.patient_id ORDER BY cnt DESC LIMIT 10").fetchall()
    pos_rate = round(cam_dist.get("POSITIVE", 0) / total_a * 100, 1) if total_a else 0
    chart = json.dumps({
        "cam":    cam_dist,
        "rass":   {"labels": [r["rass_score"] for r in rass_d],
                   "data":   [r["cnt"] for r in rass_d]},
        "weekly": {"labels":   [r["wk"] for r in weekly],
                   "total":    [r["total"] for r in weekly],
                   "positive": [r["positive"] or 0 for r in weekly]},
        "wards":  {"labels":      [r["name"] for r in ward_s],
                   "patients":    [r["patients"] for r in ward_s],
                   "assessments": [r["assessments"] for r in ward_s]},
    })
    return render_template("stats.html",
                           total_p=total_p, total_a=total_a,
                           recent_7=recent_7, pos_rate=pos_rate,
                           chart=chart, ward_stats=ward_s, top_pos=top_pos)

# ── 대시보드 ──────────────────────────────────────────
@app.route("/")
@nurse_required
def dashboard():
    sort = request.args.get("sort", "room")
    if sort not in SORT_OPTIONS:
        sort = "room"
    patients = get_patients_sorted(session["user_id"], sort)
    return render_template("dashboard.html", patients=patients,
                           sort=sort, sort_options=SORT_OPTIONS)

# ── PWA 서비스 워커 ───────────────────────────────────
@app.route("/sw.js")
def service_worker():
    response = send_from_directory(app.static_folder, "sw.js")
    response.headers["Cache-Control"] = "no-cache"
    return response

# ── 근무 인계 요약 ────────────────────────────────────
REASSESS_HOURS = {"POSITIVE": 4, "NEGATIVE": 8}

def format_kst(utc_dt):
    return (utc_dt + timedelta(hours=9)).strftime("%m-%d %H:%M")

def build_handover_item(patient, rows):
    item = {"patient": patient, "latest": rows[0] if rows else None,
            "flags": [], "priority": 9, "assessed_text": "—", "due_text": "—"}
    if not rows:
        item["flags"].append("미평가")
        item["priority"] = 3
        return item

    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    assessed_at = datetime.strptime(latest["assessed_at"][:19], "%Y-%m-%d %H:%M:%S")
    item["assessed_text"] = format_kst(assessed_at)

    hours = REASSESS_HOURS.get(latest["cam_result"])
    if hours:
        due_at = assessed_at + timedelta(hours=hours)
        item["due_text"] = format_kst(due_at)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if due_at < now:
            item["flags"].append("재평가 마감 초과")
            item["priority"] = 0

    if previous:
        if latest["cam_result"] == "POSITIVE" and previous["cam_result"] != "POSITIVE":
            item["flags"].append("POSITIVE 전환")
            item["priority"] = min(item["priority"], 1)
        elif latest["cam_result"] != "POSITIVE" and previous["cam_result"] == "POSITIVE":
            item["flags"].append("POSITIVE 해제")
        change = latest["rass_score"] - previous["rass_score"]
        if abs(change) >= 2:
            item["flags"].append(f"RASS {previous['rass_score']:+d} → {latest['rass_score']:+d}")
            item["priority"] = min(item["priority"], 2)

    if latest["cam_result"] == "POSITIVE":
        item["priority"] = min(item["priority"], 2)
    return item

@app.route("/handover")
@nurse_required
def handover():
    with connect_db() as db:
        patients = db.execute(
            "SELECT p.* FROM patients p "
            "JOIN patient_assignments pa ON pa.patient_id=p.id "
            "WHERE pa.user_id=? AND p.status='입원중' ORDER BY p.room_number",
            (session["user_id"],)).fetchall()
        items = []
        for patient in patients:
            rows = db.execute(
                "SELECT rass_score, cam_result, assessed_at, memo FROM assessments "
                "WHERE patient_id=? ORDER BY assessed_at DESC, id DESC LIMIT 2",
                (patient["id"],)).fetchall()
            items.append(build_handover_item(patient, rows))
    items.sort(key=lambda item: item["priority"])
    return render_template("handover.html", items=items)

# ── 환자 상세 ─────────────────────────────────────────
@app.route("/patients/<int:patient_id>")
@login_required
def patient_detail(patient_id):
    patient = get_assigned_patient(patient_id)
    if not patient:
        abort(403)
    with connect_db() as db:
        records = db.execute(
            "SELECT a.*, u.name AS nurse_name FROM assessments a"
            " JOIN users u ON u.id=a.nurse_id"
            " WHERE a.patient_id=? ORDER BY a.id DESC",
            (patient_id,)).fetchall()
    r_list = list(reversed(list(records)))
    cm = {"POSITIVE": "#d64545", "NEGATIVE": "#23865f", "UNASSESSABLE": "#654d96"}
    chart = json.dumps({
        "labels":  [r["assessed_at"][:16] for r in r_list],
        "rass":    [r["rass_score"] for r in r_list],
        "colors":  [cm.get(r["cam_result"], "#6b7b8d") for r in r_list],
        "results": [r["cam_result"] for r in r_list],
    })
    return render_template("patient_detail.html",
                           patient=patient, records=records, chart_data=chart)

# ── 환자 상태 수정 ────────────────────────────────────
@app.route("/patients/<int:patient_id>/status", methods=["POST"])
@login_required
def update_patient_status(patient_id):
    patient = get_assigned_patient(patient_id)
    if not patient:
        abort(403)
    status = request.form.get("status", "")
    if status not in ("입원중", "외출", "퇴원"):
        abort(400)
    with connect_db() as db:
        db.execute("UPDATE patients SET status=? WHERE id=?", (status, patient_id))
    flash(f"{patient['name']} 상태를 '{status}'로 변경했습니다.", "success")
    return redirect(request.referrer or url_for("mypage"))

# ── 평가 ──────────────────────────────────────────────
@app.route("/patients/<int:patient_id>/assess", methods=["GET", "POST"])
@nurse_required
def assessment(patient_id):
    patient = get_assigned_patient(patient_id)
    if not patient:
        abort(403)
    suggestion = None
    form_data  = {}
    with connect_db() as db:
        prev = db.execute(
            "SELECT * FROM assessments WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (patient_id,)).fetchone()
    if request.method == "POST":
        obs_str   = request.form.get("observation_index", "")
        form_data = {"observation_index": obs_str,
                     **{f"feature{i}": request.form.get(f"feature{i}") for i in range(1, 5)}}
        action = request.form.get("action", "save")
        try:
            suggestion = suggest_rass_by_index(int(obs_str))
        except Exception:
            suggestion = None
        if action == "suggest":
            if suggestion is None:
                flash("표준 절차 관찰 결과를 선택해 주세요.", "error")
            return render_template("assessment.html", patient=patient,
                                   suggestion=suggestion, form_data=form_data,
                                   obs_options=OBSERVATION_OPTIONS, prev=prev)
        try:
            if suggestion is None:
                raise ValueError("표준 절차 관찰 결과를 선택해 주세요.")
            obs_text = OBSERVATION_OPTIONS[int(obs_str)][0]
            rass_str = request.form.get("rass_score", "")
            if not rass_str:
                raise ValueError("최종 RASS 점수를 선택해 주세요.")
            rass = int(rass_str)
            memo = request.form.get("memo", "").strip()
            if rass <= -4:
                cam_result = calculate_cam_icu(rass)
                db_feat    = (None, None, None, None)
            else:
                for i in (1, 2, 4):
                    if request.form.get(f"feature{i}") not in {"yes", "no"}:
                        raise ValueError("CAM-ICU 특징 F1, F2, F4를 모두 선택해 주세요.")
                f1, f2, f4 = (request.form.get(f"feature{i}") == "yes" for i in (1, 2, 4))
                db_feat    = (f1, f2, derive_f3(rass), f4)
                cam_result = calculate_cam_icu(rass, f1, f2, f4)
            with connect_db() as db:
                cur = db.execute(
                    "INSERT INTO assessments(patient_id,nurse_id,observation,ai_status,ai_rass,"
                    "rass_score,feature1,feature2,feature3,feature4,cam_result,memo)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (patient_id, session["user_id"], obs_text,
                     suggestion["status"], suggestion["score"],
                     rass, *db_feat, cam_result, memo))
                new_assessment_id = cur.lastrowid
            log_action(session["user_id"], "ASSESSMENT_CREATED",
                       f"assessment_id={new_assessment_id}")
            return redirect(url_for("result", assessment_id=new_assessment_id))
        except (ValueError, TypeError) as e:
            flash(str(e), "error")
    return render_template("assessment.html", patient=patient,
                           suggestion=suggestion, form_data=form_data,
                           obs_options=OBSERVATION_OPTIONS, prev=prev)

# ── 결과 ──────────────────────────────────────────────
@app.route("/results/<int:assessment_id>")
@login_required
def result(assessment_id):
    with connect_db() as db:
        row = db.execute(
            "SELECT a.*, p.name AS patient_name, p.room_number, u.name AS nurse_name"
            " FROM assessments a"
            " JOIN patients p ON p.id=a.patient_id"
            " JOIN users u ON u.id=a.nurse_id"
            " JOIN patient_assignments pa ON pa.patient_id=p.id"
            " WHERE a.id=? AND pa.user_id=?",
            (assessment_id, session["user_id"])).fetchone()
    if not row:
        abort(403)
    return render_template("result.html", row=row)

# ── 마이페이지 ────────────────────────────────────────
@app.route("/mypage")
@nurse_required
def mypage():
    sort = request.args.get("sort", "room")
    if sort not in SORT_OPTIONS:
        sort = "room"
    with connect_db() as db:
        stats = db.execute(
            "SELECT COUNT(*) total,"
            " SUM(cam_result='POSITIVE') positive,"
            " SUM(cam_result='NEGATIVE') negative,"
            " SUM(cam_result='UNASSESSABLE') unassessable"
            " FROM assessments WHERE nurse_id=?",
            (session["user_id"],)).fetchone()
    patients = get_patients_sorted(session["user_id"], sort)
    return render_template("mypage.html", stats=stats, patients=patients,
                           sort=sort, sort_options=SORT_OPTIONS)

# ── 에러 핸들러 ───────────────────────────────────────
@app.errorhandler(403)
def e403(_):
    return render_template("error.html", code=403, message="접근 권한이 없습니다."), 403

@app.errorhandler(404)
def e404(_):
    return render_template("error.html", code=404, message="페이지를 찾을 수 없습니다."), 404

@app.errorhandler(Exception)
def e500(e):
    print("\n" + "=" * 60, flush=True)
    print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    print("=" * 60 + "\n", flush=True)
    return render_template("error.html", code=500,
                           message=f"서버 오류: {type(e).__name__}: {e}"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
