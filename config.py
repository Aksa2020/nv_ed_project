import streamlit as st

# Groq API Configuration
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY")

# Database Configuration
DB_CONFIG = {
    "host": st.secrets.get("DB_HOST"),
    "port": st.secrets.get("DB_PORT"),
    "database": st.secrets.get("DB_NAME"),
    "user": st.secrets.get("DB_USER"),
    "password": st.secrets.get("DB_PASSWORD")
}

# Image API Base URL
BASE_URL = st.secrets.get("BASE_URL")

# Validate required secrets
def validate_secrets():
    """Validate that all required secrets are configured"""
    required_secrets = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "DB_HOST": DB_CONFIG["host"],
        "DB_NAME": DB_CONFIG["database"],
        "DB_USER": DB_CONFIG["user"],
        "DB_PASSWORD": DB_CONFIG["password"],
        "BASE_URL": BASE_URL
    }
    
    missing = [key for key, value in required_secrets.items() if not value]
    
    if missing:
        st.error(f"❌ Missing required secrets: {', '.join(missing)}")
        st.info("Please add these secrets to your .streamlit/secrets.toml file or Streamlit Cloud settings")
        st.stop()

# Call validation on import (optional - comment out if you want manual control)
# validate_secrets()



