import sqlite3
import pandas as pd
from datetime import datetime
import os

class WorkshopDB:
    def __init__(self, db_name="data/workshop.db"):
        # بررسی و ساخت پوشه data اگر وجود نداشت
        os.makedirs(os.path.dirname(db_name), exist_ok=True)
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    profile_image TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS attendance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT,
                    entry_time DATETIME,
                    exit_time DATETIME,
                    FOREIGN KEY (student_id) REFERENCES students (student_id)
                )
            ''')
            conn.commit()

    def add_student(self, student_id, name, username, password_hash, profile_image):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO students (student_id, name, username, password_hash, profile_image) VALUES (?, ?, ?, ?, ?)", 
                    (student_id, name, username, password_hash, profile_image)
                )
                conn.commit()
                return True, "دانشجو با موفقیت ثبت شد."
        except sqlite3.IntegrityError:
            return False, "این شماره دانشجویی یا نام کاربری قبلاً ثبت شده است."
        except Exception as e:
            return False, f"خطا در ثبت‌نام: {e}"

    def get_student(self, student_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM students WHERE student_id = ?", (student_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None

    def get_active_students(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # جستجوی تمام کسانی که زمان خروج آن‌ها هنوز ثبت نشده است (در کارگاه هستند)
                cursor.execute('''
                    SELECT s.student_id, s.name 
                    FROM students s
                    JOIN attendance_logs a ON s.student_id = a.student_id
                    WHERE a.exit_time IS NULL
                ''')
                active_users = cursor.fetchall()
                return active_users
        except Exception as e:
            print(f"Error fetching active students: {e}")
            return []
    
    def process_scan(self, student_id):
        if not self.get_student(student_id):
            return False, "دانشجو در سیستم یافت نشد. لطفاً ابتدا ثبت‌نام کنید."

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, entry_time FROM attendance_logs 
                WHERE student_id = ? AND exit_time IS NULL 
                ORDER BY entry_time DESC LIMIT 1
            ''', (student_id,))
            open_log = cursor.fetchone()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if open_log:
                log_id = open_log[0]
                cursor.execute("UPDATE attendance_logs SET exit_time = ? WHERE id = ?", (now, log_id))
                conn.commit()
                return True, f"خروج در ساعت {now} ثبت شد."
            else:
                cursor.execute("INSERT INTO attendance_logs (student_id, entry_time) VALUES (?, ?)", (student_id, now))
                conn.commit()
                return True, f"ورود در ساعت {now} ثبت شد."

    def get_all_logs_df(self):
        query = '''
            SELECT s.name AS 'نام و نام خانوادگی', 
                   a.student_id AS 'شماره دانشجویی', 
                   a.entry_time AS 'زمان ورود', 
                   a.exit_time AS 'زمان خروج'
            FROM attendance_logs a
            JOIN students s ON a.student_id = s.student_id
            ORDER BY a.entry_time DESC
        '''
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn)
            
        if not df.empty:
            df = df.fillna({'زمان خروج': '---'})
            translation_table = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
            df['شماره دانشجویی'] = df['شماره دانشجویی'].astype(str).str.translate(translation_table)
            # فقط برای اکسل (برای وب بعدا هندل میکنیم اما فرمت یکسان باشد بهتر است)
            df['شماره دانشجویی'] = df['شماره دانشجویی'].apply(lambda x: f'{x}')
            df.index = df.index + 1
            df.index.name = 'ردیف'
            df = df.reset_index()
        return df

    def get_all_students_df(self):
        query = "SELECT student_id AS 'شماره دانشجویی', name AS 'نام و نام خانوادگی' FROM students ORDER BY name ASC"
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn)
            
        if not df.empty:
            translation_table = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
            df['شماره دانشجویی'] = df['شماره دانشجویی'].astype(str).str.translate(translation_table)
            df['شماره دانشجویی'] = df['شماره دانشجویی'].apply(lambda x: f'{x}')
            df.index = df.index + 1
            df.index.name = 'ردیف'
            df = df.reset_index()
        return df
    def get_all_students_raw(self):
        """دریافت داده‌های خام اعضا برای جدول مدیریت (شامل نام کاربری)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # ما در اینجا مستقیماً username را هم از دیتابیس می‌کشیم بیرون
                cursor.execute("SELECT student_id, name, username FROM students")
                return cursor.fetchall()
        except Exception as e:
            print(f"Error fetching raw students: {e}")
            return []

    def get_leaderboard_df(self):
        query = '''
            SELECT s.name AS 'نام و نام خانوادگی', 
                   a.student_id AS 'شماره دانشجویی', 
                   a.entry_time, 
                   a.exit_time
            FROM attendance_logs a
            JOIN students s ON a.student_id = s.student_id
        '''
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn)
            
        if df.empty:
            return pd.DataFrame(columns=['رتبه', 'نام و نام خانوادگی', 'شماره دانشجویی', 'مجموع زمان حضور'])

        df['entry_time'] = pd.to_datetime(df['entry_time'])
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        df = df.dropna(subset=['exit_time'])
        
        if df.empty:
            return pd.DataFrame(columns=['رتبه', 'نام و نام خانوادگی', 'شماره دانشجویی', 'مجموع زمان حضور'])

        df['duration_seconds'] = (df['exit_time'] - df['entry_time']).dt.total_seconds()
        leaderboard = df.groupby(['شماره دانشجویی', 'نام و نام خانوادگی'])['duration_seconds'].sum().reset_index()
        leaderboard = leaderboard.sort_values(by='duration_seconds', ascending=False).reset_index(drop=True)
        
        leaderboard.index = leaderboard.index + 1
        leaderboard.index.name = 'رتبه'
        leaderboard = leaderboard.reset_index()
        
        def format_total(total_seconds):
            hours, remainder = divmod(int(total_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
        leaderboard['مجموع زمان حضور'] = leaderboard['duration_seconds'].apply(format_total)
        leaderboard = leaderboard.drop(columns=['duration_seconds'])
        
        translation_table = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
        leaderboard['شماره دانشجویی'] = leaderboard['شماره دانشجویی'].astype(str).str.translate(translation_table)
        leaderboard['شماره دانشجویی'] = leaderboard['شماره دانشجویی'].apply(lambda x: f'{x}')
        
        return leaderboard
    def get_top_student_of_week(self):
        """
        محاسبه نفر برتر هفته:
        SQLite تابع مستقیمی برای اختلاف زمان ندارد، بنابراین از julianday استفاده می‌کنیم
        تا روزها را به دست آورده و در ۲۴ (ساعت) و ۶۰ (دقیقه) ضرب کنیم.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT s.name, s.profile_image,
                           SUM(CAST((julianday(IFNULL(a.exit_time, datetime('now', 'localtime'))) - julianday(a.entry_time)) * 24 * 60 AS INTEGER)) as total_minutes
                    FROM students s
                    JOIN attendance_logs a ON s.student_id = a.student_id
                    -- فیلتر کردن رکوردهایی که مربوط به ۷ روز گذشته هستند
                    WHERE a.entry_time >= date('now', '-7 days', 'localtime')
                    GROUP BY s.student_id
                    ORDER BY total_minutes DESC
                    LIMIT 1
                ''')
                return cursor.fetchone()
        except Exception as e:
            print(f"Error fetching top student of the week: {e}")
            return None
    def delete_student(self, student_id):
        """حذف کامل یک دانشجو و تمام رکوردهای تردد او"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # ابتدا حذف تمام رکوردهای تردد این شخص
                cursor.execute("DELETE FROM attendance_logs WHERE student_id = ?", (student_id,))
                # سپس حذف خود شخص از جدول اصلی
                cursor.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error deleting student: {e}")
            return False

    def get_student_info(self, student_id):
        """دریافت اطلاعات یک شخص برای نمایش در فرم ویرایش"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT student_id, name, username FROM students WHERE student_id = ?", (student_id,))
                return cursor.fetchone()
        except Exception as e:
            print(f"Error fetching student info: {e}")
            return None

    def update_student(self, old_student_id, new_student_id, name, username):
        """ذخیره اطلاعات جدید دانشجو پس از ویرایش"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # آپدیت جدول اصلی
                cursor.execute('''
                    UPDATE students 
                    SET student_id = ?, name = ?, username = ?
                    WHERE student_id = ?
                ''', (new_student_id, name, username, old_student_id))
                
                # اگر شماره دانشجویی عوض شد، باید رکوردهای تردد او هم با شماره جدید آپدیت شوند
                if old_student_id != new_student_id:
                    cursor.execute('''
                        UPDATE attendance_logs 
                        SET student_id = ? 
                        WHERE student_id = ?
                    ''', (new_student_id, old_student_id))
                
                conn.commit()
                return True, "اطلاعات با موفقیت بروزرسانی شد."
        except sqlite3.IntegrityError:
            return False, "این شماره دانشجویی یا نام کاربری در سیستم وجود دارد و تکراری است."
        except Exception as e:
            return False, f"خطا در بروزرسانی: {e}"