import requests
from bs4 import BeautifulSoup
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_latest_jobs():
    """
    Fetches the list of latest jobs from the main listing page.
    Returns a list of dictionaries: {'title': str, 'url': str}
    """
    url = "https://sarkariresult.com.cm/latest-jobs/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        jobs = []
        # Sarkari sites usually list jobs in a specific container or just unordered lists
        # We look for all links that contain typical job keywords or are in the main content area
        for link in soup.find_all('a'):
            text = link.get_text(strip=True)
            href = link.get('href')
            
            # Simple filter to ensure we get relevant job links
            # Added case-insensitive check and 'Form' keyword for robustness
            if href and ("online form" in text.lower() or "apply" in text.lower()) and href.startswith("http"):
                jobs.append({
                    "title": text,
                    "url": href
                })
        
        return jobs[:10] # Return top 10 latest jobs
    except Exception as e:
        logger.error(f"Error fetching latest jobs: {e}")
        return []

def get_job_details(job_url):
    """
    Fetches detailed information from a specific job URL.
    Extracts: Important Dates, Application Fee, Age Limit, vacancy, and Apply Links.
    """
    try:
        response = requests.get(job_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        details = {
            "title": "",
            "dates": [],
            "fees": [],
            "age_limit": [],
            "links": {}
        }
        
        # 1. Get Title
        h1 = soup.find('h1')
        if h1:
            details['title'] = h1.get_text(strip=True)
        else:
            # Fallback if no h1, try finding the first major header
            h2 = soup.find('h2')
            if h2: details['title'] = h2.get_text(strip=True)

        # 2. Extract Data by Keywords (Dates, Fee, Age)
        # We iterate through all text elements to find headers, then grab the content following them
        # Added 'p' and 'font' tags which sometimes contain headers in older HTML layouts
        text_elements = soup.find_all(['b', 'strong', 'h2', 'h3', 'p', 'font'])
        
        for el in text_elements:
            text = el.get_text(strip=True).lower()
            
            # Helper to get the next list, table, or text content
            def get_following_text(element):
                content = []
                # Strategy 1: Look for immediate sibling container (ul, table, div)
                curr = element.find_next(['ul', 'table', 'div'])
                
                # Check if the container is "close enough" (not halfway down the page)
                # If we found a container, parse it
                if curr:
                    # Check lists
                    for li in curr.find_all('li'):
                        clean_li = li.get_text(strip=True)
                        if clean_li: content.append(clean_li)
                    
                    # Check table rows if list was empty
                    if not content:
                        for tr in curr.find_all('tr'):
                            clean_tr = tr.get_text(" ", strip=True) # Join cells with space
                            if clean_tr: content.append(clean_tr)
                            
                # Strategy 2: If no structured container, capture plain text siblings
                # This handles cases where data is just lines of text separated by <br>
                if not content:
                    for sibling in element.next_siblings:
                        if sibling.name in ['b', 'strong', 'h2', 'h3']: # Stop at next header
                            break
                        if isinstance(sibling, str):
                            clean_text = sibling.strip()
                            if clean_text: content.append(clean_text)
                        elif sibling.name in ['br', 'p', 'span']:
                            clean_text = sibling.get_text(strip=True)
                            if clean_text: content.append(clean_text)
                            
                return content

            # Robust matching for keywords
            if "important dates" in text or "dates" in text and "start" in text:
                # Avoid overwriting if we already found better data
                if not details['dates']: 
                    details['dates'] = get_following_text(el)
            elif "application fee" in text or "fee details" in text:
                if not details['fees']:
                    details['fees'] = get_following_text(el)
            elif "age limit" in text or "age criteria" in text:
                if not details['age_limit']:
                    details['age_limit'] = get_following_text(el)

        # 3. Extract Important Links (Apply Online, Notification)
        # Usually found in a table at the bottom.
        # Added logic to find ALL links in the row (e.g. Registration | Login)
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    label = cols[0].get_text(strip=True).lower()
                    
                    # Check last column for links
                    link_col = cols[-1]
                    found_links = link_col.find_all('a')
                    
                    for link_tag in found_links:
                        url = link_tag.get('href')
                        link_text = link_tag.get_text(strip=True)
                        
                        if url and "http" in url:
                            if "apply online" in label or "registration" in label:
                                # Use specific text if available (e.g., "Login" vs "Registration")
                                key = "Apply Online"
                                if "login" in link_text.lower():
                                    key = "Apply - Login"
                                elif "registration" in link_text.lower():
                                    key = "Apply - Registration"
                                details['links'][key] = url
                                
                            elif "notification" in label:
                                details['links']['Notification'] = url
                            elif "official website" in label:
                                details['links']['Official Website'] = url

        return details

    except Exception as e:
        logger.error(f"Error fetching job details: {e}")
        return None

# --- TEST BLOCK ---
if __name__ == "__main__":
    print("Fetching Latest Jobs...")
    latest = get_latest_jobs()
    
    if latest:
        print(f"Found {len(latest)} jobs.")
        first_job = latest[0]
        print(f"\nScraping details for: {first_job['title']}")
        print(f"URL: {first_job['url']}")
        
        data = get_job_details(first_job['url'])
        
        if data:
            print("\n--- JOB DETAILS ---")
            print(f"Title: {data.get('title')}")
            print("\n[Important Dates]")
            for d in data.get('dates', []): print(f"- {d}")
            
            print("\n[Application Fees]")
            for f in data.get('fees', []): print(f"- {f}")
            
            print("\n[Important Links]")
            for k, v in data.get('links', {}).items():
                print(f"{k}: {v}")
    else:
        print("No jobs found. Check the URL or selector.")
