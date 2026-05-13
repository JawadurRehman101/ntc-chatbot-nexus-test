import streamlit as st
import psycopg2
import pyotp
import qrcode
from PIL import Image
import io
import hashlib
import os # For agent's HUGGINGFACEHUB_API_TOKEN
import datetime
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import ssl

# --- Imports for Agent ----
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
# --- End Imports for Agent ---


# --- Database connection details ---
# Using the full hostname as provided by Render for DB_HOST
DB_HOST = "dpg-d7ssbhgg4nts73e4o7mg-a.oregon-postgres.render.com"
DB_NAME = "demo_db_brb1"
DB_USER = "demo_db_brb1_user"
DB_PASSWORD = "dIbUkNpX5oAZxK2DtVHafYjWEtyLkxDJ"
DB_PORT = "5432"

# --- SMTP Configuration (keeping previous user's config) ---
SMTP_SERVER = "mail.ntc.org.pk"
SMTP_PORT = 587
SMTP_SENDER_EMAIL = "test.jawad@ntc.org.pk"
SMTP_USERNAME = "test.jawad@ntc.org.pk"
SMTP_PASSWORD = "16$secure@NTC"
EMAIL_OTP_EXPIRY_MINUTES = 5

def get_db_connection():
    """Establishes and returns a PostgreSQL database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

# --- Authentication Database Functions ---
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
        # Add email_otps table for email verification (from previous context)
        c.execute('''CREATE TABLE IF NOT EXISTS email_otps (email VARCHAR(255) PRIMARY KEY, otp VARCHAR(10) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NOT NULL)''')

        conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

def add_user(name, email, password, secret_key):
    """Adds a new user to the database."""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO users (name, email, password, secret_key) VALUES (%s, %s, %s, %s)",
                  (name, email, hashlib.sha256(password.encode()).hexdigest(), secret_key))
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
        c.execute("SELECT * FROM users WHERE email = %s AND password = %s",
                  (email, hashlib.sha256(password.encode()).hexdigest()))
        user = c.fetchone()
        return user
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
        c.execute("INSERT INTO email_otps (email, otp, expires_at) VALUES (%s, %s, %s) ON CONFLICT (email) DO UPDATE SET otp = EXCLUDED.otp, expires_at = EXCLUDED.expires_at", (email, otp, expires_at))
        conn.commit()
        return True
    except Exception: return False
    finally:
        if conn: conn.close()

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
    except Exception: return False
    finally:
        if conn: conn.close()

def send_email(receiver_email, subject, body_text):
    try:
        message = MIMEMultipart()
        message["From"] = SMTP_SENDER_EMAIL
        message["To"] = receiver_email
        message["Subject"] = subject
        message.attach(MIMEText(body_text, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_SENDER_EMAIL, receiver_email, message.as_string())
        return True
    except Exception as e:
        st.error(f"SMTP Error: {e}")
        return False


# --- Agent Definition (adapted for PostgreSQL) ---

class AgentState(TypedDict):
    """Represents the state of the agent's conversation."""
    messages: Annotated[list[AnyMessage], add_messages]

@tool
def check_user_registration_agent(email: str) -> str:
    """Checks if a user is registered with Firm using their email address.
    Call this tool whenever the user asks if they are registered or authenticated.
    Uses the shared PostgreSQL database."""
    conn = None
    try:
        conn = get_db_connection() # Use the shared PostgreSQL connection
        cursor = conn.cursor()

        # Check if user exists in the 'users' table
        cursor.execute("SELECT name FROM users WHERE email = %s", (email,))
        result = cursor.fetchone()

        conn.close()

        if result:
            name = result[0]
            # The original agent code had 'status'. For simplicity, we'll assume 'Active'.
            return f"User '{name}' is registered with Firm. Account status: Active."
        else:
            return "User not found in the Firm database. They are not registered."
    except Exception as e:
        return f"Error accessing the database: {str(e)}"

def create_agent():
    """Initializes the Hugging Face LLM and compiles the LangGraph agent."""
    hf_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN") # Retrieve token from environment variable
    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN is not set in the environment. Please configure it in the sidebar.")

    endpoint = HuggingFaceEndpoint(
        repo_id="Qwen/Qwen2.5-7B-Instruct",
        task="text-generation",
        max_new_tokens=512,
        temperature=0.1,
        huggingfacehub_api_token=hf_token # Pass token directly for robustness
    )
    llm = ChatHuggingFace(llm=endpoint)

    tools = [check_user_registration_agent] # Use the PostgreSQL-adapted tool
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    def should_continue(state: AgentState) -> str:
        messages = state['messages']
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    return workflow.compile()

# --- Streamlit App Logic (Combined) ---
def main():
    init_db() # Initialize DB for auth users table on app start

    # Initialize session state variables if they don't exist
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'email_verification_pending' not in st.session_state: st.session_state.email_verification_pending = False
    if 'pending_user_data' not in st.session_state: st.session_state.pending_user_data = {}
    if 'user_email' not in st.session_state:
        st.session_state.user_email = None
    if 'hf_token' not in st.session_state: # To store HF token for agent
        st.session_state.hf_token = ""
    if "agent_messages" not in st.session_state: # Agent's chat history
        st.session_state.agent_messages = []


    st.title("?? OTP Authentication & AI Assistant App")

    # --- Sidebar for HF Token Configuration ---
    with st.sidebar:
        st.header("AI Assistant Configuration")
        hf_token_input = st.text_input("Hugging Face Access Token", type="password", value=st.session_state.hf_token)
        if hf_token_input:
            st.session_state.hf_token = hf_token_input
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = hf_token_input # Set env var for agent
        st.markdown("Create an Access Token in your Hugging Face account (Settings -> Access Tokens).")

    if st.session_state.logged_in:
        st.subheader(f"Welcome, {st.session_state.user_email}! You are logged in.")
        st.write("---") # Separator

        # --- Display Agent Chat Interface ---
        st.subheader("Your AI Assistant")

        # Display chat history for the agent
        for message in st.session_state.agent_messages:
            if isinstance(message, HumanMessage):
                with st.chat_message("user"):
                    st.markdown(message.content)
            elif isinstance(message, AIMessage):
                # Only display final AI response, not intermediate tool calls
                if not getattr(message, "tool_calls", None):
                    with st.chat_message("assistant"):
                        st.markdown(message.content)

        # Agent Chat Input
        agent_prompt = st.chat_input("Ask your AI Assistant:")

        if agent_prompt:
            if not st.session_state.hf_token:
                st.error("Please enter your Hugging Face Access Token in the sidebar first to use the AI Assistant.")
            else:
                try:
                    # Initialize the LangGraph agent
                    agent_executor = create_agent()

                    # Add user input to agent's state and display it
                    st.session_state.agent_messages.append(HumanMessage(content=agent_prompt))
                    with st.chat_message("user"):
                        st.markdown(agent_prompt)

                    # Process the response
                    with st.chat_message("assistant"):
                        with st.spinner("AI Assistant is thinking..."):
                            # Pass the entire agent message history to LangGraph
                            response = agent_executor.invoke({"messages": st.session_state.agent_messages})

                            # Update session state with the full conversation
                            st.session_state.agent_messages = response["messages"]

                            # Display the final AI response
                            final_response_content = ""
                            if st.session_state.agent_messages and isinstance(st.session_state.agent_messages[-1], AIMessage):
                                final_response_content = st.session_state.agent_messages[-1].content
                            st.markdown(final_response_content)

                except ValueError as ve:
                    st.error(f"Configuration Error: {ve}")
                except Exception as e:
                    st.error(f"An error occurred with the AI Assistant: {str(e)}")
        
        st.write("---")
        if st.button("Logout from App"):
            st.session_state.logged_in = False
            st.session_state.user_email = None
            st.session_state.hf_token = "" # Clear HF token on logout
            st.session_state.agent_messages = [] # Clear agent chat history
            st.rerun()

    else: # Not logged in, show authentication forms
        tab1, tab2 = st.tabs(["Sign In", "Sign Up"])

        with tab1:
            st.subheader("Login to Your Account")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type='password', key="login_password")
            otp_input = st.text_input("Enter OTP from Google Authenticator", type='password', key="login_otp")

            if st.button("Login", key="login_button"):
                user = get_user(email, password)
                if user:
                    secret_key_from_db = get_user_secret_key(email)
                    if secret_key_from_db:
                        totp = pyotp.TOTP(secret_key_from_db)
                        if totp.verify(otp_input):
                            st.session_state.logged_in = True
                            st.session_state.user_email = email
                            st.success("Logged in successfully!")
                            st.rerun()
                        else:
                            st.error("Invalid OTP. Access denied.")
                    else:
                        st.error("Error retrieving secret key.")
                else:
                    st.error("Invalid Email or Password.")

        with tab2:
            st.subheader("Create New Account")
            if st.session_state.email_verification_pending:
                st.info(f"OTP sent to {st.session_state.pending_user_data['email']}")
                otp_input_reg = st.text_input("Enter Email OTP", key="reg_otp_input")
                if st.button("Verify & Register", key="verify_register_button"):
                    if verify_email_otp(st.session_state.pending_user_data['email'], otp_input_reg):
                        secret = pyotp.random_base32()
                        if add_user(st.session_state.pending_user_data['name'], st.session_state.pending_user_data['email'], st.session_state.pending_user_data['password'], secret):
                            st.success("Registration complete!")
                            totp = pyotp.TOTP(secret)
                            provisioning_uri = totp.provisioning_uri(name=st.session_state.pending_user_data['email'], issuer_name="NTC_OTP_App")
                            qr_img = qrcode.make(provisioning_uri)
                            buf = io.BytesIO()
                            qr_img.save(buf, format='PNG')
                            st.image(buf.getvalue(), caption="Scan this with Google Authenticator", use_column_width=True)
                            st.write(f"Manual Key: `{secret}`")
                            st.session_state.email_verification_pending = False
                            st.session_state.pending_user_data = {}
                        else: st.error("Error creating user.")
                    else: st.error("Invalid or expired OTP.")
            else:
                reg_name = st.text_input("Name", key="reg_name")
                reg_email = st.text_input("Email", key="reg_email")
                reg_pwd = st.text_input("Password", type="password", key="reg_password")
                if st.button("Send OTP", key="send_otp_button"):
                    if reg_name and reg_email and reg_pwd:
                        otp_val = f"{random.randint(100000, 999999)}"
                        if save_email_otp(reg_email, otp_val) and send_email(reg_email, "Verify Your Email", f"Your OTP is: {otp_val}"):
                            st.session_state.pending_user_data = {'name': reg_name, 'email': reg_email, 'password': reg_pwd}
                            st.session_state.email_verification_pending = True
                            st.rerun()
                        else:
                            st.error("Failed to send OTP. Please check email address or SMTP configuration.")
                    else:
                        st.error("Please fill in all fields for registration.")

if __name__ == '__main__':
    main()