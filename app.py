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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
    
    conn.commit()
    conn.close()

# DB helper
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

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
                "posts_remaining": posts_allowed
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
            "subscription_status": user['subscription_status'],
            "demo_mode": bool(user['demo_mode'])
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
            "subscription_status": user['subscription_status'],
            "demo_mode": bool(user['demo_mode'])
        }
    })

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
