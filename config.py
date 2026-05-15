# --- Database connection details ---
DB_HOST = "dpg-d7ssbhgg4nts73e4o7mg-a.oregon-postgres.render.com"
DB_NAME = "demo_db_brb1"
DB_USER = "demo_db_brb1_user"
DB_PASSWORD = "dIbUkNpX5oAZxK2DtVHafYjWEtyLkxDJ"
DB_PORT = "5432"

# --- SMTP Configuration ---
SMTP_SERVER = "mail.ntc.org.pk"
SMTP_PORT = 587
SMTP_SENDER_EMAIL = "test.jawad@ntc.org.pk"
SMTP_USERNAME = "test.jawad@ntc.org.pk"
SMTP_PASSWORD = "16$secure@NTC"
EMAIL_OTP_EXPIRY_MINUTES = 5
VDS_RECIPIENT_EMAIL = "jawad.malakandkp@gmail.com"

# --- NTC Services ---
NTC_SERVICES = [
    {"name": "IaaS VDS (Virtual Dedicated Server)", "key": "vds", "available": True},
    {"name": "E-mail Services", "key": "email", "available": False},
    {"name": "Co-location", "key": "colocation", "available": False},
    {"name": "Shared Web Hosting", "key": "hosting", "available": False},
    {"name": "SMS", "key": "sms", "available": False},
    {"name": "Network Services", "key": "network", "available": False},
]

# --- VDS Form Field Definitions (exact performa fields) ---
BILLING_POC_FIELDS = [
    ("name", "Name"),
    ("designation", "Designation"),
    ("address", "Address"),
    ("phone_no", "Phone No."),
    ("office_no", "Office No."),
]

TECHNICAL_POC_FIELDS = [
    ("name", "Name"),
    ("designation", "Designation"),
    ("address", "Address"),
    ("phone_no", "Phone No."),
    ("office_no", "Office No."),
    ("server_description", "Server Description"),
    ("url", "URL"),
    ("server", "Server"),
]

SERVER_DETAIL_FIELDS = [
    ("cpu", "CPU"),
    ("ram", "RAM"),
    ("storage_type", "Storage Type"),
    ("storage_capacity", "Storage Capacity"),
    ("os_name_version", "OS Name with Version"),
    ("os_gui_or_minimal", "OS GUI or Minimal"),
]

GENERAL_DETAIL_FIELDS = [
    ("internet_uplink_mbps", "Internet Uplink (in Mbps)"),
    ("endpoint_security", "Endpoint Security Licenses Requirements"),
    ("backup_as_service", "Backup as a Service"),
    ("ssl_type", "DV SSL or Wildcard SSL"),
    ("ssl_vpn", "SSL VPN for VM Management (existing or new)"),
    ("domain_registration", "Domain Registration and Renewal (Y/N)"),
    ("public_ip", "Public IP Required (Y/N)"),
    ("additional_requirements", "Additional Requirements"),
]

STORAGE_TYPES = ["SAS", "Auto Tiered", "NLSAS", "SSD", "NVME"]
