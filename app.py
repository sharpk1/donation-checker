# app.py
import streamlit as st
from churchScrape import check_client_portal

st.title('Client Portal Option Checker v3')

url_input = st.text_area("Enter the URLs (one per line):")
urls = [u.strip() for u in url_input.splitlines() if u.strip()]

status = st.empty()

if st.button("Check"):
    if not urls:
        st.warning("Please enter at least one URL.")
    else:
        needs_investigation, found = [], []
        for url in urls:
            status.write(f"Currently checking: {url}")
            has_portal, message = check_client_portal(url)
            if has_portal is True:
                found.append((url, message))
            elif has_portal is False:
                needs_investigation.append((url, message))
            else:
                needs_investigation.append((url, message))  # None = request error
        status.write("Check completed!")

        if found:
            st.subheader("Portals Found:")
            for u, msg in found:
                st.write(f"- **{u}** — {msg}")

        st.subheader("URLs Needing Further Investigation:")
        if needs_investigation:
            for u, msg in needs_investigation:
                st.write(f"- **{u}** — {msg}")
        else:
            st.write("None 🎉")
