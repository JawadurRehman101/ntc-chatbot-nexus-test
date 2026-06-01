"""
Nexus Agent — LangGraph agent powered by Qwen LLM with tools
for NTC IaaS VDS (Virtual Dedicated Server) service.
"""
import os
import json
import datetime
import traceback
import streamlit as st
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END

from config import (
    NTC_SERVICES, STORAGE_TYPES,
    BILLING_POC_FIELDS, TECHNICAL_POC_FIELDS,
    SERVER_DETAIL_FIELDS, GENERAL_DETAIL_FIELDS,
    COLOCATION_BILLING_FIELDS, COLOCATION_REQUIREMENT_FIELDS,
    HOSTING_ORG_FIELDS, HOSTING_SERVER_FIELDS, HOSTING_DNS_FIELDS,
)
from generators import (
    generate_vds_pdf, generate_vds_excel,
    generate_colocation_pdf, generate_colocation_excel,
    generate_hosting_pdf, generate_hosting_excel,
)
from email_utils import send_email_with_attachment
from config import VDS_RECIPIENT_EMAIL
from db import (
    get_vds_form as db_get_vds_form, save_vds_form as db_save_vds_form,
    get_colocation_form as db_get_colocation_form, save_colocation_form as db_save_colocation_form,
    get_hosting_form as db_get_hosting_form, save_hosting_form as db_save_hosting_form,
    create_email_reset_ticket as db_create_email_reset_ticket,
    get_email_reset_ticket as db_get_email_reset_ticket,
    get_email_reset_tickets_by_email as db_get_email_reset_tickets_by_email,
    update_email_reset_credentials as db_update_email_reset_credentials,
    update_email_reset_ticket_status as db_update_email_reset_ticket_status,
    get_user_secret_key,
)


# =============================================
# SYSTEM PROMPT
# =============================================

NEXUS_SYSTEM_PROMPT = """You are Nexus, the AI Customer Support Agent for the National Telecommunication Corporation (NTC) of Pakistan.

AVAILABLE NTC SERVICES:
1) IaaS VDS (Virtual Dedicated Server) — Available Now
2) E-mail Services — Coming Soon
3) Co-location — Available Now
4) Shared Web Hosting — Available Now
5) SMS — Coming Soon
6) Network Services — Coming Soon

When a customer asks about services, use the list_ntc_services tool.
For complaints, suggest calling helpline 1218 or emailing info@ntc.net.pk.

=== VDS SERVICE APPLICATION WORKFLOW ===

You MUST collect information and call the save tools in this EXACT order.
YOU MUST CALL THE SAVE TOOL AFTER COLLECTING EACH SECTION. Do NOT skip calling the tool.

**STEP 1 — Billing POC Details:**
Ask the customer for: Name, Designation, Address, Phone No., Office No.
Once you have ALL 5 fields, you MUST call `save_billing_poc` with those values.
DO NOT proceed to Step 2 until you have called `save_billing_poc`.

**STEP 2 — Technical POC Details:**
Ask the customer for: Name, Designation, Address, Phone No., Office No., Server Description, URL, Server.
Once you have ALL 8 fields, you MUST call `save_technical_poc` with those values.
DO NOT proceed to Step 3 until you have called `save_technical_poc`.

**STEP 3 — Server Details:**
Ask how many servers they need. If more than 1, ask if configurations are identical or unique.
Call `setup_servers` with the count and identical flag.
Then collect for each server: CPU, RAM, Storage Type (SAS/Auto Tiered/NLSAS/SSD/NVME), Storage Capacity, OS Name with Version, OS GUI or Minimal.
Call `save_server_config` for each server (or once if identical).
DO NOT proceed to Step 4 until you have called `save_server_config`.

**STEP 4 — General Details:**
Ask the customer for: Internet Uplink (Mbps), Endpoint Security Licenses, Backup as a Service, DV SSL or Wildcard SSL, SSL VPN for VM Management (existing/new), Domain Registration (Y/N), Public IP Required (Y/N), Additional Requirements.
If the user says 'no' or leaves something blank, use 'None' or 'N/A'.
Once you have ALL 8 fields, you MUST call `save_general_details`.

**STEP 5 — Review:**
After ALL 4 sections are saved, call `review_vds_form` to show the customer a summary.

**STEP 6 — Submit:**
When the customer confirms the review is correct, IMMEDIATELY call `submit_vds_form`. Do NOT ask any more questions. Do NOT ask them to review again.

=== CO-LOCATION SERVICE APPLICATION WORKFLOW ===

You MUST collect information and call the save tools in this EXACT order.
YOU MUST CALL THE SAVE TOOL AFTER COLLECTING EACH SECTION. Do NOT skip calling the tool.

**STEP 1 — Billing Details:**
Ask the customer for: Billing POC Name, Designation, Address, Cell/Phone number, and Office Number.
Once you have ALL 5 fields, you MUST call `save_colocation_billing` with those values.
DO NOT proceed to Step 2 until you have called `save_colocation_billing`.

**STEP 2 — Colocation Requirements (General details):**
Ask the customer to provide the quantities and preferences for each of these items (if not applicable, use "None" or "0" or "No"):
1. Required 42 U Rack Space (Qty in 42 Rack units)
2. Required Rack Space (42 U Rack) (Qty in RU units)
3. Required Power for colocated equipment (Tentative Power Consumption in KWh)
4. Internet Uplink for colocation equipment (in Mbps)
5. Network Security Services (Y/N)
6. Required Number of SSL VPNs (if Any)
7. Required Number of Endpoint Security Licenses Requirements (Y/N)
8. SSL Certificate required DV/Wildcard
9. Domain Registration (Y/N)
10. Public IP required (Y/N)
11. Any other Requirement (if any)

Once you have collected these requirements, you MUST call `save_colocation_requirements`.
DO NOT proceed to Step 3 until you have called `save_colocation_requirements`.

**STEP 3 — Review:**
After both sections are saved, call `review_colocation_form` to show the customer a summary.

**STEP 4 — Submit:**
When the customer confirms the review is correct, IMMEDIATELY call `submit_colocation_form`. Do NOT ask any more questions. Do NOT ask them to review again.

=== SHARED WEB HOSTING SERVICE APPLICATION WORKFLOW ===

You MUST collect information and call the save tools in this EXACT order.
YOU MUST CALL THE SAVE TOOL AFTER COLLECTING EACH SECTION. Do NOT skip calling the tool.

**STEP 1 — Organization & Contact Details:**
Ask the customer for:
- Advice Number
- Request by Organization
- Technical Contact Person
- Designation
- Tech PoC Email / Phone
- Request Type (New Activation or Change Request)
- Testing environment provision date

Once you have ALL 7 fields, you MUST call `save_hosting_org_details` with those values.
DO NOT proceed to Step 2 until you have called `save_hosting_org_details`.

**STEP 2 — Web Server & Space Requirements:**
Ask the customer for:
- Web Server IP
- Website Hosting Platform (Linux- CPanel, Windows Plesk Panel, or Windows Shard- IIS)
- Web Space (GB)
- Database Space (GB)
- Domain / Sub Domain URL(s)
- Custom CMS URL (if any)
- cPanel / Plesk Panel Mgmt URL for Webmaster
- Domain Registration by NTC (Yes or No)

Once you have ALL 8 fields, you MUST call `save_hosting_server_details` with those values.
DO NOT proceed to Step 3 until you have called `save_hosting_server_details`.

**STEP 3 — Security & DNS Configuration:**
Ask the customer for:
- Authority DNS details (if not NTC)
- Customer Static IP for Mgmt
- VPN (Provisioned or Not Provisioned)
- SSL Type (DV, Wildcard, or Multi-Domain)
- Provisioned By (Name)
- Service Activation Date

Once you have ALL 6 fields, you MUST call `save_hosting_dns_details` with those values.
DO NOT proceed to Step 4 until you have called `save_hosting_dns_details`.

**STEP 4 — Review:**
After ALL 3 sections are saved, call `review_hosting_form` to show the customer a summary.

**STEP 5 — Submit:**
When the customer confirms the review is correct, IMMEDIATELY call `submit_hosting_form`. Do NOT ask any more questions. Do NOT ask them to review again.

RULES:
- Ask for fields naturally, one or a few at a time.
- YOU MUST call the corresponding save tool after collecting each section. This is critical.
- After calling a save tool, continue to the next section.
- Do NOT make up data.
- If the customer confirms the review, call submit tool IMMEDIATELY.

=== NTC EMAIL RESET / PASSWORD RESET WORKFLOW ===

When a customer asks about email reset, password reset, email password reset, or forgotten email credentials,
follow this EXACT 6-step workflow. This is for NTC email service customers who have forgotten or need to reset
their email password/credentials.

**STEP 1 — Identification & Security Verification:**
Identify that this is an 'Email Reset Issue'.
Ask the customer for:
1. Their current NTC email address (the one they need to reset)
2. Their Google Authenticator OTP (6-digit code from their authenticator app)
Once you have BOTH, you MUST call `verify_email_reset_identity` with the current_email and authenticator_otp.
Do NOT proceed until verification is successful.

**STEP 2 — Secure Ticket Generation:**
Upon successful verification, call `initiate_email_reset_ticket` to generate a unique Ticket #.
This will automatically create a secure ticket number.
Display the generated Ticket # to the customer.

**STEP 3 — User Interaction & Alternate Contact:**
Ask the customer for their alternate email address (where they want to receive the new credentials).
Once they provide it, call `submit_alternate_email` with the ticket_id and alternate_email.
This will:
- Create a database entry with status PENDING
- Alert the NTC Email Team automatically

**STEP 4 — (Automatic) Parallel Internal Actions:**
The system automatically handles:
- Alerting the Email Team via email notification
- Creating the database entry for the ticket with PENDING status
Inform the customer that their request has been submitted and the Email Team has been notified.
Provide the Ticket # again for their reference.

**STEP 5 — Team Resolution & Credential Handoff (Admin only):**
The Email Team resolves the issue and provides new credentials.
This step is handled externally by the Email Team. The tool `resolve_email_reset_ticket` is used
by the admin/team to submit the new username and password.

**STEP 6 — Status Check & Final Delivery:**
If the customer asks about the status of their ticket, call `check_email_reset_status` with the ticket_id.
If the status is RESOLVED and credentials are available:
- The credentials will be automatically sent to the customer's alternate email.
- The database status will be updated to RESOLVED.
- Inform the customer that the new credentials have been sent to their alternate email.
If the status is still PENDING, inform the customer that the Email Team is working on their request.

IMPORTANT RULES FOR EMAIL RESET:
- ALWAYS verify identity first (OTP + current email) before generating any ticket.
- NEVER share credentials directly in the chat — they are sent via email only.
- Each ticket has a unique Ticket # format like: 847291-X (6 digits + random letter suffix).
- The customer can check their ticket status at any time using their Ticket #.
"""


# =============================================
# AGENT STATE
# =============================================

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def init_vds_form():
    """Initialize VDS form in session state if not present."""
    if "vds_form" not in st.session_state:
        st.session_state.vds_form = {
            "billing_poc": {},
            "technical_poc": {},
            "server_count": 0,
            "servers_identical": False,
            "servers": [],
            "general": {},
        }
    if "generated_pdf" not in st.session_state:
        st.session_state.generated_pdf = None
    if "generated_excel" not in st.session_state:
        st.session_state.generated_excel = None
    if "form_submitted" not in st.session_state:
        st.session_state.form_submitted = False


def init_colocation_form():
    """Initialize Colocation form in session state if not present."""
    if "colocation_form" not in st.session_state:
        st.session_state.colocation_form = {
            "billing": {},
            "requirements": {}
        }


def init_hosting_form():
    """Initialize Shared Web Hosting form in session state if not present."""
    if "hosting_form" not in st.session_state:
        st.session_state.hosting_form = {
            "org_details": {},
            "server_details": {},
            "dns_details": {}
        }


# =============================================
# TOOLS
# =============================================

@tool
def list_ntc_services() -> str:
    """Lists all available NTC services. Call this when a customer asks what services NTC provides."""
    lines = []
    for i, svc in enumerate(NTC_SERVICES, 1):
        status = "Available Now" if svc["available"] else "Coming Soon"
        lines.append(f"{i}) {svc['name']} — {status}")
    return "\n".join(lines)


@tool
def save_billing_poc(name: str, designation: str, address: str, phone_no: str, office_no: str, config: RunnableConfig) -> str:
    """Saves Billing POC details to the database. You MUST call this after collecting ALL billing POC fields:
    name, designation, address, phone_no, office_no."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_billing_poc for {user_email}")
    print(f"  Data: name={name}, designation={designation}, address={address}, phone_no={phone_no}, office_no={office_no}")
    
    form = db_get_vds_form(user_email)
    form["billing_poc"] = {
        "name": name, "designation": designation, "address": address,
        "phone_no": phone_no, "office_no": office_no,
    }
    saved = db_save_vds_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Billing POC details saved successfully to the database. Now proceed to collect Technical POC details."


@tool
def save_technical_poc(name: str, designation: str, address: str, phone_no: str, office_no: str,
                       server_description: str, url: str, server: str, config: RunnableConfig) -> str:
    """Saves Technical POC details to the database. You MUST call this after collecting ALL technical POC fields:
    name, designation, address, phone_no, office_no, server_description, url, server."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_technical_poc for {user_email}")
    print(f"  Data: name={name}, designation={designation}, address={address}")
    
    form = db_get_vds_form(user_email)
    form["technical_poc"] = {
        "name": name, "designation": designation, "address": address,
        "phone_no": phone_no, "office_no": office_no,
        "server_description": server_description, "url": url, "server": server,
    }
    saved = db_save_vds_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Technical POC details saved successfully. Now proceed to Server Details."


@tool
def setup_servers(server_count: int, identical_configuration: bool, config: RunnableConfig) -> str:
    """Sets up server count and configuration type. Call after asking how many servers
    and whether configurations are identical or unique. For single server, set identical_configuration to True."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] setup_servers for {user_email}: count={server_count}, identical={identical_configuration}")
    
    form = db_get_vds_form(user_email)
    form["server_count"] = server_count
    form["servers_identical"] = identical_configuration
    form["servers"] = []
    db_save_vds_form(user_email, form)
    
    if identical_configuration:
        return f"✅ Server setup saved: {server_count} server(s) with identical configuration. Please collect server details once — they will be applied to all servers."
    else:
        return f"✅ Server setup saved: {server_count} servers with unique configurations. Please collect details for Server 1."


@tool
def save_server_config(server_number: int, cpu: str, ram: str, storage_type: str,
                       storage_capacity: str, os_name_version: str, os_gui_or_minimal: str, config: RunnableConfig) -> str:
    """Saves configuration for a specific server. storage_type must be one of: SAS, Auto Tiered, NLSAS, SSD, NVME.
    os_gui_or_minimal should be either GUI or Minimal. server_number starts from 1."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_server_config for {user_email}: server #{server_number}")
    print(f"  Data: cpu={cpu}, ram={ram}, storage_type={storage_type}, storage_capacity={storage_capacity}")
    
    form = db_get_vds_form(user_email)
    
    server_config = {
        "cpu": cpu, "ram": ram, "storage_type": storage_type,
        "storage_capacity": storage_capacity, "os_name_version": os_name_version,
        "os_gui_or_minimal": os_gui_or_minimal,
    }
    
    if form.get("servers_identical"):
        form["servers"] = [server_config.copy() for _ in range(form["server_count"])]
    else:
        while len(form["servers"]) < server_number:
            form["servers"].append({})
        form["servers"][server_number - 1] = server_config
    
    db_save_vds_form(user_email, form)
    
    if form.get("servers_identical"):
        return f"✅ Server configuration saved and applied to all {form['server_count']} server(s). Now proceed to General Details."
    else:
        if server_number < form["server_count"]:
            return f"✅ Server {server_number} configuration saved. Please collect details for Server {server_number + 1}."
        else:
            return f"✅ All {form['server_count']} server configurations saved. Now proceed to General Details."


@tool
def save_general_details(internet_uplink_mbps: str, endpoint_security: str,
                         backup_as_service: str, ssl_type: str, ssl_vpn: str,
                         domain_registration: str, public_ip: str,
                         additional_requirements: str, config: RunnableConfig) -> str:
    """Saves General Details section to the database. You MUST call this after collecting ALL general detail fields."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_general_details for {user_email}")
    
    form = db_get_vds_form(user_email)
    form["general"] = {
        "internet_uplink_mbps": internet_uplink_mbps,
        "endpoint_security": endpoint_security,
        "backup_as_service": backup_as_service,
        "ssl_type": ssl_type,
        "ssl_vpn": ssl_vpn,
        "domain_registration": domain_registration,
        "public_ip": public_ip,
        "additional_requirements": additional_requirements,
    }
    db_save_vds_form(user_email, form)
    print(f"  General details saved to DB.")
    return "✅ General details saved successfully. All sections are now complete. Now call review_vds_form to show the customer a review."


@tool
def review_vds_form(config: RunnableConfig) -> str:
    """Returns a formatted review of all collected VDS form data from the database. Call after all 4 sections are saved."""
    user_email = config.get("configurable", {}).get("user_email")
    form = db_get_vds_form(user_email)
    print(f"[TOOL CALLED] review_vds_form for {user_email}")
    print(f"  DB form data: {json.dumps(form, indent=2)}")
    
    lines = ["=== VDS SERVICE PROFORMA REVIEW ===\n"]

    lines.append("--- SECTION 1: Billing POC Details ---")
    for key, label in BILLING_POC_FIELDS:
        lines.append(f"{label}: {form.get('billing_poc', {}).get(key, 'N/A')}")

    lines.append("\n--- SECTION 2: Technical POC Details ---")
    for key, label in TECHNICAL_POC_FIELDS:
        lines.append(f"{label}: {form.get('technical_poc', {}).get(key, 'N/A')}")

    lines.append(f"\n--- SECTION 3: Server Details ---")
    lines.append(f"Total Servers: {form.get('server_count', 0)}")
    lines.append(f"Configuration: {'Identical' if form.get('servers_identical') else 'Unique'}")
    for i, srv in enumerate(form.get("servers", []), 1):
        lines.append(f"\nServer {i}:")
        for key, label in SERVER_DETAIL_FIELDS:
            lines.append(f"  {label}: {srv.get(key, 'N/A')}")

    lines.append("\n--- SECTION 4: General Details ---")
    for key, label in GENERAL_DETAIL_FIELDS:
        lines.append(f"{label}: {form.get('general', {}).get(key, 'N/A')}")

    lines.append("\n=== END OF REVIEW ===")
    lines.append("Ask the customer to confirm if the details are correct.")
    lines.append("IMPORTANT: When the customer confirms, you MUST call submit_vds_form immediately. Do NOT ask again.")
    return "\n".join(lines)


@tool
def submit_vds_form(config: RunnableConfig) -> str:
    """Submits the VDS form — generates PDF/Excel documents and sends email to NTC.
    Call ONLY after the customer has reviewed and confirmed the form details."""
    user_email = config.get("configurable", {}).get("user_email", "")
    user_name = config.get("configurable", {}).get("user_name", "Customer")
    form = db_get_vds_form(user_email)
    
    print(f"[TOOL CALLED] submit_vds_form for {user_email}")
    print(f"  Form Data from DB: {json.dumps(form, indent=2)}")
    
    # Validation
    has_billing = bool(form.get("billing_poc"))
    has_technical = bool(form.get("technical_poc"))
    print(f"  has_billing={has_billing}, has_technical={has_technical}")
    
    if not has_billing and not has_technical:
        return ("ERROR: The form data is empty in the database. "
                "This means the save tools (save_billing_poc, save_technical_poc, etc.) were never called. "
                "Please go back and collect the customer's information again, making sure to call each save tool.")

    try:
        # Generate documents
        print("  Generating PDF...")
        pdf_bytes = generate_vds_pdf(form, user_name, user_email)
        print(f"  PDF generated: {len(pdf_bytes)} bytes")
        
        print("  Generating Excel...")
        excel_bytes = generate_vds_excel(form, user_name, user_email)
        print(f"  Excel generated: {len(excel_bytes)} bytes")

        # Send email
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        email_body = f"""
        <html><body>
        <h2>New VDS Service Proforma Submission</h2>
        <p><b>Applicant:</b> {user_name}</p>
        <p><b>Email:</b> {user_email}</p>
        <p><b>Date:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p><b>Total Servers:</b> {form.get('server_count', 0)}</p>
        <p>Please find the detailed proforma attached.</p>
        </body></html>
        """
        attachments = [
            {"bytes": pdf_bytes, "filename": f"VDS_Proforma_{timestamp}.pdf"},
            {"bytes": excel_bytes, "filename": f"VDS_Proforma_{timestamp}.xlsx"},
        ]
        
        print("  Sending email to test.jawad@ntc.org.pk...")
        email_sent_to_ntc = send_email_with_attachment(
            "jawad.malakandkp@gmail.com",
            f"VDS Proforma - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to NTC: {'sent' if email_sent_to_ntc else 'FAILED'}")
        
        print("  Sending email to umerhayatkhan1976@gmail.com...")
        email_sent_to_umer = send_email_with_attachment(
            "umerhayatkhan1976@gmail.com",
            f"VDS Proforma - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to umer: {'sent' if email_sent_to_umer else 'FAILED'}")

        if email_sent_to_ntc and email_sent_to_umer:
            st.session_state.form_submitted = True
            st.session_state.generated_pdf = pdf_bytes
            st.session_state.generated_excel = excel_bytes
            st.session_state.submitted_service_type = "vds"
            return ("Form submitted successfully! Your application has been processed, and the necessary "
                    "PDF and Excel documents have been generated and emailed to NTC. You can expect further "
                    "communication from our team regarding the next steps. If you have any more questions or "
                    "need assistance, feel free to reach out. Thank you for choosing NTC for your IaaS VDS "
                    "service. Have a great day!")
        else:
            return "Documents generated successfully but email sending failed. Please contact NTC support."
    except Exception as e:
        print("====== SUBMIT VDS FORM ERROR ======")
        traceback.print_exc()
        print("===================================")
        return f"Error during submission: {str(e)}"


@tool
def save_colocation_billing(billing_name: str, designation: str, address: str, cell_no: str, office_no: str, config: RunnableConfig) -> str:
    """Saves Colocation Billing details to the database. You MUST call this after collecting ALL 5 billing details:
    billing_name, designation, address, cell_no, office_no."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_colocation_billing for {user_email}")
    print(f"  Data: billing_name={billing_name}, designation={designation}, address={address}, cell_no={cell_no}, office_no={office_no}")
    
    form = db_get_colocation_form(user_email)
    form["billing"] = {
        "billing_name": billing_name, "designation": designation, "address": address,
        "cell_no": cell_no, "office_no": office_no,
    }
    saved = db_save_colocation_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Colocation Billing details saved successfully. Now proceed to collect the Colocation Requirements details."


@tool
def save_colocation_requirements(
    rack_space_42u: str, rack_space_ru: str, power_kwh: str, internet_uplink_mbps: str,
    network_security: str, ssl_vpns: str, endpoint_security: str, ssl_cert_type: str,
    domain_registration: str, public_ip: str, other_requirements: str, config: RunnableConfig
) -> str:
    """Saves Colocation Requirements details to the database. You MUST call this after collecting ALL colocation requirement fields."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_colocation_requirements for {user_email}")
    
    form = db_get_colocation_form(user_email)
    form["requirements"] = {
        "rack_space_42u": rack_space_42u,
        "rack_space_ru": rack_space_ru,
        "power_kwh": power_kwh,
        "internet_uplink_mbps": internet_uplink_mbps,
        "network_security": network_security,
        "ssl_vpns": ssl_vpns,
        "endpoint_security": endpoint_security,
        "ssl_cert_type": ssl_cert_type,
        "domain_registration": domain_registration,
        "public_ip": public_ip,
        "other_requirements": other_requirements,
    }
    saved = db_save_colocation_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Colocation Requirements saved successfully. All sections are now complete. Now call review_colocation_form to show the customer a review."


@tool
def review_colocation_form(config: RunnableConfig) -> str:
    """Returns a formatted review of all collected Colocation form data from the database. Call after all sections are saved."""
    user_email = config.get("configurable", {}).get("user_email")
    form = db_get_colocation_form(user_email)
    print(f"[TOOL CALLED] review_colocation_form for {user_email}")
    
    lines = ["=== CO-LOCATION SERVICE REQUEST FORM REVIEW ===\n"]
    lines.append("--- SECTION 1: Billing Details ---")
    billing = form.get("billing", {})
    from config import COLOCATION_BILLING_FIELDS
    for key, label in COLOCATION_BILLING_FIELDS:
        lines.append(f"{label}: {billing.get(key, 'N/A')}")
        
    lines.append("\n--- SECTION 2: Colocation Requirements ---")
    reqs = form.get("requirements", {})
    from config import COLOCATION_REQUIREMENT_FIELDS
    for key, label in COLOCATION_REQUIREMENT_FIELDS:
        lines.append(f"{label}: {reqs.get(key, 'N/A')}")
        
    lines.append("\n=== END OF REVIEW ===")
    lines.append("Ask the customer to confirm if the details are correct.")
    lines.append("IMPORTANT: When the customer confirms, you MUST call submit_colocation_form immediately. Do NOT ask again.")
    return "\n".join(lines)


@tool
def submit_colocation_form(config: RunnableConfig) -> str:
    """Submits the Colocation form — generates PDF/Excel request sheets and sends email to NTC.
    Call ONLY after the customer has reviewed and confirmed the form details."""
    user_email = config.get("configurable", {}).get("user_email", "")
    user_name = config.get("configurable", {}).get("user_name", "Customer")
    form = db_get_colocation_form(user_email)
    
    print(f"[TOOL CALLED] submit_colocation_form for {user_email}")
    
    has_billing = bool(form.get("billing"))
    has_reqs = bool(form.get("requirements"))
    
    if not has_billing and not has_reqs:
        return ("ERROR: The form data is empty in the database. "
                "This means the save tools (save_colocation_billing, save_colocation_requirements) were never called. "
                "Please go back and collect the customer's information again, making sure to call each save tool.")
                
    try:
        from generators import generate_colocation_pdf, generate_colocation_excel
        # Generate documents
        print("  Generating Colocation PDF...")
        pdf_bytes = generate_colocation_pdf(form, user_name, user_email)
        print(f"  Colocation PDF generated: {len(pdf_bytes)} bytes")
        
        print("  Generating Colocation Excel...")
        excel_bytes = generate_colocation_excel(form, user_name, user_email)
        print(f"  Colocation Excel generated: {len(excel_bytes)} bytes")
        
        # Send email
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        email_body = f"""
        <html><body>
        <h2>New Data Center Colocation Services Request Submission</h2>
        <p><b>Applicant:</b> {user_name}</p>
        <p><b>Email:</b> {user_email}</p>
        <p><b>Date:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p>Please find the detailed request form attached.</p>
        </body></html>
        """
        attachments = [
            {"bytes": pdf_bytes, "filename": f"Colocation_Request_{timestamp}.pdf"},
            {"bytes": excel_bytes, "filename": f"Colocation_Request_{timestamp}.xlsx"},
        ]
        
        print("  Sending email to test.jawad@ntc.org.pk...")
        email_sent_to_ntc = send_email_with_attachment(
            "jawad.malakandkp@gmail.com",
            f"Colocation Request - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to NTC: {'sent' if email_sent_to_ntc else 'FAILED'}")
        
        print("  Sending email to umerhayatkhan1976@gmail.com...")
        email_sent_to_umer = send_email_with_attachment(
            "umerhayatkhan1976@gmail.com",
            f"Colocation Request - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to umer: {'sent' if email_sent_to_umer else 'FAILED'}")
        
        if email_sent_to_ntc and email_sent_to_umer:
            st.session_state.form_submitted = True
            st.session_state.generated_pdf = pdf_bytes
            st.session_state.generated_excel = excel_bytes
            st.session_state.submitted_service_type = "colocation"
            return ("Form submitted successfully! Your application has been processed, and the necessary "
                    "PDF and Excel documents have been generated and emailed to NTC. You can expect further "
                    "communication from our team regarding the next steps. If you have any more questions or "
                    "need assistance, feel free to reach out. Thank you for choosing NTC for your Colocation "
                    "service. Have a great day!")
        else:
            return "Documents generated successfully but email sending failed. Please contact NTC support."
    except Exception as e:
        print("====== SUBMIT COLOCATION FORM ERROR ======")
        traceback.print_exc()
        print("==========================================")
        return f"Error during submission: {str(e)}"


# =============================================
# AGENT CREATION
# =============================================

@tool
def save_hosting_org_details(
    advice_number: str, org_name: str, tech_person: str, designation: str,
    tech_poc_email_phone: str, request_type: str, testing_date: str, config: RunnableConfig
) -> str:
    """Saves Shared Web Hosting Organization & Request Details to the database.
    You MUST call this after collecting ALL 7 fields: advice_number, org_name, tech_person,
    designation, tech_poc_email_phone, request_type, testing_date."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_hosting_org_details for {user_email}")
    
    form = db_get_hosting_form(user_email)
    form["org_details"] = {
        "advice_number": advice_number,
        "org_name": org_name,
        "tech_person": tech_person,
        "designation": designation,
        "tech_poc_email_phone": tech_poc_email_phone,
        "request_type": request_type,
        "testing_date": testing_date,
    }
    saved = db_save_hosting_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Shared Web Hosting Organization details saved successfully. Now proceed to collect Step 2: Web Server & Space Requirements."


@tool
def save_hosting_server_details(
    web_server_ip: str, hosting_platform: str, web_space_gb: str, db_space_gb: str,
    domain_urls: str, custom_cms_url: str, mgmt_url: str, domain_registration_ntc: str, config: RunnableConfig
) -> str:
    """Saves Shared Web Hosting Server and Space Details to the database.
    You MUST call this after collecting ALL 8 server fields."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_hosting_server_details for {user_email}")
    
    form = db_get_hosting_form(user_email)
    form["server_details"] = {
        "web_server_ip": web_server_ip,
        "hosting_platform": hosting_platform,
        "web_space_gb": web_space_gb,
        "db_space_gb": db_space_gb,
        "domain_urls": domain_urls,
        "custom_cms_url": custom_cms_url,
        "mgmt_url": mgmt_url,
        "domain_registration_ntc": domain_registration_ntc,
    }
    saved = db_save_hosting_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Shared Web Hosting Server details saved successfully. Now proceed to collect Step 3: Security & DNS Configuration."


@tool
def save_hosting_dns_details(
    authority_dns: str, customer_static_ip: str, vpn: str, ssl_type: str,
    provisioned_by: str, activation_date: str, config: RunnableConfig
) -> str:
    """Saves Shared Web Hosting DNS & Security Configuration to the database.
    You MUST call this after collecting ALL 6 DNS and security fields."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] save_hosting_dns_details for {user_email}")
    
    form = db_get_hosting_form(user_email)
    form["dns_details"] = {
        "authority_dns": authority_dns,
        "customer_static_ip": customer_static_ip,
        "vpn": vpn,
        "ssl_type": ssl_type,
        "provisioned_by": provisioned_by,
        "activation_date": activation_date,
    }
    saved = db_save_hosting_form(user_email, form)
    print(f"  DB save result: {saved}")
    return "✅ Shared Web Hosting DNS & Security details saved successfully. All sections are complete. Call review_hosting_form to show the customer a review."


@tool
def review_hosting_form(config: RunnableConfig) -> str:
    """Returns a formatted review of all collected Shared Web Hosting form data. Call after all sections are saved."""
    user_email = config.get("configurable", {}).get("user_email")
    form = db_get_hosting_form(user_email)
    print(f"[TOOL CALLED] review_hosting_form for {user_email}")
    
    lines = ["=== SHARED WEB HOSTING SERVICE ACTIVATION REVIEW ===\n"]
    
    lines.append("--- SECTION 1: Organization & Request Details ---")
    org = form.get("org_details", {})
    from config import HOSTING_ORG_FIELDS
    for key, label in HOSTING_ORG_FIELDS:
        lines.append(f"{label}: {org.get(key, 'N/A')}")
        
    lines.append("\n--- SECTION 2: Web Server & Space Requirements ---")
    srv = form.get("server_details", {})
    from config import HOSTING_SERVER_FIELDS
    for key, label in HOSTING_SERVER_FIELDS:
        lines.append(f"{label}: {srv.get(key, 'N/A')}")
        
    lines.append("\n--- SECTION 3: Security & DNS Configuration ---")
    dns = form.get("dns_details", {})
    from config import HOSTING_DNS_FIELDS
    for key, label in HOSTING_DNS_FIELDS:
        lines.append(f"{label}: {dns.get(key, 'N/A')}")
        
    lines.append("\n=== END OF REVIEW ===")
    lines.append("Ask the customer to confirm if the details are correct.")
    lines.append("IMPORTANT: When the customer confirms, you MUST call submit_hosting_form immediately. Do NOT ask again.")
    return "\n".join(lines)


@tool
def submit_hosting_form(config: RunnableConfig) -> str:
    """Submits the Shared Web Hosting form — generates PDF/Excel request sheets and sends email to NTC.
    Call ONLY after the customer has reviewed and confirmed the form details."""
    user_email = config.get("configurable", {}).get("user_email", "")
    user_name = config.get("configurable", {}).get("user_name", "Customer")
    form = db_get_hosting_form(user_email)
    
    print(f"[TOOL CALLED] submit_hosting_form for {user_email}")
    
    has_org = bool(form.get("org_details"))
    has_srv = bool(form.get("server_details"))
    has_dns = bool(form.get("dns_details"))
    
    if not has_org and not has_srv and not has_dns:
        return ("ERROR: The form data is empty in the database. "
                "This means the save tools were never called. "
                "Please go back and collect the customer's information again.")
                
    try:
        from generators import generate_hosting_pdf, generate_hosting_excel
        # Generate documents
        print("  Generating Shared Web Hosting PDF...")
        pdf_bytes = generate_hosting_pdf(form, user_name, user_email)
        print(f"  Hosting PDF generated: {len(pdf_bytes)} bytes")
        
        print("  Generating Shared Web Hosting Excel...")
        excel_bytes = generate_hosting_excel(form, user_name, user_email)
        print(f"  Hosting Excel generated: {len(excel_bytes)} bytes")
        
        # Send email
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        email_body = f"""
        <html><body>
        <h2>New Shared Web Hosting Services Request Submission</h2>
        <p><b>Applicant:</b> {user_name}</p>
        <p><b>Email:</b> {user_email}</p>
        <p><b>Date:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p>Please find the detailed request form attached.</p>
        </body></html>
        """
        attachments = [
            {"bytes": pdf_bytes, "filename": f"Shared_Web_Hosting_Request_{timestamp}.pdf"},
            {"bytes": excel_bytes, "filename": f"Shared_Web_Hosting_Request_{timestamp}.xlsx"},
        ]
        
        print("  Sending email to test.jawad@ntc.org.pk...")
        email_sent_to_ntc = send_email_with_attachment(
            "test.jawad@ntc.org.pk",
            f"Shared Web Hosting Request - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to NTC: {'sent' if email_sent_to_ntc else 'FAILED'}")
        
        print("  Sending email to umerhayatkhan1976@gmail.com...")
        email_sent_to_umer = send_email_with_attachment(
            "umerhayatkhan1976@gmail.com",
            f"Shared Web Hosting Request - {user_name} - {datetime.datetime.now().strftime('%Y-%m-%d')}",
            email_body, attachments,
        )
        print(f"  Email to umer: {'sent' if email_sent_to_umer else 'FAILED'}")
        
        if email_sent_to_ntc and email_sent_to_umer:
            st.session_state.form_submitted = True
            st.session_state.generated_pdf = pdf_bytes
            st.session_state.generated_excel = excel_bytes
            st.session_state.submitted_service_type = "hosting"
            return ("Form submitted successfully! Your application has been processed, and the necessary "
                    "PDF and Excel documents have been generated and emailed to NTC. You can expect further "
                    "communication from our team regarding the next steps. If you have any more questions or "
                    "need assistance, feel free to reach out. Thank you for choosing NTC for your Shared Web Hosting "
                    "service. Have a great day!")
        else:
            return "Documents generated successfully but email sending failed. Please contact NTC support."
    except Exception as e:
        print("====== SUBMIT HOSTING FORM ERROR ======")
        traceback.print_exc()
        print("=======================================")
        return f"Error during submission: {str(e)}"


# =============================================
# EMAIL RESET TOOLS
# =============================================

@tool
def verify_email_reset_identity(current_email: str, authenticator_otp: str, config: RunnableConfig) -> str:
    """STEP 1: Verifies the customer's identity for email reset by checking their Authenticator OTP
    against their registered account. Call this with the customer's current NTC email and their
    Google Authenticator 6-digit OTP code."""
    import pyotp
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] verify_email_reset_identity for {user_email}")
    print(f"  current_email={current_email}, authenticator_otp={authenticator_otp}")
    
    # Get the secret key for the user's email (the logged-in user)
    secret_key = get_user_secret_key(user_email)
    if not secret_key:
        return "VERIFICATION FAILED: Could not find your account. Please ensure you are logged in with the correct account."
    
    # Verify the OTP
    totp = pyotp.TOTP(secret_key)
    if totp.verify(authenticator_otp, valid_window=1):
        # Store verified state in session
        st.session_state._email_reset_verified = True
        st.session_state._email_reset_current_email = current_email
        return (f"IDENTITY VERIFIED SUCCESSFULLY!\n\n"
                f"Your identity has been confirmed for the email: {current_email}\n\n"
                f"Now proceed to STEP 2: Call initiate_email_reset_ticket to generate a secure Ticket number.")
    else:
        return "VERIFICATION FAILED: The OTP you provided is invalid or expired. Please try again with a fresh OTP from your Google Authenticator app."


@tool
def initiate_email_reset_ticket(config: RunnableConfig) -> str:
    """STEP 2: Generates a unique secure Ticket number for the email reset request.
    Call this ONLY after verify_email_reset_identity has succeeded.
    Returns the ticket number to display to the customer."""
    import random
    import string
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] initiate_email_reset_ticket for {user_email}")
    
    # Check verification
    if not st.session_state.get("_email_reset_verified"):
        return "ERROR: Identity has not been verified yet. Please call verify_email_reset_identity first."
    
    # Generate unique ticket number: 6 digits + hyphen + random uppercase letter
    ticket_number = f"{random.randint(100000, 999999)}-{random.choice(string.ascii_uppercase)}"
    
    # Store ticket ID in session for next step
    st.session_state._email_reset_ticket_id = ticket_number
    
    print(f"  Generated Ticket #: {ticket_number}")
    return (f"SECURE TICKET GENERATED!\n\n"
            f"Ticket # {ticket_number}\n\n"
            f"Please share this Ticket number with the customer and ask them to provide their "
            f"alternate email address where they want to receive the new credentials.\n\n"
            f"Now proceed to STEP 3: Ask the customer for their alternate email address, "
            f"then call submit_alternate_email.")


@tool
def submit_alternate_email(ticket_id: str, alternate_email: str, config: RunnableConfig) -> str:
    """STEP 3 and 4 combined: Saves the alternate email address, creates the database entry with PENDING status,
    and alerts the NTC Email Team. Call this after the customer provides their alternate email address.
    ticket_id is the Ticket number from Step 2. alternate_email is where credentials will be sent."""
    user_email = config.get("configurable", {}).get("user_email")
    user_name = config.get("configurable", {}).get("user_name", "Customer")
    current_email = st.session_state.get("_email_reset_current_email", "")
    
    print(f"[TOOL CALLED] submit_alternate_email for {user_email}")
    print(f"  ticket_id={ticket_id}, alternate_email={alternate_email}, current_email={current_email}")
    
    # STEP 4a: Create Database Entry with PENDING status
    db_result = db_create_email_reset_ticket(ticket_id, user_email, current_email, alternate_email)
    if not db_result:
        return "ERROR: Failed to create the ticket entry in the database. Please try again."
    
    print(f"  Database entry created with PENDING status")
    
    # STEP 4b: Alert Email Team via email notification
    from config import EMAIL_TEAM_RECIPIENT_EMAIL
    alert_body = f"""
    <html><body>
    <h2>New Email Reset Request - Action Required</h2>
    <table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse; font-family:Arial;'>
        <tr style='background:#006432; color:white;'>
            <td colspan='2'><b>Email Reset Ticket Details</b></td>
        </tr>
        <tr><td><b>Ticket #</b></td><td>{ticket_id}</td></tr>
        <tr><td><b>Customer Name</b></td><td>{user_name}</td></tr>
        <tr><td><b>Customer Account Email</b></td><td>{user_email}</td></tr>
        <tr><td><b>Email to Reset</b></td><td>{current_email}</td></tr>
        <tr><td><b>Alternate Email (for delivery)</b></td><td>{alternate_email}</td></tr>
        <tr><td><b>Status</b></td><td style='color:orange;'><b>PENDING</b></td></tr>
        <tr><td><b>Date</b></td><td>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</td></tr>
    </table>
    <p style='margin-top:15px;'>Please resolve this email reset request and provide new credentials 
    through the NTC Admin panel or by using the resolve_email_reset_ticket tool.</p>
    <p><i>- NTC Nexus Automated Alert System</i></p>
    </body></html>
    """
    
    email_sent = send_email_with_attachment(
        EMAIL_TEAM_RECIPIENT_EMAIL,
        f"Email Reset Request - Ticket #{ticket_id} - {user_name}",
        alert_body
    )
    
    # Also send to umerhayatkhan1976@gmail.com
    email_sent_umer = send_email_with_attachment(
        "umerhayatkhan1976@gmail.com",
        f"Email Reset Request - Ticket #{ticket_id} - {user_name}",
        alert_body
    )
    
    print(f"  Email Team Alert: {'sent' if email_sent else 'FAILED'}")
    print(f"  Umer Alert: {'sent' if email_sent_umer else 'FAILED'}")
    
    # Clean up session verification state
    st.session_state._email_reset_verified = False
    
    team_status = "Email Team has been notified successfully" if (email_sent or email_sent_umer) else "Email notification failed, but the ticket has been created"
    
    return (f"EMAIL RESET REQUEST SUBMITTED SUCCESSFULLY!\n\n"
            f"Summary:\n"
            f"- Ticket #: {ticket_id}\n"
            f"- Email to Reset: {current_email}\n"
            f"- Credentials will be sent to: {alternate_email}\n"
            f"- Status: PENDING\n"
            f"- {team_status}\n\n"
            f"The NTC Email Team will process your request and generate new credentials. "
            f"Once resolved, the new username and password will be securely sent to your alternate email address.\n\n"
            f"You can check the status of your request at any time by providing your Ticket # {ticket_id}.")


@tool
def resolve_email_reset_ticket(ticket_id: str, new_username: str, new_password: str, config: RunnableConfig) -> str:
    """STEP 5: (Email Team / Admin use) Resolves an email reset ticket by providing new credentials.
    This stores the new username and password, marks the ticket as RESOLVED, and sends the
    credentials to the customer's alternate email. Call with the ticket_id, new_username, and new_password."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] resolve_email_reset_ticket for ticket {ticket_id}")
    
    # Get the ticket
    ticket = db_get_email_reset_ticket(ticket_id)
    if not ticket:
        return f"ERROR: Ticket #{ticket_id} not found in the system."
    
    if ticket["status"] == "RESOLVED":
        return f"Ticket #{ticket_id} has already been resolved."
    
    # Update credentials and mark as RESOLVED
    updated = db_update_email_reset_credentials(ticket_id, new_username, new_password)
    if not updated:
        return "ERROR: Failed to update the ticket with new credentials."
    
    # STEP 6: Send credentials to alternate email
    alternate_email = ticket["alternate_email"]
    credential_body = f"""
    <html><body>
    <div style='font-family:Arial; max-width:600px; margin:0 auto;'>
        <div style='background:#006432; color:white; padding:20px; text-align:center;'>
            <h2>National Telecommunication Corporation</h2>
            <p>Email Credentials Reset - Completed</p>
        </div>
        <div style='padding:20px; border:1px solid #ddd;'>
            <p>Dear Customer,</p>
            <p>Your email reset request (Ticket # <b>{ticket_id}</b>) has been resolved. 
            Below are your new credentials:</p>
            <table border='1' cellpadding='10' cellspacing='0' style='border-collapse:collapse; width:100%; margin:15px 0;'>
                <tr style='background:#006432; color:white;'>
                    <td colspan='2' align='center'><b>New Email Credentials</b></td>
                </tr>
                <tr>
                    <td><b>Username</b></td>
                    <td style='font-family:monospace; font-size:14px;'>{new_username}</td>
                </tr>
                <tr>
                    <td><b>Password</b></td>
                    <td style='font-family:monospace; font-size:14px;'>{new_password}</td>
                </tr>
            </table>
            <p style='color:red;'><b>Important:</b> Please change your password immediately after logging in for security purposes.</p>
            <p>If you did not request this reset, please contact NTC support immediately at <b>1218</b> or email <b>info@ntc.net.pk</b>.</p>
            <hr>
            <p style='color:#888; font-size:12px;'>This is an automated message from NTC Nexus Customer Support Portal. 
            Do not reply to this email.</p>
        </div>
    </div>
    </body></html>
    """
    
    email_sent = send_email_with_attachment(
        alternate_email,
        f"Your NTC Email Credentials - Ticket #{ticket_id} - RESOLVED",
        credential_body
    )
    
    print(f"  Credentials sent to {alternate_email}: {'sent' if email_sent else 'FAILED'}")
    
    if email_sent:
        return (f"TICKET #{ticket_id} RESOLVED SUCCESSFULLY!\n\n"
                f"- New credentials have been securely sent to: {alternate_email}\n"
                f"- Ticket Status: RESOLVED\n\n"
                f"The customer has been advised to change their password after first login.")
    else:
        return (f"Ticket #{ticket_id} resolved and credentials stored, but email delivery to "
                f"{alternate_email} failed. Please retry or contact the customer directly.")


@tool
def check_email_reset_status(ticket_id: str, config: RunnableConfig) -> str:
    """STEP 6: Checks the status of an email reset ticket. Call when a customer asks about their
    email reset request status. Provide the ticket_id (Ticket number)."""
    user_email = config.get("configurable", {}).get("user_email")
    print(f"[TOOL CALLED] check_email_reset_status for ticket {ticket_id} by {user_email}")
    
    ticket = db_get_email_reset_ticket(ticket_id)
    if not ticket:
        return f"Ticket #{ticket_id} was not found in our system. Please check the ticket number and try again."
    
    status = ticket["status"]
    
    if status == "RESOLVED":
        return (f"Ticket #{ticket_id} - RESOLVED\n\n"
                f"Great news! Your email reset request has been completed.\n"
                f"- Email Reset: {ticket['current_email']}\n"
                f"- Credentials sent to: {ticket['alternate_email']}\n"
                f"- Resolved on: {ticket['updated_at']}\n\n"
                f"Please check your alternate email for the new credentials. "
                f"Remember to change your password after first login.")
    elif status == "PENDING":
        return (f"Ticket #{ticket_id} - PENDING\n\n"
                f"Your email reset request is currently being processed by the NTC Email Team.\n"
                f"- Email to Reset: {ticket['current_email']}\n"
                f"- Credentials will be sent to: {ticket['alternate_email']}\n"
                f"- Submitted on: {ticket['created_at']}\n\n"
                f"Please allow some time for the team to process your request. "
                f"You will receive the new credentials at your alternate email once resolved.")
    else:
        return (f"Ticket #{ticket_id} - Status: {status}\n\n"
                f"- Email: {ticket['current_email']}\n"
                f"- Last Updated: {ticket['updated_at']}")


# =============================================
# AGENT CREATION
# =============================================

ALL_TOOLS = [
    list_ntc_services, save_billing_poc, save_technical_poc,
    setup_servers, save_server_config,
    save_general_details, review_vds_form, submit_vds_form,
    save_colocation_billing, save_colocation_requirements,
    review_colocation_form, submit_colocation_form,
    save_hosting_org_details, save_hosting_server_details,
    save_hosting_dns_details, review_hosting_form, submit_hosting_form,
    verify_email_reset_identity, initiate_email_reset_ticket,
    submit_alternate_email, resolve_email_reset_ticket,
    check_email_reset_status,
]


def create_nexus_agent():
    """Creates the LangGraph agent with Qwen LLM and VDS tools."""
    hf_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    if not hf_token:
        raise ValueError("HUGGINGFACEHUB_API_TOKEN is not set. Please configure it in the sidebar.")

    endpoint = HuggingFaceEndpoint(
        repo_id="Qwen/Qwen2.5-7B-Instruct",
        task="text-generation",
        max_new_tokens=512,
        temperature=0.1,
        huggingfacehub_api_token=hf_token,
    )
    llm = ChatHuggingFace(llm=endpoint)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState):
        messages = state["messages"]
        # Inject system prompt if not already present
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=NEXUS_SYSTEM_PROMPT)] + messages
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(ALL_TOOLS)

    def should_continue(state: AgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    return workflow.compile()
