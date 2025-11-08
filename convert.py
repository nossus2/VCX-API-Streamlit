# hash_credentials.py
from pathlib import Path
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

CFG_PATH = Path("app/data/config.yaml")

def main():
    with open(CFG_PATH, "r") as f:
        cfg = yaml.load(f, Loader=SafeLoader)

    # Hash all plaintext passwords in-place (expects the v0.4+ credentials shape)
    cfg["credentials"] = stauth.Hasher.hash_passwords(cfg["credentials"])

    # Write back the file (now contains bcrypt hashes, no plaintext)
    with open(CFG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    print("✅ config.yaml updated with hashed passwords.")

if __name__ == "__main__":
    main()