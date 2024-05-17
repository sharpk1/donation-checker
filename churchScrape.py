import requests
from bs4 import BeautifulSoup
need_further = []


def check_donation_option(url):
    
    try:
        # Sending HTTP request to the given URL
        response = requests.get(url, timeout=10)  # 10 seconds timeout
        response.raise_for_status()  # Raises an HTTPError for bad responses

        # Parsing the content of the page with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # List of keywords to search for
        keywords = [
    'donate', 'give', 'giving', 'donation', 'contribute', 'contribution', 
    'support', 'help', 'fund', 'funding', 'tithing', 'pledge', 'sponsor', 
    'benefactor', 'patron', 'charity', 'philanthropy', 'aid', 'assist', 
    'backing', 'endowment', 'grant', 'gift', 'offering', 'partnership', 
    'relief', 'subsidize', 'underwrite', 'match', 'matching', 'campaign', 
    'fundraise', 'fundraiser', 'capital campaign', 'benefit'
]

        # Searching for the keywords in the text of the webpage
        webpage_text = soup.get_text().lower()
        for keyword in keywords:
            if keyword in webpage_text:
                return True, f"'{keyword}' found on the website for '{url}'."
        
        return False, "No donation-related keywords found on the website."
    
    except requests.RequestException as e:
        need_further.append(url)
        return None, f"Please take a closer look at website: {e}"

