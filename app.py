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
from agent import create_nexus_agent, init_vds_form
# --- Page Configuration ---
st.set_page_config(
    page_title="NTC Nexus — Customer Support Portal",
    page_icon="🌐",
    layout="centered",
)

# --- Custom CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
[data-testid="stChatMessage"] { border-radius: 12px; margin-bottom: 0.5rem; }
</style>
""", unsafe_allow_html=True)


def main():
    init_db()
    init_vds_form()

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
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # =============================================
    # LOGGED IN — NEXUS CHAT
    # =============================================
    if st.session_state.logged_in:
        # Header
        st.markdown("---")
        st.markdown("## 🌐 NTC Nexus")
        st.caption("Customer Support Portal — National Telecommunication Corporation")
        st.markdown("---")

        # Sidebar
        with st.sidebar:
            st.markdown("### 🌐 Nexus Portal")
            st.markdown(f"**User:** {st.session_state.user_name}")
            st.markdown(f"**Email:** {st.session_state.user_email}")
            st.divider()
            st.markdown("### AI Configuration")
            st.session_state.hf_token = st.text_input(
                "Hugging Face Token", value=st.session_state.hf_token, type="password",
                help="Enter your Hugging Face Access Token to enable Nexus Agent."
            )

            # --- Debug Data Monitor ---
            with st.expander("🔍 Nexus Data Monitor", expanded=False):
                st.write("Current Form Data (Live from DB):")
                from db import get_vds_form
                db_form = get_vds_form(st.session_state.user_email)
                st.json(db_form)

            if st.session_state.hf_token:
                os.environ["HUGGINGFACEHUB_API_TOKEN"] = st.session_state.hf_token
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
            st.success("✅ VDS Proforma submitted! Download your copies:")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download PDF", data=st.session_state.generated_pdf,
                    file_name=f"VDS_Proforma_{timestamp}.pdf", mime="application/pdf",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    "📥 Download Excel", data=st.session_state.generated_excel,
                    file_name=f"VDS_Proforma_{timestamp}.xlsx",
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
        st.markdown("---")
        st.markdown("## 🌐 NTC Nexus")
        st.caption("Customer Support Portal — Sign in to continue")
        st.markdown("---")

        tab1, tab2 = st.tabs(["🔐 Sign In", "📝 Sign Up"])

        with tab1:
            st.subheader("Login to Your Account")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            otp_input = st.text_input("Enter OTP from Google Authenticator", type="password", key="login_otp")

            if st.button("Login", key="login_button", type="primary", use_container_width=True):
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
            st.subheader("Create New Account")
            if st.session_state.email_verification_pending:
                st.info(f"OTP sent to {st.session_state.pending_user_data['email']}")
                otp_input_reg = st.text_input("Enter Email OTP", key="reg_otp_input")
                if st.button("Verify & Register", key="verify_register_button", type="primary", use_container_width=True):
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
                reg_name = st.text_input("Name", key="reg_name")
                reg_email = st.text_input("Email", key="reg_email")
                reg_pwd = st.text_input("Password", type="password", key="reg_password")
                if st.button("Send OTP", key="send_otp_button", type="primary", use_container_width=True):
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