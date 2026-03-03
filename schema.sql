-- PostgreSQL schema for ContentKit Alpha

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    plan_id VARCHAR(50) DEFAULT 'starter',
    subscription_status VARCHAR(50) DEFAULT 'active',
    posts_allowed INTEGER DEFAULT 4,
    posts_used_this_period INTEGER DEFAULT 0,
    sessions_allowed INTEGER DEFAULT 0,
    sessions_used_this_period INTEGER DEFAULT 0,
    current_period_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_period_end TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '30 days',
    demo_mode BOOLEAN DEFAULT false,
    onboarding_completed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Posts table
CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'ready',
    post_type VARCHAR(50),
    brief TEXT,
    platform VARCHAR(50),
    format VARCHAR(50),
    tone VARCHAR(50),
    generated_image_url TEXT,
    generated_prompt TEXT,
    generated_copy TEXT,
    generated_hashtags TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    downloaded_at TIMESTAMP
);

-- Sessions (professional sessions with Alberto)
CREATE TABLE IF NOT EXISTS pro_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) DEFAULT 'strategy_review',
    status VARCHAR(50) DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scheduled_at TIMESTAMP,
    meeting_link TEXT,
    notes TEXT,
    user_message TEXT
);

-- User reference images (for onboarding)
CREATE TABLE IF NOT EXISTS user_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    image_type VARCHAR(50) NOT NULL, -- 'space' or 'product'
    image_url TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User onboarding data
CREATE TABLE IF NOT EXISTS onboarding_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    objective VARCHAR(255), -- 'clients', 'visits', 'authority', 'image'
    industry VARCHAR(255),
    tone_preference VARCHAR(50),
    ai_analysis_report TEXT,
    completed_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON pro_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_images_user_id ON user_images(user_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_user_id ON onboarding_data(user_id);
