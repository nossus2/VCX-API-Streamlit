import yaml
from yaml.loader import SafeLoader
from pathlib import Path
import streamlit as st
import streamlit_authenticator as stauth

CONFIG_PATH = Path("app/data/config.yaml")

@st.cache_resource
def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.load(f, Loader=SafeLoader)

cfg = load_config()

st.set_page_config(page_title=cfg["ui"].get("title", "Portal"), page_icon="🔐", layout="centered")

# Build authenticator with hashed passwords (we already hashed them)
authenticator = stauth.Authenticate(
    credentials=cfg["credentials"],            # hashed dict
    cookie_name=cfg["cookie"]["name"],
    key=cfg["cookie"]["key"],
    cookie_expiry_days=cfg["cookie"]["expiry_days"],
    auto_hash=False                            # important—already hashed
)

# Simple header
st.title(cfg["ui"].get("title", "Portal"))
st.caption(cfg["ui"].get("subtitle", ""))

# Hide the sidebar page navigation until the user is authenticated
if st.session_state.get("authentication_status") is not True:
    # Start with the sidebar collapsed AND hide the page list
    st.set_page_config(initial_sidebar_state="collapsed")
    st.markdown("""
        <style>
        /* Hide the built-in multi-page navigation */
        [data-testid="stSidebarNav"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
else:
    # Once authenticated, let the sidebar/nav render normally
    st.set_page_config(initial_sidebar_state="expanded")

# Render the login widget (returns None in 'main'/'sidebar')
# Render the login form (v0.4+ returns None; values are in session_state)
authenticator.login(location="main", fields={"Form name": "Log in"})

auth_status = st.session_state.get("authentication_status")
name        = st.session_state.get("name")
username    = st.session_state.get("username")

if auth_status is True:
    # Show logout ONCE with a unique key for THIS script
    authenticator.logout("Log out", "sidebar", key="logout-loginpage")

    # Auto-redirect to your page exactly once per fresh login
    if not st.session_state.get("did_auto_redirect"):
        st.session_state["did_auto_redirect"] = True
        st.switch_page("pages/app.py")  # <-- your target

    # (Optional) visible link/button as a fallback
    st.page_link("pages/app.py", label="Open: Student Interim Search")
    if st.button("Go now", key="goto-app"):
        st.switch_page("pages/app.py")

elif auth_status is False:
    st.error("Invalid username or password.")
else:
    st.info("Please sign in.")


def role_of(u):
    try:
        return cfg["credentials"]["usernames"][u].get("role", "")
    except Exception:
        return ""

if auth_status is False:
    st.error("Invalid username or password.")
elif auth_status is None:
    st.info("Please sign in.")
else:
    role = role_of(username)
    st.success(f"Signed in as **{name}** ({role or 'user'})")

    st.session_state["user"] = {"username": username, "name": name, "role": role}

    tabs = ["🏠 Home"]
    if role in ("teacher", "admin"):
        tabs.append("📊 Teacher Tools")
        # OPTIONAL: show a manual link/button
        if role == "admin":
            tabs.append("🛠️ Admin Panel")

    t = st.tabs(tabs)

    with t[0]:
        st.subheader("Dashboard")
        st.write("Welcome!")

    idx = 1
    if "📊 Teacher Tools" in tabs:
        with t[idx]:
            st.subheader("Teacher Tools")
            st.write("Upload rosters, view reports, etc.")
        idx += 1
    if "🛠️ Admin Panel" in tabs:
        with t[idx]:
            st.subheader("Admin Panel")
            st.warning("Admin-only actions.")