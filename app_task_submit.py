
from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
import os
import traceback

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "🟢 Task Submission API is running."

@app.route("/submit-task", methods=["POST"])
def submit_task():
    try:
        data = request.get_json()
        title = data.get("title", "")
        description = data.get("description", "")
        name = data.get("name", "")
        phone = data.get("phone", "")
        line = data.get("line", "")
        email = data.get("email", "")

        # 整理內容
        content = f"""📮 新任務提交內容如下：

📌 任務標題：
{title}

📝 任務描述：
{description}

📬 聯絡資訊：
👤 姓名或暱稱：{name}
📞 聯絡電話：{phone}
💬 LINE ID：{line}
📧 Email：{email}
"""

        # Email 設定
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = os.environ.get("MAIL_SENDER")  # 寄件人
        sender_pass = os.environ.get("MAIL_APP_PASSWORD")  # 應用程式密碼
        receiver_email = os.environ.get("MAIL_RECEIVER")  # 收件人

        msg = MIMEText(content)
        msg["Subject"] = "📮 LawAI 任務發布通知"
        msg["From"] = sender_email
        msg["To"] = receiver_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_pass)
            server.send_message(msg)

        return jsonify({"success": True, "message": "已成功送出任務！"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
