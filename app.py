#!/usr/bin/env python3
"""
Balance Group Messenger
Open-source tool for grouping members by balance ranges and sending
personalized SMS / WhatsApp messages via your own API or WhatsApp Web.
"""

import os
import json
import re
import csv
import io
from datetime import datetime
from urllib.parse import quote
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session, send_file, Response
)
import pandas as pd
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "balance-group-messenger-dev-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "sms_config.json")
DATA_FILE = os.path.join(os.path.dirname(__file__), "session_data.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_sms_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_url": "",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body_template": '{"to": "{{phone}}", "message": "{{message}}"}',
        "phone_param": "to",
        "message_param": "message",
        "success_codes": [200, 201, 202],
        "rate_limit_ms": 200,
        "enabled": False,
    }


def save_sms_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_data():
    """Load in-memory-like data from session or temp file for simplicity."""
    if "members_df" in session and session.get("members_raw"):
        try:
            df = pd.read_json(session["members_raw"], orient="split")
            return df
        except Exception:
            pass
    return None


def set_data(df: pd.DataFrame):
    session["members_raw"] = df.to_json(orient="split")
    session["columns"] = list(df.columns)
    session.modified = True


def clean_phone(phone):
    """Normalize phone number to digits only, keep leading + if present."""
    if pd.isna(phone):
        return ""
    s = str(phone).strip()
    # Keep + and digits
    s = re.sub(r"[^\d+]", "", s)
    return s


def render_template_msg(template: str, row: dict) -> str:
    """Replace {{col}} placeholders with values from row."""
    def replacer(match):
        key = match.group(1).strip()
        val = row.get(key, "")
        if pd.isna(val):
            return ""
        return str(val)
    return re.sub(r"\{\{\s*([^}]+)\s*\}\}", replacer, template)


def suggest_balance_groups(df, balance_col, n_groups=3):
    """Suggest roughly equal-count groups using quantiles."""
    if balance_col not in df.columns:
        return []
    series = pd.to_numeric(df[balance_col], errors="coerce").dropna()
    if series.empty:
        return []
    quantiles = [i / n_groups for i in range(n_groups + 1)]
    cuts = series.quantile(quantiles).tolist()
    # Ensure unique and sorted
    cuts = sorted(set(cuts))
    while len(cuts) < n_groups + 1:
        cuts.append(cuts[-1] + 1)
    groups = []
    for i in range(n_groups):
        gmin = cuts[i]
        gmax = cuts[i + 1] if i < n_groups - 1 else series.max()
        # slight overlap fix
        if i > 0:
            gmin = cuts[i]
        groups.append({
            "name": f"Group {i+1}",
            "min": float(gmin),
            "max": float(gmax) if i < n_groups - 1 else float(series.max()),
            "count": int(((series >= gmin) & (series <= gmax)).sum()) if i == n_groups-1 else int(((series >= gmin) & (series < gmax)).sum())
        })
    # Fix last max
    groups[-1]["max"] = float(series.max())
    return groups


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    df = get_data()
    sms_cfg = load_sms_config()
    return render_template(
        "index.html",
        has_data=df is not None,
        columns=session.get("columns", []),
        sms_enabled=sms_cfg.get("enabled", False),
        phone_col=session.get("phone_col"),
        balance_col=session.get("balance_col"),
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("No file selected", "danger")
        return redirect(url_for("index"))
    file = request.files["file"]
    if file.filename == "":
        flash("No file selected", "danger")
        return redirect(url_for("index"))

    try:
        filename = secure_filename(file.filename)
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(file)
        elif filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(file)
        else:
            flash("Only CSV or Excel files are supported", "danger")
            return redirect(url_for("index"))

        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        if df.empty:
            flash("File is empty", "danger")
            return redirect(url_for("index"))

        set_data(df)
        session.pop("phone_col", None)
        session.pop("balance_col", None)
        session.pop("groups", None)
        flash(f"Successfully loaded {len(df)} rows with columns: {', '.join(df.columns)}", "success")
        return redirect(url_for("configure"))
    except Exception as e:
        flash(f"Error reading file: {str(e)}", "danger")
        return redirect(url_for("index"))


@app.route("/configure", methods=["GET", "POST"])
def configure():
    df = get_data()
    if df is None:
        flash("Please upload a CSV first", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        phone_col = request.form.get("phone_col")
        balance_col = request.form.get("balance_col")
        if not phone_col or phone_col not in df.columns:
            flash("Please select a valid phone/mobile column", "danger")
            return redirect(url_for("configure"))
        session["phone_col"] = phone_col
        if balance_col and balance_col in df.columns:
            session["balance_col"] = balance_col
            # auto suggest groups
            suggestions = suggest_balance_groups(df, balance_col)
            session["group_suggestions"] = suggestions
        else:
            session["balance_col"] = None
            session["group_suggestions"] = []
        flash("Columns mapped successfully", "success")
        return redirect(url_for("groups"))

    # Detect likely columns
    phone_candidates = [c for c in df.columns if any(k in c.lower() for k in ["phone", "mobile", "cell", "whatsapp", "contact", "number"])]
    balance_candidates = [c for c in df.columns if any(k in c.lower() for k in ["balance", "closing", "amount", "due", "outstanding", "credit"])]
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    return render_template(
        "configure.html",
        columns=list(df.columns),
        phone_candidates=phone_candidates or list(df.columns),
        balance_candidates=balance_candidates or numeric_cols,
        sample=df.head(5).to_dict(orient="records"),
        total_rows=len(df),
    )


@app.route("/groups", methods=["GET", "POST"])
def groups():
    df = get_data()
    if df is None:
        flash("Please upload data first", "warning")
        return redirect(url_for("index"))

    phone_col = session.get("phone_col")
    balance_col = session.get("balance_col")
    if not phone_col:
        flash("Please map columns first", "warning")
        return redirect(url_for("configure"))

    if request.method == "POST":
        # Save custom groups
        groups = []
        for i in range(1, 6):  # up to 5 groups
            name = request.form.get(f"name_{i}", "").strip()
            min_v = request.form.get(f"min_{i}", "").strip()
            max_v = request.form.get(f"max_{i}", "").strip()
            if name and min_v != "" and max_v != "":
                try:
                    groups.append({
                        "id": i,
                        "name": name,
                        "min": float(min_v),
                        "max": float(max_v),
                    })
                except ValueError:
                    continue
        if not groups:
            flash("Please define at least one group with min/max", "danger")
            return redirect(url_for("groups"))
        session["groups"] = groups
        flash(f"Saved {len(groups)} groups", "success")
        return redirect(url_for("members"))

    suggestions = session.get("group_suggestions", [])
    data_max = None
    data_min = None
    if balance_col and balance_col in df.columns:
        series = pd.to_numeric(df[balance_col], errors="coerce")
        data_min = float(series.min()) if not series.isna().all() else 0
        data_max = float(series.max()) if not series.isna().all() else 100000

    return render_template(
        "groups.html",
        balance_col=balance_col,
        suggestions=suggestions,
        data_min=data_min,
        data_max=data_max,
        existing=session.get("groups", []),
    )


@app.route("/members")
def members():
    df = get_data()
    if df is None:
        flash("Please upload data first", "warning")
        return redirect(url_for("index"))

    phone_col = session.get("phone_col")
    balance_col = session.get("balance_col")
    groups_def = session.get("groups", [])

    # Assign group
    members = []
    for idx, row in df.iterrows():
        m = row.to_dict()
        m["_idx"] = int(idx)
        m["_phone"] = clean_phone(row.get(phone_col, ""))
        bal = None
        if balance_col:
            try:
                bal = float(row.get(balance_col))
            except (TypeError, ValueError):
                bal = None
        m["_balance"] = bal
        assigned = "Ungrouped"
        for g in groups_def:
            if bal is not None and g["min"] <= bal <= g["max"]:
                assigned = g["name"]
                break
        m["_group"] = assigned
        members.append(m)

    # Summary counts
    from collections import Counter
    counts = Counter(m["_group"] for m in members)

    return render_template(
        "members.html",
        members=members,
        groups=groups_def,
        counts=dict(counts),
        phone_col=phone_col,
        balance_col=balance_col,
        columns=session.get("columns", []),
    )


@app.route("/messages", methods=["GET", "POST"])
def messages():
    df = get_data()
    if df is None:
        flash("Please upload data first", "warning")
        return redirect(url_for("index"))

    phone_col = session.get("phone_col")
    groups_def = session.get("groups", [])
    columns = session.get("columns", [])

    if request.method == "POST":
        action = request.form.get("action")
        template = request.form.get("template", "").strip()
        target = request.form.get("target", "all")  # all / group_name / selected
        selected_idxs = request.form.getlist("selected")

        if not template:
            flash("Message template is required", "danger")
            return redirect(url_for("messages"))

        # Build recipient list
        recipients = []
        for idx, row in df.iterrows():
            if target == "selected" and str(idx) not in selected_idxs:
                continue
            if target not in ("all", "selected"):
                # specific group
                bal = None
                if session.get("balance_col"):
                    try:
                        bal = float(row.get(session["balance_col"]))
                    except Exception:
                        pass
                match = False
                for g in groups_def:
                    if g["name"] == target and bal is not None and g["min"] <= bal <= g["max"]:
                        match = True
                        break
                if not match:
                    continue

            phone = clean_phone(row.get(phone_col, ""))
            if not phone:
                continue
            msg = render_template_msg(template, row.to_dict())
            recipients.append({
                "idx": int(idx),
                "phone": phone,
                "message": msg,
                "name": str(row.get(columns[0], "")) if columns else "",
                "row": row.to_dict(),
            })

        session["pending_recipients"] = recipients
        session["last_template"] = template
        flash(f"Prepared {len(recipients)} messages. Review and send below.", "info")
        return redirect(url_for("send"))

    # GET
    sample_row = df.iloc[0].to_dict() if len(df) else {}
    return render_template(
        "messages.html",
        columns=columns,
        groups=groups_def,
        sample_row=sample_row,
        last_template=session.get("last_template", "Hello {{Name}}, your closing balance is {{Balance}}. Please contact us."),
    )


@app.route("/send", methods=["GET", "POST"])
def send():
    recipients = session.get("pending_recipients", [])
    sms_cfg = load_sms_config()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "sms":
            if not sms_cfg.get("enabled") or not sms_cfg.get("api_url"):
                flash("SMS API is not configured. Go to Settings.", "warning")
                return redirect(url_for("settings"))
            results = []
            for r in recipients:
                try:
                    body_str = sms_cfg["body_template"]
                    body_str = body_str.replace("{{phone}}", r["phone"]).replace("{{message}}", r["message"])
                    # also allow other simple replacements
                    headers = sms_cfg.get("headers", {})
                    method = sms_cfg.get("method", "POST").upper()
                    if method == "POST":
                        # try json first
                        try:
                            payload = json.loads(body_str)
                            resp = requests.post(sms_cfg["api_url"], json=payload, headers=headers, timeout=15)
                        except json.JSONDecodeError:
                            resp = requests.post(sms_cfg["api_url"], data=body_str, headers=headers, timeout=15)
                    else:
                        resp = requests.request(method, sms_cfg["api_url"], data=body_str, headers=headers, timeout=15)
                    ok = resp.status_code in sms_cfg.get("success_codes", [200, 201, 202])
                    results.append({"phone": r["phone"], "ok": ok, "status": resp.status_code, "detail": resp.text[:200]})
                except Exception as e:
                    results.append({"phone": r["phone"], "ok": False, "status": 0, "detail": str(e)})
            session["send_results"] = results
            success = sum(1 for x in results if x["ok"])
            flash(f"SMS send finished: {success}/{len(results)} succeeded", "success" if success else "warning")
            return redirect(url_for("send"))

        elif action == "whatsapp_links":
            # Just prepare links – frontend will open them
            links = []
            for r in recipients:
                text = quote(r["message"])
                # assume Pakistan +92 if starts with 03
                phone = r["phone"]
                if phone.startswith("03") and len(phone) == 11:
                    phone = "92" + phone[1:]
                elif phone.startswith("+"):
                    phone = phone[1:]
                url = f"https://wa.me/{phone}?text={text}"
                links.append({"phone": r["phone"], "url": url, "name": r.get("name", "")})
            session["wa_links"] = links
            flash(f"Generated {len(links)} WhatsApp links. Click to open in WhatsApp Web / App.", "info")
            return redirect(url_for("send"))

    return render_template(
        "send.html",
        recipients=recipients,
        sms_enabled=sms_cfg.get("enabled", False),
        results=session.get("send_results"),
        wa_links=session.get("wa_links"),
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    cfg = load_sms_config()
    if request.method == "POST":
        cfg["api_url"] = request.form.get("api_url", "").strip()
        cfg["method"] = request.form.get("method", "POST")
        cfg["body_template"] = request.form.get("body_template", "").strip()
        cfg["enabled"] = request.form.get("enabled") == "on"
        try:
            cfg["headers"] = json.loads(request.form.get("headers", "{}"))
        except Exception:
            cfg["headers"] = {"Content-Type": "application/json"}
        try:
            cfg["success_codes"] = [int(x) for x in request.form.get("success_codes", "200,201,202").split(",") if x.strip()]
        except Exception:
            cfg["success_codes"] = [200, 201, 202]
        save_sms_config(cfg)
        flash("SMS configuration saved", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", cfg=cfg)


@app.route("/api/preview_message", methods=["POST"])
def api_preview():
    data = request.get_json() or {}
    template = data.get("template", "")
    df = get_data()
    if df is None or df.empty:
        return jsonify({"preview": ""})
    row = df.iloc[0].to_dict()
    return jsonify({"preview": render_template_msg(template, row)})


@app.route("/export/<group_name>")
def export_group(group_name):
    df = get_data()
    if df is None:
        return "No data", 400
    balance_col = session.get("balance_col")
    groups_def = session.get("groups", [])
    g = next((x for x in groups_def if x["name"] == group_name), None)
    if not g or not balance_col:
        # export all
        out = df
    else:
        series = pd.to_numeric(df[balance_col], errors="coerce")
        mask = (series >= g["min"]) & (series <= g["max"])
        out = df[mask]
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={group_name.replace(' ', '_')}.csv"}
    )


@app.route("/clear")
def clear_data():
    for k in list(session.keys()):
        session.pop(k, None)
    flash("Session data cleared", "info")
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║         Balance Group Messenger is running               ║
    ║         Open http://127.0.0.1:{port} in your browser       ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=debug)
