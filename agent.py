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
)
from generators import generate_vds_pdf, generate_vds_excel
from email_utils import send_email_with_attachment
from config import VDS_RECIPIENT_EMAIL
from db import get_vds_form as db_get_vds_form, save_vds_form as db_save_vds_form


# =============================================
# SYSTEM PROMPT
# =============================================

NEXUS_SYSTEM_PROMPT = """You are Nexus, the AI Customer Support Agent for the National Telecommunication Corporation (NTC) of Pakistan.

AVAILABLE NTC SERVICES:
1) IaaS VDS (Virtual Dedicated Server) — Available Now
2) E-mail Services — Coming Soon
3) Co-location — Coming Soon
4) Shared Web Hosting — Coming Soon
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

RULES:
- Ask for fields naturally, one or a few at a time.
- YOU MUST call the corresponding save tool after collecting each section. This is critical.
- After calling a save tool, continue to the next section.
- Do NOT make up data.
- If the customer confirms the review, call submit_vds_form IMMEDIATELY.
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


# =============================================
# AGENT CREATION
# =============================================

ALL_TOOLS = [
    list_ntc_services, save_billing_poc, save_technical_poc,
    setup_servers, save_server_config,
    save_general_details, review_vds_form, submit_vds_form,
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
