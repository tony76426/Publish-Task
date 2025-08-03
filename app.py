from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://www.lawfavor.com"}})

@app.route("/")
def home():
    return "🟢 LawFavor Email API is Running."

@app.route("/submit-task", methods=["POST"])
def submit_task():
    try:
        data = request.get_json()
        contact = data.get("contact", "")
        title = data.get("title", "")
        description = data.get("description", "")

        if not contact or not title or not description:
            return jsonify({"error": "請填寫所有欄位"}), 400

        message_body = f"📬 任務聯絡方式：{contact}\n\n📌 任務標題：{title}\n\n📝 任務描述：\n{description}"
        msg = MIMEMultipart()
        msg["From"] = os.environ.get("EMAIL_SENDER")
        msg["To"] = os.environ.get("EMAIL_RECEIVER")
        msg["Subject"] = "🔔 有新任務發布！"

        msg.attach(MIMEText(message_body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(os.environ.get("EMAIL_SENDER"), os.environ.get("EMAIL_APP_PASSWORD"))
            server.sendmail(msg["From"], msg["To"], msg.as_string())

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
