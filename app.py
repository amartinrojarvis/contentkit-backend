#!/usr/bin/env python3
"""
ContentKit Alpha Backend v2.0
Con PostgreSQL para persistencia real
"""

import os
import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')

# Config
DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true'
DATABASE_URL = os.environ.get('DATABASE_URL')

# DB Connection
def get_db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

# Initialize DB
def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            with open('schema.sql', 'r') as f:
                cur.execute(f.read())
        conn.commit()

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
        return jsonify({"status": "ok", "version": "alpha-2.0", "database": "connected", "demo_mode": DEMO_MODE})
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
            'starter': {'id': 'starter', 'price_eur': 50, 'posts_per_month': posts, 'features': [f'{posts} publicaciones', 'Imágenes IA', 'Copy + hashtags']},
            'pro': {'id': 'pro', 'price_eur': 99, 'posts_per_month': posts, 'features': [f'{posts} publicaciones', '1 sesión con Alberto', 'Soporte prioritario']},
            'business': {'id': 'business', 'price_eur': 199, 'posts_per_month': posts, 'features': [f'{posts} publicaciones', '2 sesiones', 'WhatsApp directo']}
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
        with get_db() as conn:
            with conn.cursor() as cur:
                # Check if exists
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    return jsonify({"error": "Usuario ya existe"}), 409
                
                # Create user
                user_id = str(uuid.uuid4())
                posts_allowed = 999 if DEMO_MODE else 4
                
                cur.execute("""
                    INSERT INTO users (id, email, password, name, brand_name, plan_id, posts_allowed, demo_mode, current_period_end)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, email, password, name, brand_name, plan_id, posts_allowed, DEMO_MODE, 
                      datetime.now() + timedelta(days=365 if DEMO_MODE else 30)))
                
                conn.commit()
                
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
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
                user = cur.fetchone()
                
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
                        "demo_mode": user['demo_mode']
                    }
                })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get profile
@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                
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
                        "demo_mode": user['demo_mode']
                    }
                })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Generate post (simplified for demo)
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
        with get_db() as conn:
            with conn.cursor() as cur:
                # Check user and remaining posts
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                
                if not user:
                    return jsonify({"error": "No autorizado"}), 401
                
                remaining = user['posts_allowed'] - user['posts_used_this_period']
                if remaining <= 0:
                    return jsonify({"error": "Límite alcanzado"}), 403
                
                # Generate content (mock for demo)
                post_id = str(uuid.uuid4())
                copy = f"✨ {brief[:50]}...\n\n¿Te ha pasado alguna vez? Cuéntamelo en comentarios 👇\n\n#content #marketing #{platform}"
                hashtags = ['#contentkit', f'#{platform}', '#marketing', '#negocio', '#crecimiento']
                
                # Save post
                cur.execute("""
                    INSERT INTO posts (id, user_id, brief, platform, format, generated_copy, generated_hashtags, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ready')
                """, (post_id, user_id, brief, platform, fmt, copy, hashtags))
                
                # Update user count
                cur.execute("UPDATE users SET posts_used_this_period = posts_used_this_period + 1 WHERE id = %s", (user_id,))
                
                conn.commit()
                
                return jsonify({
                    "post": {
                        "id": post_id,
                        "brief": brief,
                        "platform": platform,
                        "format": fmt,
                        "generated_copy": copy,
                        "generated_hashtags": hashtags,
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
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM posts 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                """, (user_id,))
                posts = cur.fetchall()
                
                return jsonify({"posts": [dict(p) for p in posts]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Init DB on startup
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ DB init warning: {e}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
