from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.message import EmailMessage
import os
import traceback

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "✅ Task Submission Server is Running."

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

        # 使用環境變數設定
        sender_email = os.getenv("GMAIL_ACCOUNT")
        sender_pass = os.getenv("GMAIL_PASSWORD")
        receiver_email = os.getenv("MAIL_RECEIVER")

        if not all([sender_email, sender_pass, receiver_email]):
            return jsonify({"success": False, "error": "缺少必要的環境變數"}), 500

        msg = EmailMessage()
        msg["Subject"] = "📮 LawAI 任務發布通知"
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg.set_content(content)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)

        return jsonify({"success": True, "message": "任務已成功送出！"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
