import streamlit as st
from churchScrape import check_donation_option  # Import your function

st.title('Client Portal Option Checker v2')

# Text area for input
url_input = st.text_area("Enter the URLs (one per line):")
urls = url_input.split('\n')  # This splits the input into lines, creating a list of URLs

status_text = st.empty()

if st.button('Check'):
    if urls:
        results = []
        needs_investigation = []
        for url in urls:
            if url.strip():  # Check if the URL is not empty and strip any whitespace
                status_text.text(f"Currently checking: {url}")
                has_donation, message = check_donation_option(url)
                results.append(f"{url} - {message}")
                if not has_donation:
                    needs_investigation.append(url)
        status_text.text("Check completed!")  # Update status after completion
        
        # # Display results
        # for result in results:
        #     st.write(result)
        
        # Display URLs that need further investigation
        if needs_investigation:
            st.subheader("URLs Needing Further Investigation:")
            for url in needs_investigation:
                st.write(url)
        else:
            st.write("No websites on the list need further checking.")
    else:
        st.write("Please enter at least one URL.")
