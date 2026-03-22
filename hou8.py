"""
单细胞跨物种分析平台后端服务
传统网页版 - 支持页面渲染和表单提交
"""

import os
import sqlite3
import json
import time
import math
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 创建Flask应用实例
app = Flask(__name__, template_folder='templates')

# 设置应用密钥
app.secret_key = 'scross_secret_key_2023'

# 启用跨域请求支持
CORS(app, 
     supports_credentials=True,
     origins=["http://localhost:8902", "http://127.0.0.1:8902"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type"])

# ============ 应用配置 ============
app.config.update({
    'UPLOAD_FOLDER': 'user_uploads',
    'ANALYSIS_FOLDER': 'analysis_results',
    'DATABASE': 'scross.db',
    'MAX_CONTENT_LENGTH': 500 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {
        'h5', 'h5ad', 'mtx', 'tsv', 'csv', 'txt', 'gz', 'rds'
    }
})

# 确保必要目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ANALYSIS_FOLDER'], exist_ok=True)

# ============ 辅助函数 ============
def allowed_file(filename):
    """检查文件扩展名是否合法"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_user_files(user_id):
    """获取用户上传的文件"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, filename, file_type, size, description, uploaded_at
            FROM files WHERE user_id = ? ORDER BY uploaded_at DESC
        ''', (user_id,))
        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'filename': row[1],
                'type': row[2],
                'size': row[3],
                'description': row[4],
                'uploaded_at': row[5]
            })
        return files

def get_all_uploads():
    """获取所有上传的文件"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT f.id, f.user_id, f.filename, f.file_type, f.size, f.description, f.uploaded_at, u.username
            FROM files f 
            LEFT JOIN users u ON f.user_id = u.id 
            ORDER BY f.uploaded_at DESC
        ''')
        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'user_id': row[1],
                'filename': row[2],
                'type': row[3],
                'size': row[4],
                'description': row[5],
                'uploaded_at': row[6],
                'uploader': row[7] or 'Unknown'
            })
        return files

def save_uploaded_file(file, user_id, description=None):
    """保存上传文件到用户专属目录"""
    if not file or not allowed_file(file.filename):
        return None
    
    filename = secure_filename(file.filename)
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(user_dir, filename)):
        filename = f"{base}_{counter}{ext}"
        counter += 1
    
    filepath = os.path.join(user_dir, filename)
    file.save(filepath)
    
    return {
        'filename': filename,
        'filepath': filepath,
        'file_type': filename.split('.')[-1].lower(),
        'size': os.path.getsize(filepath),
        'description': description
    }

# ============ 数据库初始化 ============
def init_db():
    """初始化数据库表结构"""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        # 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                email_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 分析任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                analysis_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                parameters TEXT,
                email_notification BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # 文件表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                analysis_id INTEGER,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                description TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (analysis_id) REFERENCES analyses (id)
            )
        ''')
        
        # ========== 演示用户创建代码 ==========
        # 创建一个测试账号，方便测试登录功能
        # 用户名: demo, 密码: demo123
        try:
            cursor.execute(
                'INSERT INTO users (username, password, email, email_verified) VALUES (?, ?, ?, ?)',
                ('demo', 'demo123', 'demo@example.com', True)
            )
            conn.commit()
            print("✓ 演示用户已创建: demo / demo123")
        except sqlite3.IntegrityError:
            print("✓ 演示用户已存在，跳过创建")
            pass

# 应用启动时初始化数据库
init_db()

# ============ 页面路由 ============

@app.route('/')
def index():
    """首页"""
    message = request.args.get('message', '')
    return render_template('index.html', message=message)

@app.route('/about')
def about():
    """关于页面"""
    return render_template('about.html')

@app.route('/case-studies')
def case_studies():
    """案例研究页面"""
    return render_template('case_studies.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'GET':
        message = request.args.get('message', '')
        return render_template('login.html', message=message)
    
    # POST请求 - 处理登录表单
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return render_template('login.html', error='Please enter username and password')
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, email FROM users 
            WHERE username = ? AND password = ?
        ''', (username, password))
        
        user = cursor.fetchone()
        
        if user:
            # 设置cookie（替代session）
            response = redirect(url_for('dashboard'))
            response.set_cookie('user_id', str(user[0]), max_age=3600*24)
            response.set_cookie('username', user[1], max_age=3600*24)
            return response
        else:
            return render_template('login.html', error='Invalid username or password')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if request.method == 'GET':
        message = request.args.get('message', '')
        return render_template('register.html', message=message)
    
    # POST请求 - 处理注册表单
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if not all([username, email, password, confirm_password]):
        return render_template('register.html', error='Please fill all fields')
    
    if password != confirm_password:
        return render_template('register.html', error='Passwords do not match')
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        # 检查用户名是否已存在
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            return render_template('register.html', error='Username already exists')
        
        # 检查邮箱是否已存在
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            return render_template('register.html', error='Email already registered')
        
        # 创建新用户
        cursor.execute('''
            INSERT INTO users (username, password, email, email_verified)
            VALUES (?, ?, ?, ?)
        ''', (username, password, email, True))
        
        conn.commit()
        
        return redirect(url_for('login', message='Registration successful! Please login'))

@app.route('/logout')
def logout():
    """登出"""
    response = redirect(url_for('index'))
    response.delete_cookie('user_id')
    response.delete_cookie('username')
    return response

@app.route('/dashboard')
def dashboard():
    """用户仪表盘"""
    user_id = request.cookies.get('user_id')
    username = request.cookies.get('username')
    
    if not user_id:
        return redirect(url_for('login', message='Please login first'))
    
    files = get_user_files(user_id)
    message = request.args.get('message', '')
    
    return render_template('dashboard.html', 
                          username=username, 
                          user_id=user_id,
                          files=files,
                          file_count=len(files),
                          message=message)

@app.route('/upload', methods=['GET', 'POST'])
def upload_page():
    """文件上传页面"""
    user_id = request.cookies.get('user_id')
    username = request.cookies.get('username')
    
    if not user_id:
        return redirect(url_for('login', message='Please login first'))
    
    if request.method == 'GET':
        return render_template('upload.html', username=username)
    
    # POST请求 - 处理文件上传
    file = request.files.get('file')
    description = request.form.get('description', '')
    
    if not file:
        return render_template('upload.html', error='Please select a file', username=username)
    
    file_info = save_uploaded_file(file, user_id, description)
    
    if not file_info:
        return render_template('upload.html', error='File type not supported', username=username)
    
    # 保存文件信息到数据库
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files (user_id, filename, filepath, file_type, size, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, file_info['filename'], file_info['filepath'], 
              file_info['file_type'], file_info['size'], file_info['description']))
        conn.commit()
    
    return redirect(url_for('uploads_list', message='File uploaded successfully!'))

@app.route('/uploads')
def uploads_list():
    """我的文件列表页面"""
    user_id = request.cookies.get('user_id')
    username = request.cookies.get('username')
    
    if not user_id:
        return redirect(url_for('login', message='Please login first'))
    
    files = get_user_files(user_id)
    message = request.args.get('message', '')
    
    return render_template('uploads_list.html', 
                          username=username,
                          files=files,
                          message=message)

@app.route('/all-uploads')
def all_uploads():
    """所有用户上传的文件列表"""
    user_id = request.cookies.get('user_id')
    username = request.cookies.get('username')
    
    if not user_id:
        return redirect(url_for('login', message='Please login first'))
    
    files = get_all_uploads()
    
    return render_template('all_uploads.html',
                          username=username,
                          files=files)

@app.route('/download/<int:file_id>')
def download_file(file_id):
    """下载文件"""
    user_id = request.cookies.get('user_id')
    
    if not user_id:
        return redirect(url_for('login', message='Please login first'))
    
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT filepath, filename FROM files WHERE id = ?', (file_id,))
        result = cursor.fetchone()
        
        if not result:
            return redirect(url_for('uploads_list', message='File not found'))
        
        filepath, filename = result
        directory = os.path.dirname(filepath)
        
        if os.path.exists(filepath):
            return send_from_directory(directory, os.path.basename(filepath), 
                                      as_attachment=True, download_name=filename)
        else:
            return redirect(url_for('uploads_list', message='File not found on server'))

# ============ API接口（兼容原有AJAX调用）============
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'success': True,
        'message': 'Service is running',
        'timestamp': time.time()
    })

# ============ 错误处理 ============
@app.errorhandler(404)
def not_found(error):
    """404错误页面"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误页面"""
    return render_template('500.html'), 500

# ============ 主程序入口 ============
if __name__ == '__main__':
    print("\n" + "="*50)
    print(f"{'ScCross Service Starting':^50}")
    print("="*50)
    print(f" * Working directory: {os.getcwd()}")
    print(f" * Port: 8902")
    print(f" * Home: http://localhost:8902/")
    print("="*50)
    
    # 检查templates目录
    if os.path.exists('templates'):
        print("✓ templates directory exists")
    else:
        print("⚠ templates directory not found - please create it")
    
    # 检查数据库
    if os.path.exists(app.config['DATABASE']):
        print("✓ Database file exists")
    else:
        print("✓ Database initialized")
    
    print("="*50)
    print("Available pages:")
    print("  GET  /              - Home page")
    print("  GET  /about         - About page")
    print("  GET  /case-studies  - Case studies")
    print("  GET  /login         - Login page")
    print("  GET  /register      - Register page")
    print("  GET  /dashboard     - User dashboard")
    print("  GET  /upload        - Upload page")
    print("  GET  /uploads       - My files")
    print("  GET  /all-uploads   - All files")
    print("="*50)
    print("Test user:")
    print("  Username: demo")
    print("  Password: demo123")
    print("="*50 + "\n")
    
    # 启动Flask开发服务器
    app.run(host='0.0.0.0', port=8902, debug=True)