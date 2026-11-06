"""طبقة البيانات + منطق العمل لبرنامج Myshurance."""
import io
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

CAIRO = ZoneInfo("Africa/Cairo")

PROVIDERS = ["Sarwa Life", "Sarwa", "Orient", "AXA", "GIG Life", "Allianz"]
CLIENTS_MAP = {
    "90502239912": "مدرسه نيو سكول",
    "90502239913": "بوب ليدرز",
    "90502239934": "مدرسه ليدرز انترناشونال",
    "90502239932": "ليدرز كوليدج للخدمات التعليميه",
}
DEFAULT_START, DEFAULT_END = "2026-09-29", "2027-09-28"

REQ_TYPES = ["add", "delete", "replace"]
REQ_STATUSES = ["draft", "sent", "review", "done", "rejected", "cancelled"]
OPEN_STATUSES = ["draft", "sent", "review"]
TRANSITIONS = {
    "draft": ["sent", "cancelled"],
    "sent": ["review", "rejected", "cancelled"],
    "review": ["done", "rejected", "cancelled"],
    "rejected": ["draft"],
    "done": [],
    "cancelled": [],
}
REF_PREFIX = {"add": "ADD", "delete": "DEL", "replace": "REP"}
DEPENDENCIES = ["PRINCIPAL", "SPOUSE", "CHILD", "OTHER"]

# حقول العضو اللي بتتنقل في طلب الإضافة
MEMBER_FIELDS = ["name", "staff_no", "card_no", "national_id", "phone", "dependency", "dob",
                 "gender", "category", "source_start", "source_end"]

COLS = {
    "members": ["name", "staff_no", "card_no", "national_id", "phone", "policy_no", "dependency", "dob",
                "gender", "category", "source_start", "source_end", "status", "termination_date"],
    "requests": ["ref_no", "type", "member_id", "member_name", "staff_no", "policy_no", "effective_date",
                 "details", "payload", "status", "created_by", "updated_at"],
    "policies": ["policy_no", "type", "start_date", "end_date", "premium", "status"],
    "notifications": ["event", "message", "status", "attempts", "sent_at", "error"],
}

TYPE_AR = {"add": "إضافة", "delete": "حذف", "replace": "بدل فاقد"}
STATUS_AR = {"draft": "مسودة", "sent": "مُرسل", "review": "قيد المراجعة", "done": "تم التنفيذ",
             "rejected": "مرفوض", "cancelled": "ملغي"}
ICON = {"add": "🟢", "delete": "🔴", "replace": "🟡"}


# ───────────────────────── أدوات عامة ─────────────────────────
def now_iso():
    return datetime.now(CAIRO).isoformat(timespec="seconds")


def nn(v):
    """يرجّع None للفاضي / NaN، وإلا القيمة (نصوص بتتقص)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def str_id(v):
    """أرقام وظيفية/كروت: يمنع 104.0 ويحافظ على الأصفار لو جاية نص."""
    v = nn(v)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def to_iso(v):
    v = nn(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s):
        d = pd.to_datetime(s, errors="coerce")
    else:
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.date().isoformat()


def fmt_date(v):
    iso = to_iso(v)
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "—"


def fmt_ts(v):
    v = nn(v)
    return str(v)[:16].replace("T", " ") if v else "—"


def norm_name(s):
    return re.sub(r"\s+", " ", str(nn(s) or "")).casefold()


def norm_gender(v):
    v = str(nn(v) or "").strip().lower()
    if v in ("m", "male", "ذكر", "1"):
        return "M"
    if v in ("f", "female", "أنثى", "انثى", "2"):
        return "F"
    return None


def norm_category(v):
    m = re.match(r"([A-D])(?:$|[\s\-_/])", str(nn(v) or "").strip().upper())
    return m.group(1) if m else None


def parse_nid(nid):
    """يستخرج تاريخ الميلاد والنوع من الرقم القومي المصري (14 رقم)."""
    nid = str(nn(nid) or "")
    if len(nid) != 14 or not nid.isdigit():
        return {}
    try:
        century, yy, mm, dd = int(nid[0]), int(nid[1:3]), int(nid[3:5]), int(nid[5:7])
        if century not in (2, 3):
            return {}
        year = (1900 if century == 2 else 2000) + yy
        return {"dob": date(year, mm, dd).isoformat(), "gender": "M" if int(nid[12]) % 2 == 1 else "F"}
    except ValueError:
        return {}


def secret(name):
    try:
        v = st.secrets.get(name)
    except Exception:
        return None
    return str(v) if v not in (None, "") else None


# ───────────────────────── الاتصال بـ Supabase ─────────────────────────
@st.cache_resource
def _connect():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_KEY")
    if not url or not key:
        return None, None
    try:
        from supabase import create_client
        return create_client(url, key), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


SB, SB_ERR = _connect()


def _mem():
    if "db" not in st.session_state:
        st.session_state.db = {k: [] for k in COLS}
        for no in CLIENTS_MAP:
            st.session_state.db["policies"].append({
                "id": str(uuid.uuid4()), "policy_no": no, "type": "p_health", "start_date": DEFAULT_START,
                "end_date": DEFAULT_END, "premium": 0, "status": "active", "created_at": now_iso()})
    return st.session_state.db


# ───────────────────────── CRUD ─────────────────────────
def _clean(table, row, drop_none):
    out = {}
    for k, v in row.items():
        if k not in COLS[table]:
            continue
        v = nn(v) if not isinstance(v, (dict, list)) else v
        if isinstance(v, (date, datetime)):
            v = v.isoformat()
        if v is None and drop_none:
            continue
        out[k] = v
    return out


def load(table):
    cols = ["id"] + COLS[table] + ["created_at"]
    rows = []
    try:
        if SB:
            start = 0
            while True:
                chunk = (SB.table(table).select("*").order("created_at", desc=True).order("id")
                         .range(start, start + 999).execute().data)
                rows += chunk
                if len(chunk) < 1000:
                    break
                start += 1000
        else:
            rows = list(reversed(_mem()[table]))
    except Exception as e:  # noqa: BLE001
        st.error(f"{table}: {e}")
        rows = []
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def insert(table, row):
    row = _clean(table, row, drop_none=True)
    if SB:
        res = SB.table(table).insert(row).execute()
        return res.data[0] if res.data else row
    rec = {**row, "id": str(uuid.uuid4()), "created_at": now_iso()}
    _mem()[table].append(rec)
    return rec


def insert_many(table, rows):
    rows = [_clean(table, r, drop_none=True) for r in rows]
    if not rows:
        return
    if SB:
        for i in range(0, len(rows), 200):
            SB.table(table).insert(rows[i:i + 200]).execute()
    else:
        for r in rows:
            _mem()[table].append({**r, "id": str(uuid.uuid4()), "created_at": now_iso()})


def update(table, rid, row):
    row = _clean(table, row, drop_none=False)
    if SB:
        SB.table(table).update(row).eq("id", rid).execute()
    else:
        for r in _mem()[table]:
            if r["id"] == rid:
                r.update(row)


# ───────────────────────── الأعضاء ─────────────────────────
def find_member(policy_no, staff_no=None, name=None, members=None):
    """يرجّع Series للعضو أو None. الأولوية للرقم الوظيفي ثم الاسم."""
    df = load("members") if members is None else members
    if df.empty:
        return None
    df = df[df["policy_no"].astype(str) == str(policy_no)]
    staff = str_id(staff_no)
    if staff:
        hit = df[df["staff_no"].map(str_id) == staff]
        if not hit.empty:
            return hit.iloc[0]
    if name:
        hit = df[df["name"].map(norm_name) == norm_name(name)]
        if not hit.empty:
            return hit.iloc[0]
    return None


ALIASES = {
    "staff_no": ["employee no", "employee number", "emp no", "staff no", "staff number", "staff id",
                 "الرقم الوظيفي", "الرقم الوظيفي staff number"],
    "name": ["employee name", "insured name", "member name", "full name", "name", "الاسم", "الاسم الكامل"],
    "card_no": ["card number", "card no", "card", "رقم كارت التأمين", "رقم الكارت"],
    "national_id": ["national id", "nid", "الرقم القومي"],
    "dob": ["date of birth", "dob", "birth date", "birthdate", "تاريخ الميلاد"],
    "gender": ["gender", "sex", "النوع"],
    "category": ["category", "class", "tier", "الفئة"],
    "dependency": ["dependency", "relation", "relationship", "member type", "نوع العضو",
                   "نوع العضو dependency"],
    "source_start": ["start date", "effective date", "inception date", "تاريخ السريان بالمصدر"],
    "source_end": ["end date", "expiry date", "expiry", "expiry date ", "تاريخ الانتهاء بالمصدر"],
}


def _hn(s):
    return re.sub(r"\s+", " ", re.sub(r"[\.:_#]+", " ", str(s))).strip().lower()


def detect_columns(df):
    cols = {_hn(c): c for c in df.columns}
    return {f: cols[_hn(n)] for f, names in ALIASES.items() for n in names[::-1] if _hn(n) in cols}


def rows_from_df(df, mapping):
    """mapping: field -> اسم عمود في الملف."""
    out = []
    for _, r in df.iterrows():
        g = lambda f: r.get(mapping[f]) if mapping.get(f) is not None else None  # noqa: E731
        name = nn(g("name"))
        if not name:
            continue
        nid = str_id(g("national_id"))
        row = {
            "name": str(name), "staff_no": str_id(g("staff_no")), "card_no": str_id(g("card_no")),
            "national_id": nid if nid and nid.isdigit() and len(nid) == 14 else None,
            "dob": to_iso(g("dob")), "gender": norm_gender(g("gender")), "category": norm_category(g("category")),
            "dependency": (str(nn(g("dependency"))).upper() if nn(g("dependency")) else None),
            "source_start": to_iso(g("source_start")), "source_end": to_iso(g("source_end")),
        }
        out.append(row)
    return out


def upsert_members(policy_no, rows):
    """يستورد صفوف الماستر: العضو (بالرقم الوظيفي أو الاسم) يتحدّث، والجديد يتضاف.
    مبيمسحش حد، ومبيغيّرش حالة العضوية. يرجّع (جديد، متحدّث، من غير تغيير)."""
    existing = load("members")
    existing = existing[existing["policy_no"].astype(str) == str(policy_no)]
    by_staff, by_name, rec = {}, {}, {}
    for r in existing.to_dict("records"):
        rec[r["id"]] = r
        if str_id(r["staff_no"]):
            by_staff[str_id(r["staff_no"])] = r["id"]
        by_name[norm_name(r["name"])] = r["id"]
    new_rows, updated, same = [], 0, 0
    for row in rows:
        key = row.get("staff_no")
        rid = by_staff.get(key) if key else by_name.get(norm_name(row["name"]))
        if rid is None:
            new_rows.append({**row, "policy_no": policy_no, "status": "active"})
            tag = f"new{len(new_rows)}"
            if key:
                by_staff[key] = tag
            by_name[norm_name(row["name"])] = tag
            continue
        if rid.startswith("new"):  # مكرر جوه نفس الشيت
            same += 1
            continue
        old = rec[rid]
        changes = {k: v for k, v in row.items() if v is not None and nn(old.get(k)) != v}
        if changes:
            update("members", rid, changes)
            updated += 1
        else:
            same += 1
    insert_many("members", new_rows)
    return len(new_rows), updated, same


# ───────────────────────── الوثائق ─────────────────────────
def policies_df():
    df = load("policies")
    rows = {str(r["policy_no"]): r for r in df.to_dict("records")}
    out = []
    for no, school in CLIENTS_MAP.items():
        r = rows.pop(no, {})
        out.append({"policy_no": no, "school": school, "start_date": to_iso(r.get("start_date")),
                    "end_date": to_iso(r.get("end_date"))})
    for no, r in rows.items():
        out.append({"policy_no": no, "school": "", "start_date": to_iso(r.get("start_date")),
                    "end_date": to_iso(r.get("end_date"))})
    return pd.DataFrame(out)


def save_policy_dates(policy_no, start, end):
    row = {"policy_no": policy_no, "type": "p_health", "start_date": to_iso(start), "end_date": to_iso(end),
           "status": "active"}
    if SB:
        SB.table("policies").upsert(_clean("policies", row, False), on_conflict="policy_no").execute()
        return
    for r in _mem()["policies"]:
        if r["policy_no"] == policy_no:
            r.update(row)
            return
    insert("policies", row)


# ───────────────────────── الإشعارات (واتساب عبر جدول notifications) ─────────────────────────
def _t():
    return datetime.now(CAIRO).strftime("%Y-%m-%d %H:%M")


def _ctx(req):
    pol = nn(req.get("policy_no")) or "—"
    school = CLIENTS_MAP.get(pol, "")
    return pol, f" ({school})" if school else ""


def msg_created(req, user):
    typ, (pol, school) = req["type"], _ctx(req)
    lines = [f"{ICON[typ]} طلب {TYPE_AR[typ]} جديد", f"المرجع: {req['ref_no']}",
             f"العضو: {req.get('member_name') or '—'}"]
    if nn(req.get("staff_no")):
        lines.append(f"الرقم الوظيفي: {req['staff_no']}")
    lines.append(f"الوثيقة: {pol}{school}")
    if typ == "delete" and nn(req.get("effective_date")):
        lines.append(f"تاريخ الحذف: {fmt_date(req['effective_date'])}")
    return "\n".join(lines + [f"بواسطة: {user or '—'}", f"الوقت: {_t()}"])


def msg_status(req, old, new, user):
    typ, (pol, school) = req["type"], _ctx(req)
    lines = [f"🔄 الطلب {req['ref_no']} ({TYPE_AR[typ]}) اتغيرت حالته",
             f"من: {STATUS_AR[old]} ← إلى: {STATUS_AR[new]}",
             f"العضو: {req.get('member_name') or '—'}", f"الوثيقة: {pol}{school}"]
    if new == "done" and typ == "add":
        lines.append("✅ تم تفعيل العضو في الوثيقة")
    elif new == "done" and typ == "delete":
        lines.append("⛔ تم إنهاء عضوية العضو (السجل محفوظ)")
    return "\n".join(lines + [f"بواسطة: {user or '—'}", f"الوقت: {_t()}"])


def notify_import(policy_no, new, upd, same, user):
    pol, school = _ctx({"policy_no": policy_no})
    notify("master_import", "\n".join([
        "📥 استيراد ماستر Allianz", f"الوثيقة: {pol}{school}",
        f"جديد: {new} | اتحدّث: {upd} | بدون تغيير: {same}", f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))


def notify_policy(policy_no, start, end, user):
    pol, school = _ctx({"policy_no": policy_no})
    notify("policy_dates", "\n".join([
        "📅 تعديل تواريخ وثيقة", f"الوثيقة: {pol}{school}",
        f"من {fmt_date(start)} إلى {fmt_date(end)}", f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))


def notify(event, message):
    try:
        insert("notifications", {"event": event, "message": message, "status": "pending", "attempts": 0})
    except Exception as e:  # noqa: BLE001 - الإشعار ميوقفش الشغل
        st.warning(f"notifications: {e}")


# ───────────────────────── الطلبات ─────────────────────────
def next_ref(rtype):
    prefix = f"REQ-{REF_PREFIX[rtype]}-{datetime.now(CAIRO).year}-"
    nums = [int(x[len(prefix):]) for x in load("requests")["ref_no"].dropna().astype(str)
            if x.startswith(prefix) and x[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) if nums else 0) + 1:04d}"


def _json_safe(d):
    return {k: (v.isoformat() if isinstance(v, (date, datetime)) else nn(v)) for k, v in d.items()}


def create_request(rtype, policy_no, member_name, payload, user, member_id=None, staff_no=None,
                   effective_date=None, details=None):
    rec = insert("requests", {
        "ref_no": next_ref(rtype), "type": rtype, "member_id": member_id, "member_name": member_name,
        "staff_no": staff_no, "policy_no": policy_no, "effective_date": to_iso(effective_date),
        "details": details, "payload": _json_safe(payload), "status": "draft", "created_by": user or None})
    rec = {**rec, "type": rtype, "member_name": member_name, "staff_no": staff_no, "policy_no": policy_no,
           "effective_date": to_iso(effective_date)}
    notify("request_created", msg_created(rec, user))
    return rec


def _open_requests(reqs, rtype, policy_no, member_id=None, staff_no=None, name=None):
    df = reqs[(reqs["type"] == rtype) & (reqs["status"].isin(OPEN_STATUSES))
              & (reqs["policy_no"].astype(str) == str(policy_no))]
    if member_id:
        return df[df["member_id"] == member_id]
    if staff_no:
        return df[df["staff_no"].map(str_id) == str_id(staff_no)]
    return df[df["member_name"].map(norm_name) == norm_name(name)]


def create_add_request(policy_no, data, effective_date, user):
    """يرجّع (الطلب، None) أو (None، مفتاح رسالة الخطأ)."""
    name = nn(data.get("name"))
    if not name:
        return None, "err_name"
    if not policy_no:
        return None, "err_policy"
    d = {k: nn(data.get(k)) for k in MEMBER_FIELDS}
    d["name"], d["staff_no"], d["card_no"] = str(name), str_id(d["staff_no"]), str_id(d["card_no"])
    if d["national_id"]:
        d["national_id"] = str_id(d["national_id"])
        info = parse_nid(d["national_id"])
        if not info:
            return None, "err_nid"
        d["dob"], d["gender"] = to_iso(d["dob"]) or info["dob"], norm_gender(d["gender"]) or info["gender"]
    d.update(dob=to_iso(d["dob"]), gender=norm_gender(d["gender"]), category=norm_category(d["category"]),
             source_start=to_iso(d["source_start"]), source_end=to_iso(d["source_end"]),
             dependency=(str(d["dependency"]).upper() if d["dependency"] else None))
    ex = find_member(policy_no, d["staff_no"], d["name"])
    if ex is not None and (nn(ex["status"]) or "active") == "active":
        return None, "err_exists"
    if not _open_requests(load("requests"), "add", policy_no, staff_no=d["staff_no"], name=d["name"]).empty:
        return None, "err_dup_req"
    rec = create_request("add", policy_no, d["name"], d, user, staff_no=d["staff_no"],
                         effective_date=effective_date,
                         member_id=(ex["id"] if ex is not None else None))
    return rec, None


def _snapshot(m):
    return {k: nn(m.get(k)) for k in ("name", "staff_no", "card_no", "national_id", "dob", "gender",
                                      "category", "dependency")}


def create_delete_request(member, effective_date, user, details=None):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    if not _open_requests(load("requests"), "delete", member["policy_no"], member_id=member["id"]).empty:
        return None, "err_open_exists"
    rec = create_request("delete", member["policy_no"], member["name"], _snapshot(member), user,
                         member_id=member["id"], staff_no=str_id(member["staff_no"]),
                         effective_date=effective_date, details=details)
    return rec, None


def create_replace_request(member, reason, user, details=None):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    if not _open_requests(load("requests"), "replace", member["policy_no"], member_id=member["id"]).empty:
        return None, "err_open_exists"
    snap = {**_snapshot(member), "reason": reason}
    rec = create_request("replace", member["policy_no"], member["name"], snap, user, member_id=member["id"],
                         staff_no=str_id(member["staff_no"]), effective_date=date.today(),
                         details=details or reason)
    return rec, None


def _payload(req):
    p = req.get("payload")
    return p if isinstance(p, dict) else {}


def _apply_done(req):
    """الأثر على الأعضاء لما الطلب يوصل 'تم التنفيذ' (آمن لو اتنفذ أكتر من مرة)."""
    p, pol = _payload(req), req["policy_no"]
    if req["type"] == "add":
        fields = {k: p.get(k) for k in MEMBER_FIELDS if nn(p.get(k)) is not None}
        fields["name"] = nn(p.get("name")) or req["member_name"]
        ex = find_member(pol, fields.get("staff_no"), fields["name"])
        if ex is not None:
            update("members", ex["id"], {**fields, "status": "active", "termination_date": None})
        else:
            insert("members", {**fields, "policy_no": pol, "status": "active"})
    elif req["type"] == "delete":
        ex = None
        if nn(req.get("member_id")):
            m = load("members")
            hit = m[m["id"] == req["member_id"]]
            ex = hit.iloc[0] if not hit.empty else None
        if ex is None:
            ex = find_member(pol, req.get("staff_no"), req["member_name"])
        if ex is not None:
            update("members", ex["id"], {"status": "terminated",
                                         "termination_date": to_iso(req.get("effective_date")) or date.today().isoformat()})


def change_status(rid, new, user):
    df = load("requests")
    hit = df[df["id"] == rid]
    if hit.empty:
        raise ValueError("request not found")
    req = hit.iloc[0].to_dict()
    old = req["status"]
    if new not in TRANSITIONS.get(old, []):
        raise ValueError("transition")
    if new == "done":
        _apply_done(req)
    update("requests", rid, {"status": new, "updated_at": now_iso()})
    notify("status_changed", msg_status(req, old, new, user))


# ───────────────────────── ملفات الإضافة/الحذف ─────────────────────────
def export_df(rtype, reqs):
    rows = []
    for r in reqs.to_dict("records"):
        p = _payload(r)
        if rtype == "add":
            rows.append({"Name": r["member_name"], "National ID": p.get("national_id"), "DOB": fmt_date(p.get("dob")),
                         "Phone": p.get("phone"), "Staff ID": p.get("staff_no"), "Date": fmt_date(r["effective_date"]),
                         "Policy": r["policy_no"]})
        elif rtype == "delete":
            rows.append({"Name": r["member_name"], "Staff ID": p.get("staff_no"), "Card No": p.get("card_no"),
                         "National ID": p.get("national_id"), "DOB": fmt_date(p.get("dob")), "Policy": r["policy_no"],
                         "Deletion Date": fmt_date(r["effective_date"])})
        else:
            rows.append({"Name": r["member_name"], "Staff ID": p.get("staff_no"), "Card No": p.get("card_no"),
                         "Policy": r["policy_no"], "Reason": p.get("reason"), "Date": fmt_date(r["effective_date"])})
    return pd.DataFrame(rows)


def to_excel_bytes(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return out.getvalue()


def parse_allianz_file(file):
    """يقرا شيت Allianz سواء HTML بامتداد xls أو XLSX أو CSV. يرجّع (DataFrame، رسالة خطأ)."""
    content = file.getvalue() if hasattr(file, "getvalue") else file.read()
    name = (getattr(file, "name", "") or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(content), dtype=str), None
        except Exception:  # noqa: BLE001
            pass
    try:
        text = content.decode("utf-8", errors="ignore")
        if "<table" in text.lower():
            dfs = pd.read_html(io.StringIO(text), converters=defaultdict(lambda: str))
            if dfs:
                df = dfs[0]
                if len(df) and df.iloc[0].astype(str).str.contains("Employee", case=False, na=False).any():
                    df.columns = df.iloc[0]
                    df = df[1:]
                return df.reset_index(drop=True).dropna(how="all"), None
    except Exception:  # noqa: BLE001
        pass
    last = None
    for engine in ("xlrd", "openpyxl", None):
        try:
            kw = {"engine": engine} if engine else {}
            return pd.read_excel(io.BytesIO(content), dtype=str, **kw).dropna(how="all"), None
        except Exception as e:  # noqa: BLE001
            last = e
    return pd.DataFrame(), str(last)
