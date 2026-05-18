"""
Nexus Conversational Engine — State-machine driven form-filling flow
for NTC IaaS VDS (Virtual Dedicated Server) service.
"""
import streamlit as st
from config import (
    NTC_SERVICES, FORM_SECTIONS, SERVER_DETAIL_FIELDS,
    STORAGE_TYPES, BILLING_POC_FIELDS, TECHNICAL_POC_FIELDS,
    GENERAL_DETAIL_FIELDS,
)


def init_nexus_state():
    """Initialize all Nexus-related session state variables."""
    defaults = {
        "user_name": None,
        "nexus_messages": [],
        "nexus_phase": "init",
        "field_index": 0,
        "vds_form": {},
        "server_count": 0,
        "servers_identical": None,
        "current_server_idx": 0,
        "pending_input": None,
        "form_submitted": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def add_message(role, content):
    """Add a message to the Nexus chat history."""
    st.session_state.nexus_messages.append({"role": role, "content": content})


def reset_vds_form():
    """Reset VDS form data for a new submission."""
    st.session_state.vds_form = {
        "billing_poc": {},
        "technical_poc": {},
        "servers": [],
        "server_count": 0,
        "servers_identical": None,
        "general": {},
    }
    st.session_state.field_index = 0
    st.session_state.server_count = 0
    st.session_state.servers_identical = None
    st.session_state.current_server_idx = 0
    st.session_state.form_submitted = False


def get_services_message():
    """Return a formatted string listing NTC services."""
    lines = ["Here are the services offered by **NTC**:\n"]
    for i, svc in enumerate(NTC_SERVICES, 1):
        status = "✅ Available" if svc["available"] else "🔜 Coming Soon"
        lines.append(f"**{i}.** {svc['name']}  —  {status}")
    lines.append("\nCurrently, I can assist you with **IaaS VDS (Virtual Dedicated Server)** service. Would you like to proceed with VDS?")
    return "\n".join(lines)


def get_section_intro(phase):
    """Return an intro message for a form section."""
    if phase == "vds_billing":
        return "Great! Let's start filling out the **VDS Service Proforma**.\n\n📋 **Section 1: Billing POC Details**\n\nPlease provide the **Full Name** of the Billing Point of Contact:"
    elif phase == "vds_technical":
        return "✅ Billing POC details saved!\n\n📋 **Section 2: Technical POC Details**\n\nPlease provide the **Full Name** of the Technical Point of Contact:"
    elif phase == "vds_server_count":
        return "✅ Technical POC details saved!\n\n📋 **Section 3: Server Details**\n\nHow many servers do you need?"
    elif phase == "vds_server_type":
        return "Will all servers have **identical** (same) or **unique** (different) configurations?\n\nPlease type **identical** or **unique**:"
    elif phase == "vds_server_details":
        idx = st.session_state.current_server_idx
        total = st.session_state.server_count
        identical = st.session_state.servers_identical
        if identical:
            prefix = f"Please provide the server configuration (will be applied to all {total} servers)."
        else:
            prefix = f"Please provide configuration for **Server {idx + 1} of {total}**."
        field_key, field_label = SERVER_DETAIL_FIELDS[0]
        return f"{prefix}\n\nPlease enter the **{field_label}**:"
    elif phase == "vds_general":
        return "✅ Server details saved!\n\n📋 **Section 4: General Details**\n\nPlease provide the **Purpose / Use Case for the server(s)**:"
    elif phase == "vds_review":
        return build_review_message()
    return ""


def build_review_message():
    """Build a formatted review of the complete VDS form."""
    form = st.session_state.vds_form
    lines = ["📝 **VDS Service Proforma — Review**\n"]
    lines.append("---")

    # Billing POC
    lines.append("### Section 1: Billing POC Details")
    billing = form.get("billing_poc", {})
    for key, label in BILLING_POC_FIELDS:
        lines.append(f"- **{label}:** {billing.get(key, 'N/A')}")

    lines.append("\n### Section 2: Technical POC Details")
    tech = form.get("technical_poc", {})
    for key, label in TECHNICAL_POC_FIELDS:
        lines.append(f"- **{label}:** {tech.get(key, 'N/A')}")

    lines.append(f"\n### Section 3: Server Details")
    lines.append(f"- **Total Servers:** {form.get('server_count', 0)}")
    lines.append(f"- **Configuration:** {'Identical' if form.get('servers_identical') else 'Unique'}")
    servers = form.get("servers", [])
    for i, srv in enumerate(servers):
        lines.append(f"\n**Server {i + 1}:**")
        for key, label in SERVER_DETAIL_FIELDS:
            lines.append(f"  - {label}: {srv.get(key, 'N/A')}")

    lines.append("\n### Section 4: General Details")
    general = form.get("general", {})
    for key, label in GENERAL_DETAIL_FIELDS:
        lines.append(f"- **{label}:** {general.get(key, 'N/A')}")

    lines.append("\n---")
    lines.append("Please review the above details. Type **submit** to confirm, or **edit** to make changes.")
    return "\n".join(lines)


def process_nexus_input(user_input):
    """Process user input based on current phase. Returns the assistant response string."""
    phase = st.session_state.nexus_phase
    text = user_input.strip()
    lower = text.lower()

    # --- IDLE PHASE ---
    if phase == "idle":
        if any(kw in lower for kw in ["service", "provide", "offer", "what do you"]):
            return get_services_message()
        elif any(kw in lower for kw in ["vds", "virtual dedicated", "iaas", "server service", "subscribe", "new service"]):
            reset_vds_form()
            st.session_state.nexus_phase = "vds_billing"
            st.session_state.field_index = 0
            return get_section_intro("vds_billing")
        elif any(kw in lower for kw in ["complaint", "lodge", "issue", "problem"]):
            return "I understand you'd like to lodge a complaint. This feature is coming soon in a future update. For immediate assistance, please call our helpline at **1218** or email **info@ntc.net.pk**."
        else:
            return "I'm here to help! I can tell you about NTC services or assist you in subscribing to our **IaaS VDS (Virtual Dedicated Server)** service. What would you like to do?"

    # --- BILLING / TECHNICAL / GENERAL POC FIELDS ---
    if phase in FORM_SECTIONS:
        section = FORM_SECTIONS[phase]
        field_idx = st.session_state.field_index
        fields = section["fields"]
        field_key, _ = fields[field_idx]

        # Store the answer
        if section["data_key"] not in st.session_state.vds_form:
            st.session_state.vds_form[section["data_key"]] = {}
        st.session_state.vds_form[section["data_key"]][field_key] = text

        # Move to next field
        st.session_state.field_index += 1

        if st.session_state.field_index < len(fields):
            next_key, next_label = fields[st.session_state.field_index]
            return f"Please provide the **{next_label}**:"
        else:
            # Section complete
            st.session_state.field_index = 0
            next_phase = section["next_phase"]
            st.session_state.nexus_phase = next_phase
            return get_section_intro(next_phase)

    # --- SERVER COUNT ---
    if phase == "vds_server_count":
        try:
            count = int(text)
            if count < 1:
                return "Please enter a valid number (at least 1):"
            st.session_state.server_count = count
            st.session_state.vds_form["server_count"] = count
            if count == 1:
                st.session_state.servers_identical = True
                st.session_state.vds_form["servers_identical"] = True
                st.session_state.nexus_phase = "vds_server_details"
                st.session_state.field_index = 0
                st.session_state.current_server_idx = 0
                return get_section_intro("vds_server_details")
            else:
                st.session_state.nexus_phase = "vds_server_type"
                return get_section_intro("vds_server_type")
        except ValueError:
            return "Please enter a valid number for the server count:"

    # --- SERVER TYPE (identical/unique) ---
    if phase == "vds_server_type":
        if "identical" in lower or "same" in lower:
            st.session_state.servers_identical = True
            st.session_state.vds_form["servers_identical"] = True
        elif "unique" in lower or "different" in lower:
            st.session_state.servers_identical = False
            st.session_state.vds_form["servers_identical"] = False
        else:
            return "Please type **identical** or **unique**:"

        st.session_state.nexus_phase = "vds_server_details"
        st.session_state.field_index = 0
        st.session_state.current_server_idx = 0
        return get_section_intro("vds_server_details")

    # --- SERVER DETAILS ---
    if phase == "vds_server_details":
        field_idx = st.session_state.field_index
        srv_idx = st.session_state.current_server_idx
        field_key, field_label = SERVER_DETAIL_FIELDS[field_idx]

        # Validate storage type
        if field_key == "storage_type":
            matched = None
            for st_type in STORAGE_TYPES:
                if st_type.lower() == lower or st_type.lower() in lower:
                    matched = st_type
                    break
            if not matched:
                return f"Please select a valid storage type: **{' / '.join(STORAGE_TYPES)}**"
            text = matched

        # Initialize server list if needed
        while len(st.session_state.vds_form.get("servers", [])) <= srv_idx:
            st.session_state.vds_form.setdefault("servers", []).append({})

        st.session_state.vds_form["servers"][srv_idx][field_key] = text
        st.session_state.field_index += 1

        if st.session_state.field_index < len(SERVER_DETAIL_FIELDS):
            next_key, next_label = SERVER_DETAIL_FIELDS[st.session_state.field_index]
            if next_key == "storage_type":
                next_label += f"\n\nAvailable types: **{' / '.join(STORAGE_TYPES)}**"
            return f"Please enter the **{next_label}**:"
        else:
            # Current server done
            if st.session_state.servers_identical:
                # Copy to all servers
                template = st.session_state.vds_form["servers"][0].copy()
                st.session_state.vds_form["servers"] = [
                    template.copy() for _ in range(st.session_state.server_count)
                ]
                st.session_state.nexus_phase = "vds_general"
                st.session_state.field_index = 0
                return get_section_intro("vds_general")
            else:
                st.session_state.current_server_idx += 1
                if st.session_state.current_server_idx < st.session_state.server_count:
                    st.session_state.field_index = 0
                    return get_section_intro("vds_server_details")
                else:
                    st.session_state.nexus_phase = "vds_general"
                    st.session_state.field_index = 0
                    return get_section_intro("vds_general")

    # --- REVIEW ---
    if phase == "vds_review":
        if "submit" in lower or "confirm" in lower or "yes" in lower:
            st.session_state.nexus_phase = "vds_submitted"
            return "__SUBMIT__"  # Special signal handled by UI
        elif "edit" in lower or "change" in lower:
            st.session_state.nexus_phase = "vds_edit_select"
            return (
                "Which section would you like to edit?\n\n"
                "1. Billing POC Details\n"
                "2. Technical POC Details\n"
                "3. Server Details\n"
                "4. General Details\n\n"
                "Please enter the section number:"
            )
        else:
            return "Please type **submit** to confirm the form, or **edit** to make changes."

    # --- EDIT SELECT ---
    if phase == "vds_edit_select":
        section_map = {"1": "vds_billing", "2": "vds_technical", "3": "vds_server_count", "4": "vds_general"}
        if text in section_map:
            target = section_map[text]
            st.session_state.nexus_phase = target
            st.session_state.field_index = 0
            if target == "vds_server_count":
                st.session_state.current_server_idx = 0
                st.session_state.vds_form["servers"] = []
            return get_section_intro(target)
        else:
            return "Please enter a number between 1 and 4:"

    return "I'm sorry, I didn't understand that. Could you please try again?"
