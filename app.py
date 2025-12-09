# pip install flask peewee bcrypt wtforms waitress
import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from peewee import *
from bcrypt import hashpw, gensalt, checkpw
from wtforms import Form, StringField, PasswordField, validators

# --- 1. 資料庫與模型配置 ---
DB_PATH = 'database.db'
db = SqliteDatabase(DB_PATH)
# 請務必設置一個安全的 SECRET_KEY
SECRET_KEY = os.environ.get('SECRET_KEY', 'a_very_secret_and_long_key_for_flask_session_security')

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(unique=True, index=True)
    password_hash = CharField()
    @staticmethod
    def create_user(username, password):
        # 由於我們在 before_request/after_request 中處理連線，這裡不需要 connect/close
        if User.select().where(User.username == username).exists():
            raise ValueError("Username already exists.")
        hashed_password = hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')
        return User.create(username=username, password_hash=hashed_password)

class Score(BaseModel):
    user = ForeignKeyField(User, backref='scores')
    score_value = IntegerField()
    timestamp = DateTimeField(default=datetime.now)
    class Meta:
        indexes = (
            (('score_value', 'timestamp'), False),
        )

def initialize_db(db):
    """連接資料庫並創建表格 (如果不存在)"""
    db.connect()
    try:
        # 確保在嘗試創建表格時資料庫是可用的
        db.create_tables([User, Score], safe=True)
    except Exception as e:
        print(f"Error creating tables: {e}")
    finally:
        if not db.is_closed():
            db.close()

# --- 2. 表單驗證 (WTForms) ---
class RegistrationForm(Form):
    username = StringField('使用者名稱', [validators.Length(min=4, max=25, message='長度必須介於 4 到 25 個字元')])
    password = PasswordField('密碼', [
        validators.DataRequired(message='密碼為必填項'),
        validators.EqualTo('confirm', message='兩次密碼輸入不匹配')
    ])
    confirm = PasswordField('重複密碼')

class LoginForm(Form):
    username = StringField('使用者名稱', [validators.DataRequired(message='使用者名稱為必填項')])
    password = PasswordField('密碼', [validators.DataRequired(message='密碼為必填項')])

# --- 3. Flask 應用程式設定與路由 ---

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# 在 app 實例化後立即執行初始化，確保資料表存在
initialize_db(db)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('您需要登入才能訪問此頁面。', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def before_request():
    """在每次請求前連接資料庫"""
    if db.is_closed():
        db.connect()

@app.after_request
def after_request(response):
    """在每次請求後關閉資料庫連接"""
    if not db.is_closed():
        db.close()
    return response

# --- 4. 路由定義 ---

@app.route('/')
def index():
    try:
        # 使用 select 和 join 來高效地提取數據
        top_scores = (Score
                      .select(Score.score_value, User.username)
                      .join(User)
                      .order_by(Score.score_value.desc())
                      .limit(10))
        
        # leaderboard_data 為字典列表，包含 'username' 和 'score'
        leaderboard_data = [{'username': s.user.username, 'score': s.score_value} for s in top_scores]
    except Exception as e:
        # 這會捕捉到 peewee.OperationalError: no such table，如果初始化失敗
        print(f"Leaderboard error (DB init issue?): {e}")
        flash('無法加載英雄榜數據。請確認資料庫已初始化。', 'danger')
        leaderboard_data = []

    return render_template('index.html', leaderboard=leaderboard_data, session=session)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm(request.form)
    if request.method == 'POST' and form.validate():
        try:
            User.create_user(form.username.data, form.password.data)
            flash('註冊成功！您現在可以登入了。', 'success')
            return redirect(url_for('login'))
        except ValueError as e:
            # 處理使用者名稱已存在
            flash(str(e), 'danger')
        except Exception as e:
            # 處理其他資料庫錯誤 (例如表不存在)
            print(f"Registration DB Error: {e}")
            flash('註冊失敗，伺服器或資料庫錯誤。', 'danger')
            
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        try:
            user = User.get(User.username == form.username.data)
        except User.DoesNotExist:
            flash('無效的使用者名稱或密碼。', 'danger')
            return render_template('login.html', form=form)

        if checkpw(form.password.data.encode('utf-8'), user.password_hash.encode('utf-8')):
            session['username'] = user.username
            session['user_id'] = user.id
            flash('登入成功！', 'success')
            return redirect(url_for('game'))
        else:
            flash('無效的使用者名稱或密碼。', 'danger')

    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    flash('您已成功登出。', 'info')
    return redirect(url_for('index'))

@app.route('/game')
@login_required
def game():
    return render_template('game.html')

@app.route('/submit_score', methods=['POST'])
@login_required
def submit_score():
    """接收 Brython 傳來分數的 API """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Request must be JSON format.'}), 415
    try:
        score_value = int(request.json.get('score'))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid or non-integer score value provided.'}), 400

    if score_value <= 0:
         return jsonify({'success': False, 'message': 'Score must be positive.'}), 400

    try:
        user_id = session.get('user_id')
        if user_id is None:
            return jsonify({'success': False, 'message': 'Authentication failed or session expired (No user_id).'}), 401
        
        # 直接傳入 user_id 作為外鍵值
        Score.create(
            user=user_id,
            score_value=score_value,
            timestamp=datetime.now()
        )
        print(f"Success: Score {score_value} saved for user ID {user_id}.")
        return jsonify({'success': True, 'message': 'Score saved successfully!'})
        
    except Exception as e:
        print(f"CRITICAL DB ERROR saving score: {e}")
        # 如果發生 DB 錯誤，提示用戶重新登入
        return jsonify({'success': False, 'message': 'Database error occurred. Please log in again.'}), 401

if __name__ == '__main__':
    app.run(debug=True)