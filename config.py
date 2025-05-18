import os
import re
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

HASHTOPOLIS_URL = os.getenv("HASHTOPOLIS_URL", "http://your.hashtopolis.server")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "your_agent_token_here")

TRUSTED_ROLE_NAME = os.getenv("TRUSTED_ROLE_NAME", "Trusted Agent")

SUPPORTED_ALGORITHMS = {
    "md5": 0,
    "sha1": 100,
    "sha224": 1400,
    "sha256": 1400,
    "sha384": 10800,
    "sha512": 1700,
    "sha3-256": 17400,
    "sha3-512": 17410,
    "ripemd160": 6100,
    "whirlpool": 6100,
    "ntlm": 1000,
    "netntlmv2": 5600,
    "mssql2000": 131,
    "mssql2005": 132,
    "mysql323": 200,
    "mysql41": 300,
    "bcrypt": 3200,
    "asrep23": 18200,
    "asrep18": 19700,
}

HASH_PATTERNS = {
    "md5": re.compile(r"^[a-fA-F0-9]{32}$"),
    "sha1": re.compile(r"^[a-fA-F0-9]{40}$"),
    "sha224": re.compile(r"^[a-fA-F0-9]{56}$"),
    "sha256": re.compile(r"^[a-fA-F0-9]{64}$"),
    "sha384": re.compile(r"^[a-fA-F0-9]{96}$"),
    "sha512": re.compile(r"^[a-fA-F0-9]{128}$"),
    "sha3-256": re.compile(r"^[a-fA-F0-9]{64}$"),
    "sha3-512": re.compile(r"^[a-fA-F0-9]{128}$"),
    "ripemd160": re.compile(r"^[a-fA-F0-9]{40}$"),
    "whirlpool": re.compile(r"^[a-fA-F0-9]{128}$"),
    "ntlm": re.compile(r"^[a-fA-F0-9]{32}$"),
    "netntlmv2": re.compile(r"^[a-zA-Z0-9\-_$]+::[a-zA-Z0-9\-_$]*:[a-fA-F0-9]{16}:[a-fA-F0-9]+:[a-fA-F0-9]+$"),
    "mssql2000": re.compile(r"^[a-fA-F0-9]{54}$"),
    "mssql2005": re.compile(r"^[a-fA-F0-9]{40}$"),
    "mysql323": re.compile(r"^[a-fA-F0-9]{16}$"),
    "mysql41": re.compile(r"^[a-fA-F0-9]{40}$"),
    "bcrypt": re.compile(r"^\$2[ayb]\$[0-9]{2}\$[a-zA-Z0-9./]{53}$"),
    "asrep23": re.compile(r"^\$krb5asrep\$[0-9]+\$[a-zA-Z0-9\-_.]+@[a-zA-Z0-9\-_.]+:.*\$[a-fA-F0-9]+$"),
    "asrep18": re.compile(r"^\$krb5tgs\$18\$[a-zA-Z0-9\-./]+\$[A-Z]+\$\*[a-zA-Z0-9\-./]+\*\$[a-fA-F0-9]+\$[a-fA-F0-9]+$"),
}

