
from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://www.lawfavor.com"}})

@app.route("/submit-task", methods=["POST"])
def submit_task():
    data = request.get_json()
    task_title = data.get("taskTitle")
    task_description = data.get("taskDescription")
    contact_info = data.get("contactInfo")

    if not all([task_title, task_description, contact_info]):
        return jsonify({"error": "缺少必要欄位"}), 400

    email_content = f"📌 任務標題：{task_title}\n\n📝 任務描述：{task_description}\n\n📬 聯絡方式：{contact_info}"

    sender_email = "lawaiadvisor@gmail.com"
    receiver_email = "lawaiadvisor@gmail.com"
    app_password = os.environ.get("EMAIL_APP_PASSWORD")

    if not app_password:
        return jsonify({"error": "未設定 EMAIL_APP_PASSWORD"}), 500

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "📬 LawAi 使用者提交新任務"
    message.attach(MIMEText(email_content, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.send_message(message)
        return jsonify({"message": "任務已成功發送"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False)
