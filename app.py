import streamlit as st
import pyotp
import qrcode
import io
import os
import random
import datetime

from langchain_core.messages import HumanMessage, AIMessage

from db import init_db, add_user, get_user, get_user_secret_key, save_email_otp, verify_email_otp
from email_utils import send_email
from agent import create_nexus_agent, init_vds_form, init_colocation_form

# --- Page Configuration ---
st.set_page_config(
    page_title="NTC Nexus — Customer Support Portal",
    page_icon="🌐",
    layout="centered",
)

# --- Load External CSS ---
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "styles.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# --- SVG Icons ---
GLOBE_SVG = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>'

# --- UI Component Helpers ---
def render_auth_header():
    st.markdown(f"""
    <div class="nexus-bg-orbs">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    </div>
    <div class="nexus-auth-header">
        <div class="nexus-logo-icon">{GLOBE_SVG}</div>
        <h1>NTC Nexus</h1>
        <p class="nexus-subtitle">Smart Customer Support Portal — National Telecommunication Corporation</p>
    </div>
    """, unsafe_allow_html=True)

def render_auth_footer():
    st.markdown("""
    <div class="nexus-features">
        <span class="nexus-feature-pill">🔒 Secure 2FA</span>
        <span class="nexus-feature-pill">⚡ AI-Powered</span>
        <span class="nexus-feature-pill">🌐 24/7 Support</span>
        <span class="nexus-feature-pill">📋 VDS Services</span>
    </div>
    <div class="nexus-footer">
        <span class="nexus-footer-badge">🌐 Powered by NTC Pakistan — Connecting the Nation</span>
    </div>
    """, unsafe_allow_html=True)

def render_chat_header():
    st.markdown(f"""
    <div class="nexus-chat-header">
        <div class="header-content">
            <div class="header-icon">{GLOBE_SVG}</div>
            <div>
                <h2>NTC Nexus</h2>
                <div class="header-sub">Customer Support Portal — National Telecommunication Corporation</div>
            </div>
            <div class="status-badge">
                <span class="status-dot"></span>
                Online
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar_user(name, email):
    initial = name[0].upper() if name else "U"
    st.markdown(f"""
    <div class="sidebar-user-card">
        <div class="user-avatar">{initial}</div>
        <div class="user-name">{name}</div>
        <div class="user-email">{email}</div>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar_links():
    st.markdown("""
    <div class="sidebar-quick-links">
        <div class="sidebar-quick-link">📞 Helpline: 1218</div>
        <div class="sidebar-quick-link">📧 info@ntc.net.pk</div>
        <div class="sidebar-quick-link">🌐 www.ntc.net.pk</div>
    </div>
    """, unsafe_allow_html=True)


def main():
    init_db()
    init_vds_form()
    init_colocation_form()

    # --- Session State Defaults ---
    defaults = {
        "logged_in": False,
        "email_verification_pending": False,
        "pending_user_data": {},
        "user_email": None,
        "user_name": None,
        "hf_token": "",
        "agent_messages": [],  # LangGraph message history
        "form_submitted": False,
        "generated_pdf": None,
        "generated_excel": None,
        "submitted_service_type": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # =============================================
    # LOGGED IN — NEXUS CHAT
    # =============================================
    if st.session_state.logged_in:
        # Chat Header
        render_chat_header()

        # Sidebar
        with st.sidebar:
            st.markdown("### 🌐 Nexus Portal")
            render_sidebar_user(st.session_state.user_name, st.session_state.user_email)
            st.divider()
            st.markdown("### ⚙️ AI Configuration")
            st.session_state.hf_token = st.text_input(
                "Hugging Face Token", value=st.session_state.hf_token, type="password",
                help="Enter your Hugging Face Access Token to enable Nexus Agent."
            )

            # --- Debug Data Monitor ---
            with st.expander("🔍 Nexus Data Monitor", expanded=False):
                st.write("Current VDS Form (Live from DB):")
                from db import get_vds_form, get_colocation_form
                db_form = get_vds_form(st.session_state.user_email)
                st.json(db_form)
                st.write("Current Colocation Form (Live from DB):")
                db_colo = get_colocation_form(st.session_state.user_email)
                st.json(db_colo)

            if st.session_state.hf_token:
                os.environ["HUGGINGFACEHUB_API_TOKEN"] = st.session_state.hf_token
            st.divider()
            st.markdown("### 🔗 Quick Links")
            render_sidebar_links()
            st.divider()
            if st.button("🚪 Logout", use_container_width=True):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()

        # Greeting (first time after login)
        if not st.session_state.agent_messages:
            greeting = (
                f"Hello **{st.session_state.user_name}**! 👋\n\n"
                "This is **Nexus** — your NTC Customer Support Agent. "
                "How may I help you today?"
            )
            st.session_state.agent_messages.append(AIMessage(content=greeting))

        # Display chat history
        for msg in st.session_state.agent_messages:
            if isinstance(msg, HumanMessage):
                with st.chat_message("user"):
                    st.markdown(msg.content)
            elif isinstance(msg, AIMessage):
                if not getattr(msg, "tool_calls", None):
                    with st.chat_message("assistant", avatar="🌐"):
                        st.markdown(msg.content)

        # Download buttons if form was submitted
        if st.session_state.form_submitted and st.session_state.generated_pdf:
            st.markdown("---")
            service_type = st.session_state.get("submitted_service_type", "vds")
            if service_type == "colocation":
                label = "Colocation Request"
                file_prefix = "Colocation_Request"
            else:
                label = "VDS Proforma"
                file_prefix = "VDS_Proforma"
                
            st.success(f"✅ {label} submitted! Download your copies:")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download PDF", data=st.session_state.generated_pdf,
                    file_name=f"{file_prefix}_{timestamp}.pdf", mime="application/pdf",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    "📥 Download Excel", data=st.session_state.generated_excel,
                    file_name=f"{file_prefix}_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            st.markdown("---")

        # Suggestion buttons (only when chat just has greeting)
        if len(st.session_state.agent_messages) <= 1:
            suggestions = [
                "What services does NTC provide?",
                "How to lodge a complaint against existing services?",
                "I want to subscribe to a new service",
            ]
            cols = st.columns(len(suggestions))
            for i, (col, sug) in enumerate(zip(cols, suggestions)):
                with col:
                    if st.button(sug, key=f"sug_{i}", type="secondary", use_container_width=True):
                        st.session_state._pending_suggestion = sug
                        st.rerun()

        # Handle pending suggestion
        pending = st.session_state.get("_pending_suggestion")
        if pending:
            del st.session_state._pending_suggestion
            _process_user_input(pending)

        # Chat input
        if user_input := st.chat_input("Type your message to Nexus..."):
            _process_user_input(user_input)

    # =============================================
    # NOT LOGGED IN — AUTH
    # =============================================
    else:
        render_auth_header()

        tab1, tab2 = st.tabs(["🔐 Sign In", "📝 Sign Up"])

        with tab1:
            st.markdown("#### 👋 Welcome Back")
            st.caption("Sign in to access your NTC Nexus portal")
            email = st.text_input("Email Address", key="login_email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
            otp_input = st.text_input("Google Authenticator OTP", type="password", key="login_otp", placeholder="6-digit code")

            if st.button("Sign In →", key="login_button", type="primary", use_container_width=True):
                user = get_user(email, password)
                if user:
                    secret_key_from_db = get_user_secret_key(email)
                    if secret_key_from_db:
                        totp = pyotp.TOTP(secret_key_from_db)
                        if totp.verify(otp_input):
                            st.session_state.logged_in = True
                            st.session_state.user_email = email
                            st.session_state.user_name = user[1]
                            st.session_state.agent_messages = []
                            st.success("Logged in successfully!")
                            st.rerun()
                        else:
                            st.error("Invalid OTP. Access denied.")
                    else:
                        st.error("Error retrieving secret key.")
                else:
                    st.error("Invalid Email or Password.")

        with tab2:
            st.markdown("#### ✨ Create Account")
            st.caption("Join NTC Nexus for smart customer support")
            if st.session_state.email_verification_pending:
                st.info(f"OTP sent to {st.session_state.pending_user_data['email']}")
                otp_input_reg = st.text_input("Enter Email OTP", key="reg_otp_input", placeholder="6-digit verification code")
                if st.button("Verify & Register →", key="verify_register_button", type="primary", use_container_width=True):
                    if verify_email_otp(st.session_state.pending_user_data["email"], otp_input_reg):
                        secret = pyotp.random_base32()
                        if add_user(
                            st.session_state.pending_user_data["name"],
                            st.session_state.pending_user_data["email"],
                            st.session_state.pending_user_data["password"],
                            secret,
                        ):
                            st.success("Registration complete!")
                            totp = pyotp.TOTP(secret)
                            uri = totp.provisioning_uri(
                                name=st.session_state.pending_user_data["email"],
                                issuer_name="NTC_Nexus_Portal",
                            )
                            import qrcode.image.pil
                            qr_img = qrcode.make(uri, image_factory=qrcode.image.pil.PilImage)
                            buf = io.BytesIO()
                            qr_img.save(buf, format="PNG")
                            st.image(buf.getvalue(), caption="Scan with Google Authenticator", use_column_width=True)
                            st.write(f"Manual Key: `{secret}`")
                            st.session_state.email_verification_pending = False
                            st.session_state.pending_user_data = {}
                        else:
                            st.error("Error creating user.")
                    else:
                        st.error("Invalid or expired OTP.")
            else:
                reg_name = st.text_input("Full Name", key="reg_name", placeholder="Your full name")
                reg_email = st.text_input("Email Address", key="reg_email", placeholder="you@example.com")
                reg_pwd = st.text_input("Password", type="password", key="reg_password", placeholder="Create a strong password")
                if st.button("Send OTP →", key="send_otp_button", type="primary", use_container_width=True):
                    if reg_name and reg_email and reg_pwd:
                        otp_val = f"{random.randint(100000, 999999)}"
                        if save_email_otp(reg_email, otp_val) and send_email(
                            reg_email, "Verify Your Email — NTC Nexus", f"Your OTP is: {otp_val}"
                        ):
                            st.session_state.pending_user_data = {"name": reg_name, "email": reg_email, "password": reg_pwd}
                            st.session_state.email_verification_pending = True
                            st.rerun()
                        else:
                            st.error("Failed to send OTP.")
                    else:
                        st.error("Please fill in all fields.")

        render_auth_footer()


def _process_user_input(user_input: str):
    """Send user input to the LangGraph Nexus agent and display response."""
    if not st.session_state.hf_token:
        st.error("⚠️ Please enter your Hugging Face Access Token in the sidebar to use Nexus.")
        return

    # Add user message
    st.session_state.agent_messages.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call agent
    with st.chat_message("assistant", avatar="🌐"):
        with st.spinner("Nexus is thinking..."):
            try:
                agent = create_nexus_agent()
                config = {"configurable": {
                    "user_email": st.session_state.user_email, 
                    "user_name": st.session_state.user_name
                }}
                result = agent.invoke({"messages": st.session_state.agent_messages}, config=config)
                st.session_state.agent_messages = result["messages"]

                # Display final AI response
                final = ""
                if st.session_state.agent_messages and isinstance(st.session_state.agent_messages[-1], AIMessage):
                    final = st.session_state.agent_messages[-1].content
                st.markdown(final)
            except ValueError as ve:
                st.error(f"Configuration Error: {ve}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

    st.rerun()


if __name__ == "__main__":
    main()