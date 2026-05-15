import psycopg2
import hashlib
import datetime
import streamlit as st
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT, EMAIL_OTP_EXPIRY_MINUTES


def get_db_connection():
    """Establishes and returns a PostgreSQL database connection."""
    return psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER,
        password=DB_PASSWORD, port=DB_PORT
    )


def init_db():
    """Initializes the users table in the database if it doesn't exist."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                secret_key VARCHAR(255) NOT NULL
            )
        ''')
        c.execute('''CREATE TABLE IF NOT EXISTS email_otps (
            email VARCHAR(255) PRIMARY KEY, otp VARCHAR(10) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS vds_forms (
            email VARCHAR(255) PRIMARY KEY,
            form_data JSONB NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()


def save_vds_form(email, form_data):
    """Saves or updates the VDS form JSON for a user."""
    import json
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO vds_forms (email, form_data, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (email) DO UPDATE SET form_data = EXCLUDED.form_data, updated_at = CURRENT_TIMESTAMP",
            (email, json.dumps(form_data))
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error save_vds_form: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_vds_form(email):
    """Retrieves the VDS form JSON for a user."""
    import json
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT form_data FROM vds_forms WHERE email = %s", (email,))
        res = c.fetchone()
        if res:
            return res[0] if isinstance(res[0], dict) else json.loads(res[0])
        return {
            "billing_poc": {}, "technical_poc": {}, "server_count": 0,
            "servers_identical": False, "servers": [], "general": {}
        }
    except Exception as e:
        print(f"DB Error get_vds_form: {e}")
        return {
            "billing_poc": {}, "technical_poc": {}, "server_count": 0,
            "servers_identical": False, "servers": [], "general": {}
        }
    finally:
        if conn:
            conn.close()


def add_user(name, email, password, secret_key):
    """Adds a new user to the database."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (name, email, password, secret_key) VALUES (%s, %s, %s, %s)",
            (name, email, hashlib.sha256(password.encode()).hexdigest(), secret_key)
        )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        st.error("Email already registered.")
        return False
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_user(email, password):
    """Retrieves a user from the database by email and password."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM users WHERE email = %s AND password = %s",
            (email, hashlib.sha256(password.encode()).hexdigest())
        )
        return c.fetchone()
    except Exception as e:
        st.error(f"Error getting user: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_user_secret_key(email):
    """Retrieves the secret key for a user by email."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT secret_key FROM users WHERE email = %s", (email,))
        secret_key = c.fetchone()
        return secret_key[0] if secret_key else None
    except Exception as e:
        st.error(f"Error getting secret key: {e}")
        return None
    finally:
        if conn:
            conn.close()


def save_email_otp(email, otp):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=EMAIL_OTP_EXPIRY_MINUTES)
        c.execute(
            "INSERT INTO email_otps (email, otp, expires_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET otp = EXCLUDED.otp, expires_at = EXCLUDED.expires_at",
            (email, otp, expires_at)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def verify_email_otp(email, otp):
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT otp, expires_at FROM email_otps WHERE email = %s", (email,))
        res = c.fetchone()
        if res and res[0] == otp and res[1] > datetime.datetime.now():
            c.execute("DELETE FROM email_otps WHERE email = %s", (email,))
            conn.commit()
            return True
        return False
    except Exception:
        return False
    finally:
        if conn:
            conn.close()
