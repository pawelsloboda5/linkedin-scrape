from linkedin_scraper import Person, actions
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import json

# Import configuration
from config import (
    TARGET_INSTITUTIONS,
    BROWSER_SETTINGS
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('webdriver_manager').setLevel(logging.WARNING)

def extract_education(profile_url, email, password, chrome_driver_path=None):
    """
    Extract education details from a LinkedIn profile.
    
    Args:
        profile_url: URL of the LinkedIn profile
        email: LinkedIn login email
        password: LinkedIn login password
        chrome_driver_path: Path to chromedriver.exe (optional)
    
    Returns:
        List of education details
    """
    driver = None
    try:
        # Initialize the driver using Selenium 4 approach
        chrome_driver_path = chrome_driver_path or BROWSER_SETTINGS["chrome_driver_path"]
        
        if chrome_driver_path and os.path.exists(chrome_driver_path):
            print(f"Using ChromeDriver from: {chrome_driver_path}")
            service = Service(chrome_driver_path)
            driver = webdriver.Chrome(service=service)
        else:
            # Use webdriver_manager to automatically download and manage ChromeDriver
            print("Using webdriver_manager to handle ChromeDriver")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service)
        
        driver.maximize_window()
        
        # Login to LinkedIn
        actions.login(driver, email, password)
        logging.info("Successfully logged in to LinkedIn")
        
        # Scrape the profile
        logging.info(f"Scraping profile: {profile_url}")
        person = Person(profile_url, driver=driver, close_on_complete=False)
        
        # Extract education details
        education_data = []
        if hasattr(person, 'educations') and person.educations:
            for edu in person.educations:
                education_info = {}
                
                if hasattr(edu, 'institution'):
                    education_info['institution'] = edu.institution
                
                if hasattr(edu, 'degree'):
                    education_info['degree'] = edu.degree
                
                if hasattr(edu, 'date_range'):
                    education_info['date_range'] = edu.date_range
                
                # Check if this is one of our target institutions
                is_target = False
                if 'institution' in education_info:
                    for target in TARGET_INSTITUTIONS:
                        if target.lower() in education_info['institution'].lower():
                            is_target = True
                            education_info['is_target'] = True
                            break
                
                education_data.append(education_info)
            
            logging.info(f"Found {len(education_data)} education entries")
        else:
            logging.info("No education data found")
        
        # Print basic profile info
        print(f"\nProfile: {person.name}")
        print(f"Current: {person.job_title} at {person.company}")
        
        # Print education details
        print("\nEducation History:")
        if education_data:
            for i, edu in enumerate(education_data, 1):
                institution = edu.get('institution', 'Unknown Institution')
                is_target = edu.get('is_target', False)
                tag = "** TARGET INSTITUTION **" if is_target else ""
                
                print(f"\n{i}. {institution} {tag}")
                print(f"   Degree: {edu.get('degree', 'N/A')}")
                print(f"   Period: {edu.get('date_range', 'N/A')}")
        else:
            print("No education data available")
        
        return education_data
    
    except Exception as e:
        logging.error(f"Error extracting education data: {e}")
        return []
    
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    # Get credentials from environment or input
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")
    
    if not email:
        email = input("Enter your LinkedIn email: ")
    if not password:
        password = input("Enter your LinkedIn password: ")
    
    # Get profile URL to analyze
    profile_url = input("Enter LinkedIn profile URL to analyze: ")
    
    # Extract and display education data
    education_data = extract_education(profile_url, email, password)
    
    # Save the data to a JSON file for reference
    if education_data:
        with open('education_data.json', 'w') as f:
            json.dump(education_data, f, indent=2)
        print("\nEducation data saved to education_data.json") 