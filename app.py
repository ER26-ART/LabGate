from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from database import WorkshopDB
import qrcode
from io import BytesIO
import pandas as pd
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os
import urllib.request
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# کلید امنیتی برای کارکرد سشن‌ها و پیام‌های فلش (Flash Messages)
app.secret_key = 'super_secret_arka_key' 
db = WorkshopDB()

# دانلود و ثبت فونت فارسی برای ساخت PDF
font_path = "static/fonts/Vazirmatn-Regular.ttf"
os.makedirs(os.path.dirname(font_path), exist_ok=True)
if not os.path.exists(font_path):
    urllib.request.urlretrieve("https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Regular.ttf", font_path)
pdfmetrics.registerFont(TTFont('Vazir', font_path))

def convert_persian_to_english(text):
    translation_table = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    return str(text).translate(translation_table)

def generate_qrcode_image(student_id):
    # آدرس آی‌پی خود را در صورت نیاز اینجا بروزرسانی کنید
    link = f"http://10.22.45.172:5000/scan?sid={student_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def generate_pdf_report(df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    
    # استایل تیتر (سرمه‌ای تیره)
    title_style = ParagraphStyle(
        name='Title', fontName='Vazir', fontSize=16, alignment=1, spaceAfter=20, textColor=colors.HexColor('#2C3E50')
    )
    
    def persian_text(text):
        if pd.isnull(text):
            text = "---"
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)

    elements.append(Paragraph(persian_text("📋 گزارش جامع تردد دانشجویان کارگاه"), title_style))
    
    if not df.empty:
        df_rtl = df[df.columns[::-1]]
        table_data = [[persian_text(col) for col in df_rtl.columns]]
        for _, row in df_rtl.iterrows():
            table_data.append([persian_text(cell) for cell in row])
            
        t = Table(table_data)
        
        # طراحی جدید جدول: تمیز، روشن و کاملاً خوانا (مناسب پرینت)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2C3E50')), # هدر سرمه‌ای حرفه‌ای
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),                # متن هدر سفید
            ('TEXTCOLOR', (0,1), (-1,-1), colors.black),               # متن داده‌ها مشکی خالص
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,-1), 'Vazir'),
            ('FONTSIZE', (0,0), (-1,0), 12),
            ('FONTSIZE', (0,1), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            # پس‌زمینه ردیف‌ها یکی‌درمیان سفید و طوسی بسیار روشن
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#F8F9F9'), colors.HexColor('#FFFFFF')]), 
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#BDC3C7')), # خطوط کشی طوسی ملایم
        ]))
        elements.append(t)
        
    doc.build(elements)
    buffer.seek(0)
    return buffer


# ================= مسيرهای وب (Routes) =================

@app.route('/')
def index():
    online_users = db.get_active_students()
    return render_template('index.html', online_users=online_users)

@app.route('/scan')
def scan():
    sid = request.args.get('sid')
    if sid:
        clean_id = convert_persian_to_english(sid)
        status, msg = db.process_scan(clean_id)
        if status:
            flash(msg, "success")
        else:
            flash(msg, "error")
    return redirect(url_for('index'))

@app.route('/manual_scan', methods=['POST'])
def manual_scan():
    sid = request.form.get('student_id')
    if sid:
        clean_id = convert_persian_to_english(sid)
        status, msg = db.process_scan(clean_id)
        if status:
            flash(msg, "success")
        else:
            flash(msg, "error")
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # دریافت اطلاعات از فرم HTML
        name = request.form.get('name')
        sid = request.form.get('student_id')
        username = request.form.get('username')
        password = request.form.get('password')
        file = request.files.get('profile_photo')

        if name and sid and username and password:
            clean_id = convert_persian_to_english(sid)
            
            # ۱. پردازش و ذخیره عکس پروفایل
            image_db_path = ""
            if file and file.filename != '':
                # ساخت نام امن برای عکس ترکیبی از شماره دانشجویی و اسم فایل
                filename = secure_filename(f"{clean_id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_db_path = f"uploads/profiles/{filename}"

            # ۲. هش کردن رمز عبور برای امنیت بالا
            hashed_password = generate_password_hash(password)

            # ۳. ارسال به دیتابیس
            status, msg = db.add_student(clean_id, name, username, hashed_password, image_db_path)
            
            if status:
                flash("هویت با موفقیت ثبت شد.", "success")
                # انتقال به صفحه صدور کارت با شماره دانشجویی
                return redirect(url_for('view_card', sid=clean_id))
            else:
                flash(msg, "error")
        else:
            flash("لطفاً تمام فیلدها را پر کنید.", "error")
            
    return render_template('register.html')

@app.route('/card', methods=['GET', 'POST'])
def view_card():
    sid = request.args.get('sid') or request.form.get('student_id')
    student_name = None
    if sid:
        clean_id = convert_persian_to_english(sid)
        student_name = db.get_student(clean_id)
        if not student_name:
            flash("هویتی یافت نشد.", "error")
            sid = None
    return render_template('card.html', student_name=student_name, sid=sid)

@app.route('/qrcode/<sid>')
def get_qrcode(sid):
    buffer = generate_qrcode_image(sid)
    return send_file(buffer, mimetype='image/png', as_attachment=True, download_name=f'qr_{sid}.png')

@app.route('/leaderboard')
def leaderboard():
    df = db.get_leaderboard_df()
    # تبدیل دیتافریم به HTML تمیز برای نمایش در فرانت‌اند
    table_html = df.to_html(classes='dataframe', index=False, justify='center') if not df.empty else None
    top_week = db.get_top_student_of_week()
    return render_template('leaderboard.html', table_html=table_html, top_week=top_week)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        if request.method == 'POST':
            password = request.form.get('password')
            if password == '1234':
                session['admin_logged_in'] = True
                return redirect(url_for('admin'))
            else:
                flash("احراز هویت ناموفق بود.", "error")
        return render_template('admin_login.html')
    
    logs_df = db.get_all_logs_df()
    students_df = db.get_all_students_df()
    
    active_count = len(logs_df[logs_df['زمان خروج'] == "---"]) if not logs_df.empty else 0
    stats = {
        'students': len(students_df),
        'logs': len(logs_df),
        'active': active_count
    }
    
    return render_template('admin.html', stats=stats, 
                           logs_table=logs_df.to_html(classes='dataframe', index=False) if not logs_df.empty else None,
                           students_table=students_df.to_html(classes='dataframe', index=False) if not students_df.empty else None)

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

@app.route('/download/pdf')
def download_pdf():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    df = db.get_all_logs_df()
    buffer = generate_pdf_report(df)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='attendance_report.pdf')

@app.route('/download/csv/<type>')
def download_csv(type):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    if type == 'logs':
        df = db.get_all_logs_df()
        filename = 'logs.csv'
    else:
        df = db.get_all_students_df()
        filename = 'students.csv'
        
    csv = df.to_csv(index=False).encode('utf-8-sig')
    buffer = BytesIO(csv)
    return send_file(buffer, mimetype='text/csv', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
