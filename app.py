#!/usr/bin/env python3
"""
ContentKit Alpha Backend - SQLite Version (Temporal)
Funciona inmediatamente mientras resolvemos PostgreSQL
"""

import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')

# Config
DEMO_MODE = os.environ.get('DEMO_MODE', 'true').lower() == 'true'
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contentkit.db')

# Uploads (temporal)
UPLOAD_ROOT = os.environ.get('UPLOAD_ROOT', '/tmp/uploads')
APP_UPLOAD_DIR = os.path.join(UPLOAD_ROOT, 'contentkit')
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_MIME = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
}

# Init DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            plan_id TEXT DEFAULT 'starter',
            subscription_status TEXT DEFAULT 'active',
            posts_allowed INTEGER DEFAULT 4,
            posts_used_this_period INTEGER DEFAULT 0,
            demo_mode INTEGER DEFAULT 0,
            onboarding_completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Lightweight migration: add onboarding_completed if DB existed before
    try:
        cols = [r['name'] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        if 'onboarding_completed' not in cols:
            c.execute("ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0")
    except Exception:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT DEFAULT 'ready',
            brief TEXT,
            platform TEXT,
            format TEXT,
            generated_copy TEXT,
            generated_hashtags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Onboarding tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_images (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            image_type TEXT NOT NULL, -- 'space' | 'product'
            filename TEXT NOT NULL,
            original_name TEXT,
            description TEXT,
            file_path TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS onboarding_data (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            objectives TEXT, -- JSON array
            industry TEXT,
            tone TEXT,
            ai_analysis_report TEXT,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()

# DB helper
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_id_from_auth():
    """Very simple auth for Alpha: token == user_id (UUID)."""
    return request.headers.get('Authorization', '').replace('Bearer ', '').strip()


def require_auth():
    user_id = get_user_id_from_auth()
    if not user_id:
        return None, (jsonify({"error": "No autorizado"}), 401)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    if not user:
        return None, (jsonify({"error": "No autorizado"}), 401)
    return dict(user), None


def _safe_ext(mime: str):
    return ALLOWED_MIME.get(mime)


def save_uploaded_images(user_id: str, image_type: str, files, descriptions):
    """Save multiple uploaded images. Returns list of inserted rows (id, url, description)."""
    if image_type not in ('space', 'product'):
        raise ValueError('image_type inválido')

    os.makedirs(APP_UPLOAD_DIR, exist_ok=True)
    user_dir = os.path.join(APP_UPLOAD_DIR, user_id, image_type)
    os.makedirs(user_dir, exist_ok=True)

    saved = []
    conn = get_db()
    c = conn.cursor()

    for idx, f in enumerate(files):
        if not f:
            continue

        mime = f.mimetype
        ext = _safe_ext(mime)
        if not ext:
            raise ValueError(f"Tipo de archivo no permitido: {mime}")

        # Size check (best-effort)
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > MAX_IMAGE_BYTES:
            raise ValueError("Imagen demasiado grande (max 5MB)")

        image_id = str(uuid.uuid4())
        filename = f"{image_id}{ext}"
        file_path = os.path.join(user_dir, filename)
        f.save(file_path)

        desc = None
        if descriptions and idx < len(descriptions):
            desc = (descriptions[idx] or '').strip()[:500]

        c.execute(
            """
            INSERT INTO user_images (id, user_id, image_type, filename, original_name, description, file_path, mime_type, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (image_id, user_id, image_type, filename, f.filename, desc, file_path, mime, size)
        )

        saved.append({
            "id": image_id,
            "url": f"/api/uploads/{image_id}",
            "description": desc,
            "type": image_type,
        })

    conn.commit()
    conn.close()
    return saved

@app.route('/api/init', methods=['POST'])
def init_endpoint():
    """Initialize database - call this if tables don't exist"""
    try:
        init_db()
        return jsonify({"status": "ok", "message": "Database initialized"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    try:
        conn = get_db()
        conn.execute('SELECT 1')
        conn.close()
        return jsonify({
            "status": "ok", 
            "version": "alpha-sqlite",
            "database": "sqlite",
            "demo_mode": DEMO_MODE
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Get plans
@app.route('/api/plans', methods=['GET'])
def get_plans():
    posts = 999 if DEMO_MODE else 4
    return jsonify({
        'demo_mode': DEMO_MODE,
        'demo_message': 'Modo DEMO: Generación ilimitada' if DEMO_MODE else None,
        'plans': {
            'starter': {'id': 'starter', 'price_eur': 50, 'posts_per_month': posts, 
                       'features': [f'{posts} publicaciones', 'Imágenes IA', 'Copy + hashtags']},
            'pro': {'id': 'pro', 'price_eur': 99, 'posts_per_month': posts,
                    'features': [f'{posts} publicaciones', '1 sesión con Alberto', 'Soporte prioritario']},
            'business': {'id': 'business', 'price_eur': 199, 'posts_per_month': posts,
                        'features': [f'{posts} publicaciones', '2 sesiones', 'WhatsApp directo']}
        }
    })

# Register
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    brand_name = data.get('brand_name')
    plan_id = data.get('plan_id', 'starter')
    
    if not all([email, password, name, brand_name]):
        return jsonify({"error": "Faltan campos"}), 400
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if exists
        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "Usuario ya existe"}), 409
        
        # Create user
        user_id = str(uuid.uuid4())
        posts_allowed = 999 if DEMO_MODE else 4
        
        c.execute("""
            INSERT INTO users (id, email, password, name, brand_name, plan_id, posts_allowed, demo_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email, password, name, brand_name, plan_id, posts_allowed, int(DEMO_MODE)))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "token": user_id,
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "plan_id": plan_id,
                "posts_remaining": posts_allowed,
                "posts_allowed": posts_allowed,
                "posts_used_this_period": 0,
                "onboarding_completed": False
            }
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Login
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "Credenciales inválidas"}), 401
    
    if user['subscription_status'] != 'active':
        return jsonify({"error": "Suscripción no activa"}), 403
    
    remaining = user['posts_allowed'] - user['posts_used_this_period']
    
    return jsonify({
        "token": user['id'],
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "brand_name": user['brand_name'],
            "plan_id": user['plan_id'],
            "posts_remaining": remaining,
            "posts_allowed": user['posts_allowed'],
            "posts_used_this_period": user['posts_used_this_period'],
            "subscription_status": user['subscription_status'],
            "demo_mode": bool(user['demo_mode']),
            "onboarding_completed": bool(user['onboarding_completed']),
        }
    })

# Get profile
@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    
    remaining = user['posts_allowed'] - user['posts_used_this_period']
    
    return jsonify({
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "brand_name": user['brand_name'],
            "plan_id": user['plan_id'],
            "posts_remaining": remaining,
            "posts_allowed": user['posts_allowed'],
            "posts_used_this_period": user['posts_used_this_period'],
            "subscription_status": user['subscription_status'],
            "demo_mode": bool(user['demo_mode']),
            "onboarding_completed": bool(user['onboarding_completed']),
        }
    })

# --- Onboarding ---

@app.route('/api/onboarding/status', methods=['GET'])
def onboarding_status():
    user, err = require_auth()
    if err:
        return err

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT completed_at FROM onboarding_data WHERE user_id = ?", (user['id'],))
    row = c.fetchone()
    conn.close()

    completed = bool(user.get('onboarding_completed')) or (row and row['completed_at'] is not None)
    return jsonify({
        "completed": bool(completed),
    })


@app.route('/api/onboarding/start', methods=['POST'])
def onboarding_start():
    user, err = require_auth()
    if err:
        return err

    data = request.json or {}
    objectives = data.get('objectives') or []
    industry = (data.get('industry') or '').strip()
    tone = (data.get('tone') or '').strip()

    if not isinstance(objectives, list) or len(objectives) == 0:
        return jsonify({"error": "Selecciona al menos un objetivo"}), 400
    if not industry:
        return jsonify({"error": "Industria requerida"}), 400
    if not tone:
        return jsonify({"error": "Tono requerido"}), 400

    onboarding_id = str(uuid.uuid4())
    conn = get_db()
    c = conn.cursor()

    # Upsert onboarding_data by user_id
    c.execute("SELECT id FROM onboarding_data WHERE user_id = ?", (user['id'],))
    existing = c.fetchone()
    if existing:
        c.execute(
            """UPDATE onboarding_data
               SET objectives=?, industry=?, tone=?, updated_at=CURRENT_TIMESTAMP
               WHERE user_id=?""",
            (json.dumps(objectives), industry, tone, user['id'])
        )
        onboarding_id = existing['id']
    else:
        c.execute(
            """INSERT INTO onboarding_data (id, user_id, objectives, industry, tone)
               VALUES (?, ?, ?, ?, ?)""",
            (onboarding_id, user['id'], json.dumps(objectives), industry, tone)
        )

    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "onboarding_id": onboarding_id})


@app.route('/api/onboarding/upload-space', methods=['POST'])
def onboarding_upload_space():
    user, err = require_auth()
    if err:
        return err

    files = request.files.getlist('files')
    descriptions = request.form.getlist('descriptions')
    if not files or len([f for f in files if f and f.filename]) == 0:
        return jsonify({"error": "No se recibieron archivos"}), 400

    try:
        saved = save_uploaded_images(user['id'], 'space', files, descriptions)
        return jsonify({"uploaded": len(saved), "files": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/onboarding/upload-products', methods=['POST'])
def onboarding_upload_products():
    user, err = require_auth()
    if err:
        return err

    files = request.files.getlist('files')
    descriptions = request.form.getlist('descriptions')
    if not files or len([f for f in files if f and f.filename]) == 0:
        return jsonify({"uploaded": 0, "files": []})

    try:
        saved = save_uploaded_images(user['id'], 'product', files, descriptions)
        return jsonify({"uploaded": len(saved), "files": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/onboarding/analyze', methods=['POST'])
def onboarding_analyze():
    user, err = require_auth()
    if err:
        return err

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT objectives, industry, tone FROM onboarding_data WHERE user_id = ?", (user['id'],))
    ob = c.fetchone()
    if not ob:
        conn.close()
        return jsonify({"error": "Primero completa tus objetivos/industria/tono"}), 400

    c.execute("SELECT COUNT(*) as n FROM user_images WHERE user_id = ? AND image_type = 'space'", (user['id'],))
    n_space = c.fetchone()['n']

    if n_space < 3:
        conn.close()
        return jsonify({"error": "Necesitas subir al menos 3 fotos del local"}), 400

    # MVP: analysis mock (texto estático pero personalizado)
    objectives = []
    try:
        objectives = json.loads(ob['objectives'] or '[]')
    except Exception:
        objectives = []

    report = (
        f"Análisis (MVP - mock)\n\n"
        f"Sector: {ob['industry']}\n"
        f"Tono: {ob['tone']}\n"
        f"Objetivos: {', '.join(objectives) if objectives else '—'}\n\n"
        f"Hemos recibido {n_space} fotos de tu local.\n"
        f"Recomendación: mezcla 70% contenido de valor + 30% promoción. "
        f"Incluye pruebas sociales y consistencia visual."
    )

    c.execute(
        """UPDATE onboarding_data
           SET ai_analysis_report=?, completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
           WHERE user_id=?""",
        (report, user['id'])
    )
    c.execute("UPDATE users SET onboarding_completed = 1 WHERE id = ?", (user['id'],))

    conn.commit()
    conn.close()

    return jsonify({"report": report, "completed": True})


@app.route('/api/user/images', methods=['GET'])
def list_user_images():
    user, err = require_auth()
    if err:
        return err

    image_type = request.args.get('type')
    conn = get_db()
    c = conn.cursor()
    if image_type in ('space', 'product'):
        c.execute("SELECT id, image_type, description, created_at FROM user_images WHERE user_id=? AND image_type=? ORDER BY created_at DESC", (user['id'], image_type))
    else:
        c.execute("SELECT id, image_type, description, created_at FROM user_images WHERE user_id=? ORDER BY created_at DESC", (user['id'],))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    for r in rows:
        r['url'] = f"/api/uploads/{r['id']}"
    return jsonify({"images": rows})


@app.route('/api/uploads/<image_id>', methods=['GET'])
def get_upload(image_id):
    user, err = require_auth()
    if err:
        return err

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT file_path, mime_type FROM user_images WHERE id = ? AND user_id = ?", (image_id, user['id']))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "No encontrado"}), 404

    from flask import send_file
    return send_file(row['file_path'], mimetype=row['mime_type'])


# Generate post
@app.route('/api/posts/generate', methods=['POST'])
def generate_post():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    data = request.json
    
    brief = data.get('brief')
    platform = data.get('platform', 'instagram')
    fmt = data.get('format', 'square')
    
    if not brief:
        return jsonify({"error": "Brief requerido"}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check user
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({"error": "No autorizado"}), 401
    
    remaining = user['posts_allowed'] - user['posts_used_this_period']
    if remaining <= 0:
        conn.close()
        return jsonify({"error": "Límite alcanzado"}), 403
    
    # Generate content
    post_id = str(uuid.uuid4())
    copy = f"✨ {brief[:50]}...\n\n¿Qué opinas? Cuéntamelo 👇\n\n#content #marketing #{platform} #negocio"
    hashtags = json.dumps(['#contentkit', f'#{platform}', '#marketing', '#negocio', '#emprendedor'])
    
    # Save post
    c.execute("""
        INSERT INTO posts (id, user_id, brief, platform, format, generated_copy, generated_hashtags, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ready')
    """, (post_id, user_id, brief, platform, fmt, copy, hashtags))
    
    # Update count
    c.execute("UPDATE users SET posts_used_this_period = posts_used_this_period + 1 WHERE id = ?", (user_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "post": {
            "id": post_id,
            "brief": brief,
            "platform": platform,
            "format": fmt,
            "generated_copy": copy,
            "generated_hashtags": json.loads(hashtags),
            "status": "ready",
            "created_at": datetime.now().isoformat()
        }
    })

# List posts
@app.route('/api/posts/list', methods=['GET'])
def list_posts():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    posts = []
    for row in rows:
        post = dict(row)
        if post.get('generated_hashtags'):
            try:
                post['generated_hashtags'] = json.loads(post['generated_hashtags'])
            except:
                post['generated_hashtags'] = []
        posts.append(post)
    
    return jsonify({"posts": posts})

if __name__ == '__main__':
    init_db()
    print("✅ SQLite database initialized")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# Initialize on import (for gunicorn)
try:
    init_db()
    print("✅ Database initialized on import")
except Exception as e:
    print(f"⚠️ DB init on import: {e}")
