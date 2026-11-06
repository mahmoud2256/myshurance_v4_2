import hmac
import html
import traceback
from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Myshurance", page_icon="🛡", layout="wide", initial_sidebar_state="expanded")

from PIL import Image  # noqa: E402

import ocr  # noqa: E402
import store as S  # noqa: E402
from i18n import lang, t  # noqa: E402

TEAL_DARK, TEAL, TEAL_ACTIVE = "#07363B", "#0B4F55", "#226068"
SAND, CREAM, BORDER = "#E8C9A0", "#F6F1E8", "#E8DCC8"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PAYLOAD_LABELS = {"name": "c_name", "staff_no": "c_staff", "card_no": "c_card", "national_id": "f_nid",
                  "phone": "f_phone", "dob": "c_dob", "gender": "c_gender", "category": "c_cat",
                  "dependency": "c_dep", "source_start": "c_start", "source_end": "c_end", "reason": "f_reason"}


# ───────────────────────── أدوات واجهة ─────────────────────────
def inject_css():
    css = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea, select { font-family: 'Cairo', sans-serif !important; }
.stApp { background: %CREAM%; %DIR% }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.5rem; max-width: 1250px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, %TEAL%, %DARK%); %DIR% }
[data-testid="stSidebar"] * { color: #EAF1F0; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
.brand { display:flex; align-items:center; gap:12px; padding: 6px 4px 2px 4px; }
.brand .logo { width:46px; height:46px; border-radius:14px; border:1.5px solid rgba(232,201,160,.5);
  background: rgba(255,255,255,.06); display:flex; align-items:center; justify-content:center;
  color:%SAND%; font-weight:800; font-style:italic; font-size:20px; }
.brand .name { font-size:24px; font-weight:800; color:#fff; line-height:1.1; }
.tagline { color:%SAND%; font-style:italic; font-size:14px; padding: 0 4px 10px 4px; opacity:.9 }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 6px; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding: 12px 14px; border-radius: 14px; width:100%; cursor:pointer; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: %ACTIVE%; box-shadow: inset -4px 0 0 %SAND%; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display:none; }
[data-testid="stSidebar"] [role="radiogroup"] label p { font-size: 17px; font-weight:600; }
.hero { background: linear-gradient(135deg, %TEAL% 0%, %ACTIVE% 100%); color:#fff; border-radius: 26px; padding: 26px 30px; margin-bottom: 18px; }
.hero h1 { color:#fff; font-size: 32px; font-weight:800; margin:0 0 8px 0; }
.hero .pill { display:inline-block; background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.35); border-radius: 999px; padding: 8px 16px; font-size: 14px; }
.stat { background:#fff; border:1px solid %BORDER%; border-radius:20px; padding:14px 16px; }
.stat .n { font-size: 30px; font-weight:800; color:%TEAL%; line-height:1.1 }
.stat .l { font-size: 13px; color:#5b6f70 }
.stat.gold { border-color:%SAND%; background: #FBF4E8 }
.pcard { background:#fff; border:1px solid %BORDER%; border-radius:22px; padding:18px; margin-bottom:10px; }
.pcard .top { display:flex; justify-content:space-between; align-items:center; }
.pcard .no { font-weight:800; color:%TEAL%; font-size:18px; }
.pcard .school { font-weight:700; margin:8px 0 2px 0; font-size:17px; }
.pcard .box { background:#FBF4E8; border:1px solid %BORDER%; border-radius:14px; padding:10px 12px; margin:10px 0; font-size:14px; }
.pcard .counts { display:flex; gap:8px; } .pcard .counts div { flex:1; background:%CREAM%; border-radius:12px; padding:8px; text-align:center; font-size:13px; }
.pcard .counts b { display:block; font-size:20px; color:%TEAL%; }
.badge { display:inline-block; padding:3px 12px; border-radius:999px; font-size:12px; font-weight:700; }
.badge.ok { background:#DDF3E6; color:#1B6B3A; } .badge.bad { background:#F8DADA; color:#9A2A2A; }
h2, h3 { color: %TEAL% !important; font-weight:800 !important; }
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button { background: %TEAL%; color:#fff; border:0; border-radius: 12px; padding: .5rem 1.1rem; font-weight:700; }
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover { background: %ACTIVE%; color:#fff; }
.stButton > button:disabled { background:#b9c7c8; color:#fff; }
[data-testid="stSidebar"] .stButton > button { background: transparent; border:1px solid rgba(255,255,255,.22); width:100%; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: %SAND%; }
[data-testid="stForm"] { background:#fff; border:1px solid %BORDER%; border-radius:20px; }
"""
    for k, v in {"%CREAM%": CREAM, "%TEAL%": TEAL, "%DARK%": TEAL_DARK, "%ACTIVE%": TEAL_ACTIVE, "%SAND%": SAND,
                 "%BORDER%": BORDER,
                 "%DIR%": "direction: rtl; text-align: right;" if lang() == "ar" else ""}.items():
        css = css.replace(k, v)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def table(df):
    st.dataframe(df, hide_index=True, width="stretch")


def stat(col, n, label, gold=False):
    col.markdown(f'<div class="stat {"gold" if gold else ""}"><div class="n">{n}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)


def flash(kind, msg):
    st.session_state["_flash"] = (kind, msg)


def show_flash():
    f = st.session_state.pop("_flash", None)
    if f:
        getattr(st, f[0])(f[1])


def user():
    return st.session_state.get("user_name", "")


def can_edit():
    return st.session_state.get("role") == "admin"


def policy_label(no):
    return f"{no} - {S.CLIENTS_MAP.get(no, '')}"


def all_or(label_fn):
    return lambda x: t("all") if x == "*" else label_fn(x)


def member_table(df, reqs):
    df = df.reset_index(drop=True)
    delmap = {}
    if not reqs.empty:
        o = reqs[(reqs["type"] == "delete") & reqs["status"].isin(S.OPEN_STATUSES) & reqs["member_id"].notna()]
        delmap = dict(zip(o["member_id"], o["status"]))
    dash = lambda s: s.fillna("—")  # noqa: E731
    return pd.DataFrame({
        t("c_idx"): range(1, len(df) + 1),
        t("c_name"): df["name"], t("c_staff"): dash(df["staff_no"]), t("c_card"): dash(df["card_no"]),
        t("c_policy"): df["policy_no"], t("c_company"): df["policy_no"].map(lambda p: S.CLIENTS_MAP.get(str(p), "—")),
        t("c_cat"): dash(df["category"]), t("c_dep"): dash(df["dependency"]),
        t("c_dob"): df["dob"].map(S.fmt_date),
        t("c_gender"): df["gender"].map(lambda g: t("g_" + g) if g in ("M", "F") else "—"),
        t("c_start"): df["source_start"].map(S.fmt_date), t("c_end"): df["source_end"].map(S.fmt_date),
        t("c_mstatus"): df["status"].fillna("active").map(lambda s: t("ms_" + s)),
        t("c_delreq"): df["id"].map(lambda i: t("st_" + delmap[i]) if i in delmap else t("no_req")),
    })


def date_or_none(iso):
    iso = S.to_iso(iso)
    return date.fromisoformat(iso) if iso else None


# ───────────────────────── الدخول ─────────────────────────
def login_screen():
    c = st.columns([1, 1.2, 1])[1]
    with c:
        st.markdown(f'<div class="hero" style="text-align:center"><h1>Myshurance</h1>'
                    f'<div class="pill">{t("tagline")}</div></div>', unsafe_allow_html=True)
        pw = {"admin": S.secret("ADMIN_PASSWORD"), "viewer": S.secret("VIEWER_PASSWORD")}
        roles = [r for r, p in pw.items() if p]
        if not roles:
            st.error(t("no_secrets"))
            return
        with st.form("login"):
            role = st.selectbox(t("role"), roles, format_func=t)
            name = st.text_input(t("user_name"))
            typed = st.text_input(t("pw"), type="password")
            if st.form_submit_button(t("login")):
                if hmac.compare_digest(typed.encode(), pw[role].encode()):
                    st.session_state.role, st.session_state.user_name = role, name.strip()
                    st.rerun()
                else:
                    st.error(t("bad_pw"))


# ───────────────────────── الصفحات ─────────────────────────
def page_dash():
    members, reqs = S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    open_n = int(reqs["status"].isin(S.OPEN_STATUSES).sum())
    drafts = int((reqs["status"] == "draft").sum())
    st.markdown(f'<div class="hero"><h1>{t("welcome")}</h1><div class="pill">{t("welcome_sub")}</div></div>',
                unsafe_allow_html=True)
    c = st.columns(4)
    stat(c[0], int((members["status"] == "active").sum()), t("m_active"))
    stat(c[1], open_n, t("m_open"), gold=True)
    stat(c[2], int((reqs["status"] == "done").sum()), t("m_done"))
    stat(c[3], int((members["status"] == "terminated").sum()), t("m_term"))
    if drafts:
        st.info(t("drafts_alert").format(n=drafts))
    a, b = st.columns(2)
    with a:
        st.subheader(t("recent"))
        if reqs.empty:
            st.info(t("nothing"))
        else:
            r = reqs.head(8)
            table(pd.DataFrame({t("rq_ref"): r["ref_no"], t("rq_member"): r["member_name"],
                                t("rq_status"): r["status"].map(lambda s: t("st_" + s))}))
    with b:
        st.subheader(t("per_policy"))
        rows = []
        for no, school in S.CLIENTS_MAP.items():
            m = members[members["policy_no"].astype(str) == no]
            rows.append({t("c_policy"): no, t("c_company"): school, t("n_active"): int((m["status"] == "active").sum()),
                         t("n_term"): int((m["status"] == "terminated").sum())})
        table(pd.DataFrame(rows))


def page_policies():
    st.header(t("policies"))
    pol, members, reqs = S.policies_df(), S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    cols = st.columns(2)
    for i, p in enumerate(pol.to_dict("records")):
        no = p["policy_no"]
        m = members[members["policy_no"].astype(str) == no]
        n_open = int(((reqs["policy_no"].astype(str) == no) & reqs["status"].isin(S.OPEN_STATUSES)).sum())
        expired = bool(p["end_date"]) and p["end_date"] < date.today().isoformat()
        badge = f'<span class="badge {"bad" if expired else "ok"}">{t("pol_expired" if expired else "pol_active")}</span>'
        with cols[i % 2]:
            st.markdown(f"""<div class="pcard">
<div class="top"><span class="no">#{no}</span>{badge}</div>
<div class="school">{html.escape(p["school"] or "—")}</div>
<div style="font-size:13px;color:#5b6f70">{t("pol_provider")}: Allianz</div>
<div class="box">{t("pol_start")}: <b>{S.fmt_date(p["start_date"])}</b> &nbsp;|&nbsp; {t("pol_end")}: <b>{S.fmt_date(p["end_date"])}</b></div>
<div class="counts"><div><b>{int((m["status"] == "active").sum())}</b>{t("n_active")}</div>
<div><b>{int((m["status"] == "terminated").sum())}</b>{t("n_term")}</div>
<div><b>{n_open}</b>{t("pol_open")}</div></div></div>""", unsafe_allow_html=True)
            if can_edit():
                with st.expander(t("pol_edit")):
                    with st.form(f"pol_{no}"):
                        s = st.date_input(t("pol_start"), value=date_or_none(p["start_date"]) or date.today(),
                                          min_value=date(2020, 1, 1), max_value=date(2100, 1, 1), key=f"ps_{no}")
                        e = st.date_input(t("pol_end"), value=date_or_none(p["end_date"]) or date.today(),
                                          min_value=date(2020, 1, 1), max_value=date(2100, 1, 1), key=f"pe_{no}")
                        if st.form_submit_button(t("save")):
                            S.save_policy_dates(no, s, e)
                            S.notify_policy(no, s, e, user())
                            flash("success", t("saved"))
                            st.rerun()


def show_preview(file, caption):
    try:
        st.image(file, caption=caption, width="stretch")
    except Exception:  # noqa: BLE001
        st.warning(t("scan_img_fail"))


def add_member_tab():
    """إضافة عضو بالمسح الذكي: ارفع البطاقة (والكارنيه) ← قراءة ← راجع ← إنشاء الطلب."""
    st.caption(t("scan_privacy") if ocr.claude_available() else t("scan_no_ai"))
    ss = st.session_state
    ss.setdefault("up_ver", 0)
    ss.setdefault("scan_ver", 0)
    pol = st.selectbox(t("c_policy"), list(S.CLIENTS_MAP), format_func=policy_label, key="add_pol")
    c1, c2 = st.columns(2)
    types = ["jpg", "jpeg", "png", "webp"]
    nid_file = c1.file_uploader(t("scan_nid"), type=types, key=f"up_nid_{ss.up_ver}")
    card_file = c2.file_uploader(t("scan_card"), type=types, key=f"up_card_{ss.up_ver}")
    if card_file and not nid_file:
        st.info(t("scan_need_nid"))
    if (nid_file or card_file) and st.button(t("scan_read"), key=f"scan_btn_{ss.up_ver}"):
        with st.spinner(t("scan_reading")):
            ss["add_scan"] = ocr.read_all(nid_file, card_file)
        ss["scan_ver"] += 1
        st.rerun()
    res = ss.get("add_scan")
    d = res["data"] if res else {}
    if res:
        if res["engine"] == "claude":
            st.success(t("scan_engine_claude"))
        elif res["engine"] == "tesseract":
            st.warning(t("scan_engine_ocr"))
        for w in res["warnings"]:
            st.warning(t(w))
        for e in res["errors"]:
            st.error(t("scan_error").format(e=e))
        if res["uncertain"]:
            st.warning(t("scan_uncertain").format(fields=", ".join(t(k) for k in res["uncertain"])))
        if not d:
            st.error(t("scan_nothing"))
    fv = ss.scan_ver
    left, right = st.columns([1, 1.6], gap="large")
    with left:  # صور المسح جنب البيانات عشان الموظف يطابقها بعينه
        if nid_file:
            show_preview(nid_file, t("scan_nid"))
        if card_file:
            show_preview(card_file, t("scan_card"))
        if not (nid_file or card_file):
            st.info(t("scan_upload_hint"))
    with right, st.form(f"add_member_{fv}"):
        r1 = st.columns(2)
        name = r1[0].text_input(t("c_name"), value=d.get("name", ""), key=f"a_name_{fv}")
        nid = r1[1].text_input(t("f_nid"), value=d.get("national_id", ""), key=f"a_nid_{fv}")
        r2 = st.columns(2)
        dob = r2[0].date_input(t("c_dob"), value=date_or_none(d.get("dob")), min_value=date(1930, 1, 1),
                               max_value=date.today(), key=f"a_dob_{fv}")
        gopts = ["", "M", "F"]
        gender = r2[1].selectbox(t("c_gender"), gopts, index=gopts.index(d.get("gender") or ""),
                                 format_func=lambda g: t("g_" + g) if g else "—", key=f"a_g_{fv}")
        r3 = st.columns(2)
        card = r3[0].text_input(t("c_card"), value=d.get("card_no", ""), key=f"a_card_{fv}")
        copts = ["", "A", "B", "C", "D"]
        categ = r3[1].selectbox(t("c_cat"), copts, index=copts.index(d.get("category") or ""),
                                format_func=lambda g: g or "—", key=f"a_cat_{fv}")
        r4 = st.columns(2)
        end = r4[0].date_input(t("c_end"), value=date_or_none(d.get("source_end")), min_value=date(2020, 1, 1),
                               max_value=date(2100, 1, 1), key=f"a_end_{fv}")
        dep = r4[1].selectbox(t("c_dep"), S.DEPENDENCIES, key=f"a_dep_{fv}")
        r5 = st.columns(3)
        staff = r5[0].text_input(t("c_staff"), key=f"a_staff_{fv}")
        phone = r5[1].text_input(t("f_phone"), key=f"a_phone_{fv}")
        eff = r5[2].date_input(t("f_eff"), value=date.today(), key=f"a_eff_{fv}")
        if st.form_submit_button(t("submit_add")):
            if not (staff.strip() and phone.strip()):
                st.error(t("err_required"))
            else:
                rec, e = S.create_add_request(pol, {"name": name, "staff_no": staff, "national_id": nid,
                                                    "phone": phone, "card_no": card, "dob": dob, "gender": gender,
                                                    "category": categ, "source_end": end, "dependency": dep}, eff, user())
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    ss.pop("add_scan", None)
                    ss["up_ver"] += 1
                    ss["scan_ver"] += 1
                    st.rerun()


def page_members():
    st.header(t("members"))
    members, reqs = S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    f = st.columns([1.4, 1, 1, 1.4])
    policy = f[0].selectbox(t("flt_policy"), ["*"] + list(S.CLIENTS_MAP), format_func=all_or(policy_label))
    cat = f[1].selectbox(t("flt_cat"), ["*", "A", "B", "C", "D"], format_func=all_or(str))
    stt = f[2].selectbox(t("flt_status"), ["*", "active", "terminated"], format_func=all_or(lambda s: t("ms_" + s)))
    q = f[3].text_input(t("search"))
    view = members
    if policy != "*":
        view = view[view["policy_no"].astype(str) == policy]
    if cat != "*":
        view = view[view["category"] == cat]
    if stt != "*":
        view = view[view["status"] == stt]
    if q:
        hay = view[["name", "staff_no", "card_no"]].astype(str).agg(" ".join, axis=1)
        view = view[hay.str.contains(q, case=False, na=False, regex=False)]
    c = st.columns(6)
    stat(c[0], len(view), t("n_total"))
    stat(c[1], int((view["status"] == "active").sum()), t("n_active"))
    stat(c[2], int((view["status"] == "terminated").sum()), t("n_term"), gold=True)
    for col, k in zip(c[3:], "BCD"):
        stat(col, int((view["category"] == k).sum()), f"{t('f_tier')} {k}")
    shown = member_table(view, reqs)
    table(shown)
    st.download_button(t("export_view"), S.to_excel_bytes(shown), "members.xlsx", mime=XLSX)
    if not can_edit():
        st.caption(t("readonly"))
        return
    tab_add, tab_act = st.tabs([t("tab_add"), t("tab_act")])
    with tab_add:
        add_member_tab()
    with tab_act:
        pool = view[view["status"] == "active"].head(300)
        if pool.empty:
            st.info(t("nothing"))
            return
        ids = pool["id"].tolist()
        lab = dict(zip(pool["id"], pool["name"].astype(str) + " | " + pool["staff_no"].fillna("—").astype(str)))
        mid = st.selectbox(t("choose_member"), ids, format_func=lab.get)
        m = pool[pool["id"] == mid].iloc[0]
        action = st.radio(t("action"), ["delete", "replace"], format_func=lambda a: t("act_" + a), horizontal=True)
        details = st.text_input(t("f_details"), key=f"det_{mid}_{action}")
        if action == "delete":
            eff = st.date_input(t("del_date"), value=date.today(), min_value=date.today() - timedelta(days=30),
                                max_value=date.today(), key=f"deld_{mid}")
            damaged = st.file_uploader(t("damaged_img"), type=["jpg", "jpeg", "png"], key=f"dmg_{mid}")
            ok = st.checkbox(t("confirm_ck"), key=f"cnf_{mid}")
            if st.button(t("submit_req"), disabled=not (damaged and ok), key=f"btn_del_{mid}"):
                rec, e = S.create_delete_request(m, eff, user(), details or None)
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    st.rerun()
        else:
            reason = st.selectbox(t("f_reason"), ["lost", "damaged"], format_func=lambda r: t("reason_" + r))
            if st.button(t("submit_req"), key=f"btn_rep_{mid}"):
                rec, e = S.create_replace_request(m, reason, user(), details or None)
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    st.rerun()


def page_requests():
    st.header(t("requests"))
    reqs = S.load("requests")
    counts = reqs["status"].value_counts()
    sel = st.radio(t("flt_status"), ["*"] + S.REQ_STATUSES, horizontal=True, key="req_filter",
                   label_visibility="collapsed",
                   format_func=lambda s: f"{t('all') if s == '*' else t('st_' + s)} "
                                         f"({len(reqs) if s == '*' else int(counts.get(s, 0))})")
    f = st.columns(3)
    typ = f[0].selectbox(t("rq_type"), ["*"] + S.REQ_TYPES, format_func=all_or(lambda x: t("ty_" + x)))
    pol = f[1].selectbox(t("flt_policy"), ["*"] + list(S.CLIENTS_MAP), format_func=all_or(policy_label))
    q = f[2].text_input(t("search"))
    v = reqs
    if sel != "*":
        v = v[v["status"] == sel]
    if typ != "*":
        v = v[v["type"] == typ]
    if pol != "*":
        v = v[v["policy_no"].astype(str) == pol]
    if q:
        hay = v[["ref_no", "member_name", "staff_no"]].astype(str).agg(" ".join, axis=1)
        v = v[hay.str.contains(q, case=False, na=False, regex=False)]
    if v.empty:
        st.info(t("nothing"))
        return
    table(pd.DataFrame({
        t("rq_ref"): v["ref_no"], t("rq_type"): v["type"].map(lambda x: t("ty_" + x)), t("rq_member"): v["member_name"],
        t("rq_staff"): v["staff_no"].fillna("—"), t("rq_policy"): v["policy_no"],
        t("rq_date"): v["effective_date"].map(S.fmt_date), t("rq_status"): v["status"].map(lambda s: t("st_" + s)),
        t("rq_created"): v["created_at"].map(S.fmt_ts), t("rq_by"): v["created_by"].fillna("—")}))
    st.subheader(t("req_details"))
    lab = dict(zip(v["id"], v["ref_no"].astype(str) + " | " + v["member_name"].astype(str)))
    rid = st.selectbox(t("choose_req"), list(lab), format_func=lab.get)
    r = v[v["id"] == rid].iloc[0].to_dict()
    st.markdown(f"**{r['ref_no']}** — {t('ty_' + r['type'])} — {t('st_' + r['status'])}")
    p = r["payload"] if isinstance(r["payload"], dict) else {}
    shown = {t(PAYLOAD_LABELS[k]): (S.fmt_date(val) if k in ("dob", "source_start", "source_end") else
                                    (t("g_" + val) if k == "gender" else (t("reason_" + val) if k == "reason" else val)))
             for k, val in p.items() if k in PAYLOAD_LABELS and S.nn(val) is not None}
    if shown:
        table(pd.DataFrame([shown]))
    if S.nn(r.get("details")):
        st.caption(f"{t('f_details')}: {r['details']}")
    nxt = S.TRANSITIONS.get(r["status"], [])
    if not can_edit():
        st.caption(t("readonly"))
        return
    if not nxt:
        st.caption(t("no_actions"))
        return
    if "done" in nxt and r["type"] in ("add", "delete"):
        st.caption(t("done_note_" + r["type"]))
    cols = st.columns(len(nxt))
    for col, s in zip(cols, nxt):
        if col.button(f"{t('move_to')}: {t('st_' + s)}", key=f"to_{rid}_{s}"):
            try:
                S.change_status(rid, s, user())
                flash("success", t("status_changed"))
            except Exception as e:  # noqa: BLE001
                flash("error", f"{t('err_transition')} ({e})")
            st.rerun()


def page_import():
    st.header(t("import"))
    tab1, tab2 = st.tabs([t("tab_masters"), t("tab_files")])
    with tab1:
        pol = st.selectbox(t("c_policy"), list(S.CLIENTS_MAP), format_func=policy_label, key="mp")
        members = S.load("members")
        cur = members[members["policy_no"].astype(str) == pol].copy()
        if not cur.empty:
            cur["status"] = cur["status"].fillna("active")
            st.download_button(t("imp_dl_master"), S.to_excel_bytes(member_table(cur, S.load("requests"))),
                               f"MASTER_{pol}_{date.today()}.xlsx", mime=XLSX)
        if not can_edit():
            st.caption(t("readonly"))
        else:
            up = st.file_uploader(t("imp_up"), type=["xlsx", "xls", "xlsm", "csv"], key="master_up")
            if up:
                df, err = S.parse_allianz_file(up)
                if err or df.empty:
                    st.error(f"{t('imp_fail')} {err or ''}")
                else:
                    det = S.detect_columns(df)
                    st.caption(t("imp_preview"))
                    table(df.head(8).astype(str))
                    st.subheader(t("imp_map"))
                    opts = [None] + list(df.columns)
                    mapping, cols = {}, st.columns(4)
                    for i, fld in enumerate(S.ALIASES):
                        mapping[fld] = cols[i % 4].selectbox(
                            t(PAYLOAD_LABELS[fld]), opts, index=opts.index(det[fld]) if fld in det else 0,
                            format_func=lambda c: t("imp_skip") if c is None else str(c), key=f"map_{fld}_{up.name}")
                    if not mapping["name"]:
                        st.error(t("err_need_name"))
                    else:
                        rows = S.rows_from_df(df, mapping)
                        keys = {r["staff_no"] for r in rows if r["staff_no"]}
                        absent = int((cur["staff_no"].map(S.str_id).map(lambda x: x not in keys)).sum()) if not cur.empty else 0
                        st.write(t("imp_count").format(n=len(rows)))
                        if absent:
                            st.info(t("imp_missing").format(n=absent))
                        if st.button(t("imp_go"), key="imp_go"):
                            new, upd, same = S.upsert_members(pol, rows)
                            if new or upd:
                                S.notify_import(pol, new, upd, same, user())
                            flash("success", t("imp_result").format(new=new, upd=upd, same=same))
                            st.rerun()
    with tab2:
        c = st.columns(2)
        pol = c[0].selectbox(t("c_policy"), list(S.CLIENTS_MAP), format_func=policy_label, key="fp")
        rtype = c[1].radio(t("rq_type"), S.REQ_TYPES, format_func=lambda x: t("ty_" + x), horizontal=True, key="ft")
        reqs = S.load("requests")
        df = reqs[(reqs["type"] == rtype) & (reqs["policy_no"].astype(str) == pol) & (reqs["status"] == "draft")]
        if df.empty:
            st.info(t("files_none"))
            return
        lab = dict(zip(df["id"], df["ref_no"].astype(str) + " | " + df["member_name"].astype(str)))
        ids = st.multiselect(t("files_pick"), list(lab), default=list(lab), format_func=lab.get)
        sel = df[df["id"].isin(ids)]
        exp = S.export_df(rtype, sel)
        table(exp)
        c1, c2 = st.columns(2)
        c1.download_button(t("files_dl"), S.to_excel_bytes(exp), f"{rtype.upper()}_{pol}_{date.today()}.xlsx",
                           mime=XLSX, disabled=sel.empty)
        if can_edit() and c2.button(t("files_mark_sent"), disabled=sel.empty):
            for i in ids:
                S.change_status(i, "sent", user())
            flash("success", t("files_marked").format(n=len(ids)))
            st.rerun()


def page_settings():
    st.header(t("settings"))
    st.write("**Providers:** " + ", ".join(S.PROVIDERS))
    table(pd.DataFrame({t("c_policy"): list(S.CLIENTS_MAP), t("c_company"): list(S.CLIENTS_MAP.values())}))
    st.subheader(t("set_scan"))
    st.success(t("scan_ai_on")) if ocr.claude_available() else st.warning(t("scan_no_ai"))
    st.subheader(t("set_notif"))
    if S.SB:
        st.success(t("sb_ok"))
    else:
        st.warning(t("sb_err").format(e=S.SB_ERR) if S.SB_ERR else t("notif_demo_warn"))
    n = S.load("notifications")
    c = st.columns(3)
    for col, s in zip(c, ["pending", "sent", "failed"]):
        stat(col, int((n["status"] == s).sum()), t("notif_" + s))
    if can_edit() and st.button(t("notif_test")):
        S.notify("test", f"✅ رسالة تجربة من Myshurance\nبواسطة: {user() or '—'}\nالوقت: {S._t()}")
        flash("success", t("notif_test_sent"))
        st.rerun()
    if not n.empty:
        table(pd.DataFrame({t("rq_created"): n.head(20)["created_at"].map(S.fmt_ts),
                            t("rq_status"): n.head(20)["status"],
                            "message": n.head(20)["message"].astype(str).str.split("\n").str[0]}))


# ───────────────────────── التشغيل ─────────────────────────
def main():
    with st.sidebar:
        st.radio("lang", ["العربية", "English"], horizontal=True, key="lang_label", label_visibility="collapsed")
    inject_css()
    if "role" not in st.session_state:
        login_screen()
        return
    try:
        open_n = int(S.load("requests")["status"].isin(S.OPEN_STATUSES).sum())
    except Exception:  # noqa: BLE001
        open_n = 0
    pages = ["dash", "members", "requests", "policies", "import", "settings"]
    icons = {"dash": "▦", "members": "👥", "requests": "📋", "policies": "🛡️", "import": "📄", "settings": "⚙️"}
    with st.sidebar:
        st.markdown('<div class="brand"><div class="logo">sM</div><div class="name">Myshurance</div></div>'
                    f'<div class="tagline">{t("tagline")}</div>', unsafe_allow_html=True)
        st.divider()
        page = st.radio("nav", pages, label_visibility="collapsed", key="page",
                        format_func=lambda k: f"{icons[k]}  {t(k)}" + (f"  ({open_n})" if k == "requests" and open_n else ""))
        st.divider()
        if st.button(t("logout")):
            for k in ("role", "user_name"):
                st.session_state.pop(k, None)
            st.rerun()
        st.caption(f"{user() or '—'} · {t(st.session_state.role)}")
        if not S.SB:
            st.caption(t("demo"))
    show_flash()
    runner = {"dash": page_dash, "members": page_members, "requests": page_requests, "policies": page_policies,
              "import": page_import, "settings": page_settings}[page]
    try:
        runner()
    except Exception as e:  # noqa: BLE001
        if e.__class__.__module__.startswith("streamlit.runtime.scriptrunner"):
            raise  # st.rerun / st.stop لازم يعدّوا
        st.error(t("page_error"))
        with st.expander(t("details")):
            st.code(traceback.format_exc())


main()
