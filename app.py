#!/usr/bin/env python3
"""
ContentKit Alpha Backend v1.1
API para generación de contenido con suscripción de pago
Soporta: ChatGPT Image 1.5 para fotos, Stripe para pagos
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, List, Dict

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Configuración
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'contentkit-alpha-dev-key')

# Constants
DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true'
DEMO_GENERATIONS = 999 if DEMO_MODE else 2  # Ilimitado (prácticamente) en modo demo

PLANS = {
    'starter': {'price': 5000, 'posts_per_month': 4, 'sessions_per_month': 0},    # 50€ = 5000 cents
    'pro': {'price': 9900, 'posts_per_month': 8, 'sessions_per_month': 1},        # 99€
    'business': {'price': 19900, 'posts_per_month': 16, 'sessions_per_month': 2}  # 199€
}

IMAGE_SIZES = {
    'square': '1024x1024',
    'vertical': '1024x1792',
    'landscape': '1792x1024'
}

# Base de datos simple (JSON) para MVP
DB_FILE = 'data/contentkit_db.json'
os.makedirs('data', exist_ok=True)

if not os.path.exists(DB_FILE):
    with open(DB_FILE, 'w') as f:
        json.dump({"users": [], "posts": [], "sessions": []}, f)

def load_db():
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

# ============== SERVIR FRONTEND ==============

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('../frontend', path)

# ============== API ENDPOINTS ==============

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "version": "alpha-1.1",
        "features": ["image_generation", "subscriptions", "stripe_integration"]
    })

# ============== PLANS ==============

@app.route('/api/plans', methods=['GET'])
def get_plans():
    """Devuelve los planes disponibles con precios en EUR"""
    plans_display = {}
    for plan_id, plan_data in PLANS.items():
        plans_display[plan_id] = {
            'id': plan_id,
            'price_eur': plan_data['price'] / 100,
            'posts_per_month': DEMO_GENERATIONS if DEMO_MODE else plan_data['posts_per_month'],
            'sessions_per_month': 0 if DEMO_MODE else plan_data['sessions_per_month'],
            'features': [
                f"{DEMO_GENERATIONS if DEMO_MODE else plan_data['posts_per_month']} publicaciones",
                "Imágenes con ChatGPT Image 1.5",
                "Copy + hashtags optimizados",
                "Estrategia de contenido IA"
            ] + ([f"{plan_data['sessions_per_month']} sesión con Alberto"] if not DEMO_MODE and plan_data['sessions_per_month'] > 0 else [])
        }
    return jsonify({
        'plans': plans_display,
        'demo_mode': DEMO_MODE,
        'demo_message': 'Modo DEMO: 2 generaciones gratuitas, sin pagos reales' if DEMO_MODE else None
    })

# ============== AUTH & USER ==============

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Registro de usuario + creación de suscripción Stripe"""
    data = request.json
    email = data.get('email')
    password = data.get('password')  # En producción: hash
    name = data.get('name')
    brand_name = data.get('brand_name')
    plan_id = data.get('plan_id', 'starter')
    stripe_payment_method = data.get('stripe_payment_method')  # Token de Stripe
    
    if not all([email, password, name, brand_name]):
        return jsonify({"error": "Faltan campos requeridos"}), 400
    
    if plan_id not in PLANS:
        return jsonify({"error": "Plan inválido"}), 400
    
    db = load_db()
    
    # Check if user exists
    if any(u['email'] == email for u in db['users']):
        return jsonify({"error": "Usuario ya existe"}), 409
    
    # En producción: crear suscripción en Stripe
    # Si DEMO_MODE, permitir sin pago
    if not DEMO_MODE:
        # Aquí iría la lógica de Stripe real
        pass  # Placeholder para Stripe
    
    # Si es DEMO, limitar generaciones
    posts_allowed = DEMO_GENERATIONS if DEMO_MODE else PLANS[plan_id]['posts_per_month']
    
    user = {
        'id': str(uuid.uuid4()),
        'email': email,
        'password': password,  # Hash in production!
        'name': name,
        'brand_name': brand_name,
        'plan_id': plan_id,
        'subscription_status': 'active',
        'posts_allowed': posts_allowed,
        'posts_used_this_period': 0,
        'sessions_allowed': 0 if DEMO_MODE else PLANS[plan_id]['sessions_per_month'],
        'sessions_used_this_period': 0,
        'current_period_start': datetime.now().isoformat(),
        'current_period_end': (datetime.now() + timedelta(days=365 if DEMO_MODE else 30)).isoformat(),
        'stripe_customer_id': 'demo' if DEMO_MODE else None,
        'stripe_subscription_id': 'demo' if DEMO_MODE else None,
        'demo_mode': DEMO_MODE,
        'created_at': datetime.now().isoformat(),
        'onboarding_completed': False
    }
    
    db['users'].append(user)
    save_db(db)
    
    return jsonify({
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "plan_id": user['plan_id'],
            "posts_remaining": user['posts_allowed'] - user['posts_used_this_period']
        },
        "token": user['id']
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    db = load_db()
    user = next((u for u in db['users'] if u['email'] == email), None)
    
    if not user or user['password'] != password:  # Check hash in production
        return jsonify({"error": "Credenciales inválidas"}), 401
    
    # Check subscription status
    if user['subscription_status'] != 'active':
        return jsonify({
            "error": "Suscripción no activa",
            "status": user['subscription_status']
        }), 403
    
    return jsonify({
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "brand_name": user['brand_name'],
            "plan_id": user['plan_id'],
            "posts_remaining": user['posts_allowed'] - user['posts_used_this_period'],
            "subscription_status": user['subscription_status']
        },
        "token": user['id']
    })

@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    """Obtener perfil del usuario autenticado"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    db = load_db()
    user = next((u for u in db['users'] if u['id'] == user_id), None)
    
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    
    return jsonify({
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "brand_name": user.get('brand_name', ''),
            "plan_id": user['plan_id'],
            "posts_remaining": user['posts_allowed'] - user['posts_used_this_period'],
            "posts_allowed": user['posts_allowed'],
            "subscription_status": user['subscription_status'],
            "demo_mode": user.get('demo_mode', False)
        }
    })

# ============== POSTS / CONTENT GENERATION ==============

@app.route('/api/posts/generate', methods=['POST'])
def generate_post():
    """
    Genera una publicación completa:
    - Imagen con ChatGPT Image 1.5
    - Copy con GPT-4
    - Hashtags relevantes
    """
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    data = request.json
    
    # Check user
    db = load_db()
    user = next((u for u in db['users'] if u['id'] == user_id), None)
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    
    # Check subscription
    if user['subscription_status'] != 'active':
        return jsonify({"error": "Suscripción no activa"}), 403
    
    # Check posts remaining
    posts_remaining = user['posts_allowed'] - user['posts_used_this_period']
    if posts_remaining <= 0:
        return jsonify({
            "error": "Límite de publicaciones alcanzado",
            "message": "Renueva tu suscripción o upgradea tu plan",
            "upgrade_url": "/pricing"
        }), 403
    
    # Get input data
    post_type = data.get('post_type')  # product, lifestyle, promotional, testimonial
    brief = data.get('brief')
    platform = data.get('platform', 'instagram')
    image_format = data.get('format', 'square')  # square, vertical, story
    tone = data.get('tone', 'professional')
    reference_image = data.get('reference_image')  # Optional: URL de imagen de referencia
    
    if not brief:
        return jsonify({"error": "El brief es requerido"}), 400
    
    # Generate content
    try:
        result = generate_content_with_ai(
            post_type=post_type,
            brief=brief,
            platform=platform,
            image_format=image_format,
            tone=tone,
            brand_name=user['brand_name'],
            reference_image=reference_image
        )
        
        # Save post to DB
        post = {
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'status': 'ready',
            'post_type': post_type,
            'brief': brief,
            'platform': platform,
            'format': image_format,
            'tone': tone,
            'generated_image_url': result['image_url'],
            'generated_prompt': result['prompt'],
            'generated_copy': result['copy'],
            'generated_hashtags': result['hashtags'],
            'created_at': datetime.now().isoformat(),
            'downloaded_at': None,
            'generation_cost': result.get('cost', 0)
        }
        
        db['posts'].append(post)
        
        # Increment user's post count
        user['posts_used_this_period'] += 1
        save_db(db)
        
        return jsonify({
            "post": post,
            "posts_remaining": posts_remaining - 1
        })
        
    except Exception as e:
        print(f"Error generating content: {e}")
        return jsonify({"error": "Error generando contenido", "details": str(e)}), 500

def generate_content_with_ai(post_type: str, brief: str, platform: str, 
                             image_format: str, tone: str, brand_name: str,
                             reference_image: Optional[str] = None) -> Dict:
    """
    Genera contenido usando OpenAI:
    1. Crea prompt optimizado para imagen
    2. Genera imagen con ChatGPT Image 1.5 (o DALL-E 3 como fallback)
    3. Genera copy con GPT-4
    4. Genera hashtags
    """
    
    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        # Fallback para demo sin API
        return generate_fallback_content(post_type, brief, platform, image_format, tone, brand_name)
    
    import openai
    openai.api_key = openai_key
    
    # Step 1: Generate optimized image prompt
    prompt_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Eres un experto en prompts para generación de imágenes. Crea prompts detallados y optimizados para ChatGPT Image 1.5/DALL-E 3."},
            {"role": "user", "content": f"""
Crea un prompt profesional para generar una imagen de tipo '{post_type}'.

Brief del cliente: {brief}
Tono deseado: {tone}
Marca: {brand_name}
Plataforma: {platform}

El prompt debe ser:
- Detallado y específico
- Optimizado para generación de imágenes de alta calidad
- En inglés (mejor para las APIs de imagen)
- Incluir estilo fotográfico, iluminación, composición

Solo devuelve el prompt, sin explicaciones.
"""}
        ],
        temperature=0.7,
        max_tokens=500
    )
    
    image_prompt = prompt_response.choices[0].message.content.strip()
    
    # Step 2: Generate image with ChatGPT Image 1.5 (or DALL-E 3)
    try:
        # Intentar con gpt-image-1.5 si está disponible
        # Si no, fallback a DALL-E 3
        image_size = IMAGE_SIZES.get(image_format, '1024x1024')
        
        image_response = openai.Image.create(
            model="dall-e-3",  # Cambiar a "gpt-image-1.5" cuando esté disponible
            prompt=image_prompt,
            size=image_size,
            quality="hd",
            n=1
        )
        
        image_url = image_response['data'][0]['url']
        image_cost = 0.08 if image_format == 'square' else 0.12  # Aproximado DALL-E 3
        
    except Exception as e:
        print(f"Image generation error: {e}")
        # Fallback: placeholder
        image_url = f"https://via.placeholder.com/{image_size.replace('x', '/')}?text=Imagen+generada"
        image_cost = 0
    
    # Step 3: Generate copy
    copy_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"Eres un copywriter experto en {platform}. Crea copy que enganche y convierta."},
            {"role": "user", "content": f"""
Crea un copy/caption para {platform} sobre:
{brief}

Tono: {tone}
Marca: {brand_name}
Tipo de contenido: {post_type}

El copy debe:
- Tener un hook fuerte en la primera línea
- Incluir emojis relevantes
- Tener una llamada a la acción (CTA)
- Ser optimizado para {platform}
- Máximo 150 palabras para Instagram/TikTok

Devuelve solo el copy, sin explicaciones.
"""}
        ],
        temperature=0.8,
        max_tokens=300
    )
    
    copy = copy_response.choices[0].message.content.strip()
    
    # Step 4: Generate hashtags
    hashtags_response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": f"""
Genera 10-15 hashtags relevantes para Instagram sobre:
{brief}

Nicho: {post_type}
Tono: {tone}

Requisitos:
- Mezcla de populares (1M+), medianos (100K-1M) y nicho (<100K)
- En español e inglés
- Sin # en la respuesta, solo las palabras

Devuelve solo los hashtags separados por espacios.
"""}
        ],
        temperature=0.5,
        max_tokens=100
    )
    
    hashtags_text = hashtags_response.choices[0].message.content.strip()
    hashtags = [f"#{tag.strip()}" for tag in hashtags_text.split() if tag.strip()]
    
    return {
        'image_url': image_url,
        'prompt': image_prompt,
        'copy': copy,
        'hashtags': hashtags[:15],  # Max 15 hashtags
        'cost': image_cost + 0.01  # Coste aproximado
    }

def generate_fallback_content(post_type, brief, platform, image_format, tone, brand_name):
    """Contenido de ejemplo cuando no hay API key"""
    
    formats_display = {
        'square': '1024x1024',
        'vertical': '1024x1792',
        'landscape': '1792x1024'
    }
    size = formats_display.get(image_format, '1024x1024')
    
    return {
        'image_url': f'https://via.placeholder.com/{size.replace("x", "/")}?text={brand_name.replace(" ", "+")}',
        'prompt': f'Professional {post_type} photography for {brand_name}: {brief}. Style: {tone}, high quality, commercial photography.',
        'copy': f'''✨ Nuevo contenido listo para {brand_name}!

{brief}

Descubre más en nuestra cuenta 🔗

¿Te gusta? ¡Déjanos un comentario! 💬

#contentkit #{brand_name.replace(" ", "")} #{post_type}''',
        'hashtags': ['#contentkit', f'#{brand_name.replace(" ", "")}', f'#{post_type}', '#marketing', '#socialmedia', '#contentcreator'],
        'cost': 0
    }

@app.route('/api/posts/list', methods=['GET'])
def list_posts():
    """Lista las publicaciones del usuario"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    db = load_db()
    user = next((u for u in db['users'] if u['id'] == user_id), None)
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    
    user_posts = [p for p in db['posts'] if p['user_id'] == user_id]
    user_posts.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        "posts": user_posts,
        "posts_remaining": user['posts_allowed'] - user['posts_used_this_period'],
        "posts_allowed": user['posts_allowed'],
        "period_end": user['current_period_end']
    })

@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    """Obtiene una publicación específica"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    db = load_db()
    post = next((p for p in db['posts'] if p['id'] == post_id and p['user_id'] == user_id), None)
    
    if not post:
        return jsonify({"error": "Publicación no encontrada"}), 404
    
    return jsonify({"post": post})

@app.route('/api/posts/<post_id>/download', methods=['POST'])
def mark_downloaded(post_id):
    """Marca una publicación como descargada"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    db = load_db()
    post = next((p for p in db['posts'] if p['id'] == post_id and p['user_id'] == user_id), None)
    
    if not post:
        return jsonify({"error": "Publicación no encontrada"}), 404
    
    post['downloaded_at'] = datetime.now().isoformat()
    post['status'] = 'downloaded'
    save_db(db)
    
    return jsonify({"message": "Marcado como descargado"})

# ============== PRO SESSIONS ==============

@app.route('/api/sessions/request', methods=['POST'])
def request_session():
    """Solicitar sesión con Alberto"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    data = request.json
    
    db = load_db()
    user = next((u for u in db['users'] if u['id'] == user_id), None)
    
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    
    # Check sessions remaining
    sessions_remaining = user['sessions_allowed'] - user['sessions_used_this_period']
    
    # If no sessions in plan, offer paid session
    if sessions_remaining <= 0:
        # Check if they want to pay for extra session
        session_type = data.get('type', 'strategy_review')
        prices = {'strategy_review': 7900, 'content_workshop': 14900, 'consulting_pack': 29900}
        
        return jsonify({
            "error": "No tienes sesiones disponibles",
            "message": "Puedes contratar una sesión adicional",
            "extra_session_price": prices.get(session_type, 7900) / 100,
            "checkout_url": f"/checkout/session?type={session_type}"
        }), 402  # Payment Required
    
    session_request = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_email": user['email'],
        "user_name": user['name'],
        "type": data.get('type', 'strategy_review'),
        "message": data.get('message', ''),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "scheduled_at": None,
        "meeting_link": None
    }
    
    db['sessions'].append(session_request)
    
    # Increment used sessions
    user['sessions_used_this_period'] += 1
    save_db(db)
    
    # TODO: Enviar notificación a Alberto (email/Slack/Telegram)
    
    return jsonify({
        "session": session_request,
        "message": "Solicitud enviada. Alberto te contactará en 24h para coordinar.",
        "sessions_remaining": sessions_remaining - 1
    }), 201

@app.route('/api/sessions/list', methods=['GET'])
def list_sessions():
    """Lista las sesiones del usuario"""
    user_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    db = load_db()
    user_sessions = [s for s in db['sessions'] if s['user_id'] == user_id]
    user_sessions.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        "sessions": user_sessions,
        "sessions_remaining": None  # Calcular dinámicamente
    })

# ============== STRIPE WEBHOOKS ==============

@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Webhook para eventos de Stripe"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    # En producción: verificar firma
    # event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    
    event = json.loads(payload)
    event_type = event.get('type')
    
    db = load_db()
    
    if event_type == 'invoice.payment_succeeded':
        # Renovar período
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        user = next((u for u in db['users'] if u['stripe_customer_id'] == customer_id), None)
        if user:
            user['posts_used_this_period'] = 0
            user['sessions_used_this_period'] = 0
            user['current_period_start'] = datetime.now().isoformat()
            user['current_period_end'] = (datetime.now() + timedelta(days=30)).isoformat()
            user['subscription_status'] = 'active'
            save_db(db)
    
    elif event_type == 'customer.subscription.deleted':
        # Cancelación
        subscription = event['data']['object']
        customer_id = subscription['customer']
        
        user = next((u for u in db['users'] if u['stripe_customer_id'] == customer_id), None)
        if user:
            user['subscription_status'] = 'canceled'
            save_db(db)
    
    return jsonify({"status": "ok"})

# ============== ADMIN ENDPOINTS ==============

@app.route('/api/admin/dashboard', methods=['GET'])
def admin_dashboard():
    """Dashboard para Alberto"""
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != os.environ.get('ADMIN_KEY', 'admin-secret-key'):
        return jsonify({"error": "No autorizado"}), 401
    
    db = load_db()
    
    # Stats
    total_users = len(db['users'])
    active_subscriptions = len([u for u in db['users'] if u['subscription_status'] == 'active'])
    total_posts = len(db['posts'])
    pending_sessions = len([s for s in db['sessions'] if s['status'] == 'pending'])
    
    # Revenue (aproximado)
    revenue = sum(
        PLANS[u['plan_id']]['price'] / 100 
        for u in db['users'] 
        if u['subscription_status'] == 'active'
    )
    
    return jsonify({
        "stats": {
            "total_users": total_users,
            "active_subscriptions": active_subscriptions,
            "total_posts_generated": total_posts,
            "pending_sessions": pending_sessions,
            "monthly_revenue_eur": round(revenue, 2)
        },
        "pending_sessions": [s for s in db['sessions'] if s['status'] == 'pending'],
        "recent_users": db['users'][-10:]
    })

@app.route('/api/admin/sessions/<session_id>/schedule', methods=['POST'])
def admin_schedule_session(session_id):
    """Programar sesión (para Alberto)"""
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != os.environ.get('ADMIN_KEY', 'admin-secret-key'):
        return jsonify({"error": "No autorizado"}), 401
    
    data = request.json
    db = load_db()
    
    session = next((s for s in db['sessions'] if s['id'] == session_id), None)
    if not session:
        return jsonify({"error": "Sesión no encontrada"}), 404
    
    session['status'] = 'scheduled'
    session['scheduled_at'] = data.get('scheduled_at')
    session['meeting_link'] = data.get('meeting_link')
    
    save_db(db)
    
    # TODO: Enviar email de confirmación al usuario
    
    return jsonify({"session": session})

# ============== MAIN ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🚀 ContentKit Alpha v1.1")
    print(f"🌐 http://localhost:{port}")
    print(f"📊 Admin: http://localhost:{port}/api/admin/dashboard")
    print(f"🔧 Debug: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
