# app.py
import streamlit as st
from churchScrape import check_react_job_us  # ⬅️ new import

st.title('React US Job Checker')

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
            has_match, message = check_react_job_us(url)
            if has_match is True:
                found.append((url, message))
            elif has_match is False:
                needs_investigation.append((url, message))
            else:
                needs_investigation.append((url, message))  # None = request error
        status.write("Check completed!")

        if found:
            st.subheader("React + US Confirmed:")
            for u, msg in found:
                st.write(f"- **{u}** — {msg}")

        st.subheader("URLs Needing Further Investigation:")
        if needs_investigation:
            for u, msg in needs_investigation:
                st.write(f"- **{u}** — {msg}")
        else:
            st.write("None 🎉")
