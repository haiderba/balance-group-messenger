# Balance Group Messenger

**Open-source, self-hosted tool** to upload member CSVs (with closing balances & mobile numbers), split members into custom balance-based groups, create personalized messages, and send them via **your own SMS API** or **WhatsApp Web** links.

Perfect for cooperatives, officer messes, micro-finance groups, societies, or any organization that needs to message members differently according to their account balance.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Self-hosted](https://img.shields.io/badge/Self--hosted-Yes-success)

---

## Features

- **CSV / Excel upload** – any columns you want
- **Column mapping** – automatically suggests phone & balance columns
- **Custom balance groups** – define min/max for up to 5 groups (e.g. Low / Medium / High)
- **Smart suggestions** – auto-generates roughly equal-sized groups using quantiles
- **Personalized message templates** – use `{{AnyColumn}}` placeholders
- **Group or All targeting** – send different messages to different balance tiers
- **Your own SMS API** – fully configurable HTTP endpoint (Twilio, local gateways, custom services…)
- **WhatsApp Web integration** – one-click `wa.me` links with pre-filled message (opens in same browser / new tab)
- **Export any group** as CSV
- **100% local & open source** – no cloud dependency, data stays on your machine
- **Simple & beautiful UI** – Bootstrap 5, works on desktop & mobile

> **Note on WhatsApp availability check**  
> True real-time “is this number on WhatsApp?” requires either the official WhatsApp Business API or unofficial libraries (e.g. whatsapp-web.js) that need QR login. This tool deliberately stays simple and pure-Python: it generates ready-to-use WhatsApp chat links so you can open them directly in WhatsApp Web / the app. You can always verify presence manually.

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/haiderba/balance-group-messenger.git
cd balance-group-messenger
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

Open your browser at: **http://127.0.0.1:5000**

That’s it. No database, no Docker required for basic use.

---

## How to Use

1. **Upload** a CSV or Excel file of your members.
2. **Map columns** – choose which column is the mobile number and which is the closing balance.
3. **Define groups** – set name + min/max balance for each group (or accept the automatic suggestions).
4. **Review members** – see who falls into which group and export any group if needed.
5. **Create messages** – write a template using `{{Name}}`, `{{ClosingBalance}}`, `{{City}}` etc.
6. **Send**
   - Configure your SMS API under **SMS Settings** and click Send.
   - Or generate WhatsApp links and open them one-by-one (or first 5 at once).

A sample file is included: `sample_data/members_sample.csv`

---

## SMS API Configuration

Go to **SMS Settings** in the app.

| Field            | Description                                      | Example                                      |
|------------------|--------------------------------------------------|----------------------------------------------|
| API URL          | Full endpoint of your SMS provider               | `https://api.yoursms.com/send`               |
| Method           | POST or GET                                      | `POST`                                       |
| Headers (JSON)   | Auth headers etc.                                | `{"Authorization": "Bearer xxx"}`            |
| Body Template    | Request body with placeholders                   | `{"to": "{{phone}}", "message": "{{message}}"}` |
| Success Codes    | HTTP codes that mean success                     | `200,201,202`                                |

The tool replaces `{{phone}}` and `{{message}}` automatically for every recipient.

Works with:
- Twilio (with some extra form-encoding if needed)
- Most Pakistani SMS aggregators that offer HTTP API
- Any custom / self-hosted SMS gateway that speaks HTTP

---

## Message Placeholders

Any column from your CSV can be used:

```
Assalam o Alaikum {{Name}},

Your closing balance is Rs. {{ClosingBalance}}.
Member ID: {{MemberID}}
City: {{City}}

Please clear dues at your earliest convenience.
Thank you.
```

---

## Project Structure

```
balance-group-messenger/
├── app.py                 # Main Flask application
├── requirements.txt
├── README.md
├── sample_data/
│   └── members_sample.csv
├── static/
│   ├── css/style.css
│   └── js/app.js
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── configure.html
│   ├── groups.html
│   ├── members.html
│   ├── messages.html
│   ├── send.html
│   └── settings.html
└── sms_config.json        # Created automatically when you save settings
```

---

## Advanced / Production Notes

- Change the `SECRET_KEY` environment variable for production.
- The app stores the uploaded data in the Flask session (cookie/server-side). For very large files you may want to switch to a temporary file or Redis.
- Rate limiting is left to your SMS provider. The tool sends sequentially.
- You can run behind nginx / gunicorn:

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

---

## Roadmap / Ideas for Contributors

- [ ] Optional WhatsApp presence check via unofficial Node service
- [ ] Message history / audit log
- [ ] Multi-user support with login
- [ ] Scheduled / delayed sending
- [ ] Support for more than 5 groups and nested filters (city + balance etc.)
- [ ] Docker Compose one-liner

Pull requests are welcome!

---

## License

MIT License – free for personal and commercial use.

---

## Author

Created for practical member communication needs.  
GitHub: [haiderba/balance-group-messenger](https://github.com/haiderba/balance-group-messenger)

If this tool saves you time, give the repo a ⭐
