#!/usr/bin/env python3
"""
ContentKit Alpha Backend - SQLite Version
Funciona inmediatamente sin PostgreSQL
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
DEMO_MODE = True  # Forzado a True para testing
DB_FILE = '/tmp/contentkit.db'  # SQLite en /tmp (ephemeral pero funcional)

# Init SQLite
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            plan_id TEXT DEFAULT 'starter',
            subscription_status TEXT DEFAULT 'active',
            posts_allowed INTEGER DEFAULT 999,
            posts_used_this_period INTEGER DEFAULT 0,
            demo_mode INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
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
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# DB connection
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "version": "alpha-sqlite",
        "database": "sqlite",
        "demo_mode": True
    })

# Get plans
@app.route('/api/plans', methods=['GET'])
def get_plans():
    return jsonify({
        'demo_mode': True,
        'demo_message': 'Modo DEMO: Generación ilimitada',
        'plans': {
            'starter': {'id': 'starter', 'price_eur': 50, 'posts_per_month': 999, 'features': ['999 publicaciones', 'Imágenes IA', 'Copy + hashtags']},
            'pro': {'id': 'pro', 'price_eur': 99, 'posts_per_month': 999, 'features': ['999 publicaciones', '1 sesión con Alberto', 'Soporte']},
            'business': {'id': 'business', 'price_eur': 199, 'posts_per_month': 999, 'features': ['999 publicaciones', '2 sesiones', 'WhatsApp']}
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
    
    if not all([email, password, name, brand_name]):
        return jsonify({"error": "Faltan campos"}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Check if exists
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "Usuario ya existe"}), 409
        
        user_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO users (id, email, password, name, brand_name, posts_allowed, demo_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email, password, name, brand_name, 999, 1))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "token": user_id,
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "plan_id": "starter",
                "posts_remaining": 999,
                "demo_mode": True
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
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password))
        user = cur.fetchone()
        conn.close()
        
        if not user:
            return jsonify({"error": "Credenciales inválidas"}), 401
        
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
                "demo_mode": bool(user['demo_mode'])
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get profile
@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
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
                "demo_mode": bool(user['demo_mode'])
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Check user
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        
        if not user:
            conn.close()
            return jsonify({"error": "No autorizado"}), 401
        
        remaining = user['posts_allowed'] - user['posts_used_this_period']
        if remaining <= 0:
            conn.close()
            return jsonify({"error": "Límite alcanzado"}), 403
        
        # Generate content
        post_id = str(uuid.uuid4())
        copy = f"✨ {brief[:50]}...\n\n¿Te ha pasado alguna vez? Cuéntamelo en comentarios 👇\n\n#content #marketing #{platform}"
        hashtags = json.dumps(['#contentkit', f'#{platform}', '#marketing', '#negocio'])
        
        # Save post
        cur.execute("""
            INSERT INTO posts (id, user_id, brief, platform, format, generated_copy, generated_hashtags, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ready')
        """, (post_id, user_id, brief, platform, fmt, copy, hashtags))
        
        # Update count
        cur.execute("UPDATE users SET posts_used_this_period = posts_used_this_period + 1 WHERE id = ?", (user_id,))
        
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# List posts
@app.route('/api/posts/list', methods=['GET'])
def list_posts():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM posts 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (user_id,))
        posts = cur.fetchall()
        conn.close()
        
        result = []
        for p in posts:
            post_dict = dict(p)
            try:
                post_dict['generated_hashtags'] = json.loads(post_dict['generated_hashtags'])
            except:
                post_dict['generated_hashtags'] = ['#content', '#marketing']
            result.append(post_dict)
        
        return jsonify({"posts": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    print("✅ SQLite DB initialized")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
