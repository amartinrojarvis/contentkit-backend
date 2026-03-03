# ContentKit API

Backend Flask para ContentKit Alpha - API de generación de contenido con IA.

## 🚀 Despliegue en Render

### Paso 1: Subir a GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TU_USUARIO/contentkit-backend.git
git push -u origin main
```

### Paso 2: Crear servicio en Render
1. Ve a [render.com](https://render.com) e inicia sesión con GitHub
2. Click "New" → "Web Service"
3. Conecta el repo `contentkit-backend`
4. Configura:
   - **Name:** `contentkit-api` (o el que prefieras)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** `Free`
5. Click **Create Web Service**

### Paso 3: Configurar Variables de Entorno
En el dashboard de Render:
- Environment → Environment Variables
- Añade estas variables:

```
OPENAI_API_KEY=sk-tu-api-key-aqui
STRIPE_SECRET_KEY=sk_test_tu-key-aqui
STRIPE_PUBLISHABLE_KEY=pk_test_tu-key-aqui
STRIPE_WEBHOOK_SECRET=whsec_tu-secret-aqui
ADMIN_KEY=tu-admin-secret-key
SECRET_KEY=tu-flask-secret-key
PYTHON_VERSION=3.11.0
```

### URL resultante
`https://contentkit-api.onrender.com`

---

## 📁 Estructura
```
├── app.py              # API Flask principal
├── requirements.txt    # Dependencias
├── render.yaml         # Configuración Render (opcional)
├── Procfile           # Comando de inicio
└── README.md          # Este archivo
```

---

## 🔄 Actualizaciones automáticas
Cada `git push` a main desencadena redeploy automático en Render.

---

## 💤 Limitación Free Tier
Render Free "se duerme" después de 15 min de inactividad:
- Primera petición tras inactividad: ~30-60s de espera
- Peticiones siguientes: normales
- Para producción real, considera upgrade a Starter ($7/mes)

---

## 🧪 Test local
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

API disponible en `http://localhost:5000`

---

## 📊 Admin Dashboard
Accede al panel de admin en:
`https://contentkit-api.onrender.com/api/admin/dashboard`

Header requerido: `X-Admin-Key: tu-admin-key`

---

*ContentKit Alpha - Backend API*
