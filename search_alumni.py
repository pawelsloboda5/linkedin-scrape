from linkedin_scraper import Person, actions
import os
import logging
import csv
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import configuration
from config import (
    TARGET_INSTITUTIONS,
    SEARCH_SETTINGS,
    OUTPUT_SETTINGS,
    BROWSER_SETTINGS,
    LINKEDIN_SELECTORS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename=OUTPUT_SETTINGS["log_filename"],
    filemode='w'  # Overwrite existing log file
)

# Also log to console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# Suppress noisy logs
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('webdriver_manager').setLevel(logging.WARNING)

class AlumniScraper:
    def __init__(self, email, password, chrome_driver_path=None):
        self.email = email
        self.password = password
        self.chrome_driver_path = chrome_driver_path or BROWSER_SETTINGS["chrome_driver_path"]
        self.driver = None
        self.alumni_data = []
        
    def initialize_driver(self):
        """Initialize the Chrome driver."""
        try:
            # For Selenium 4, use Service class
            if self.chrome_driver_path and os.path.exists(self.chrome_driver_path):
                logging.info(f"Using ChromeDriver from: {self.chrome_driver_path}")
                service = Service(self.chrome_driver_path)
                self.driver = webdriver.Chrome(service=service)
            else:
                # Use webdriver_manager to automatically download and manage ChromeDriver
                logging.info("Using webdriver_manager to handle ChromeDriver")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service)
            
            self.driver.maximize_window()
            logging.info("ChromeDriver initialized successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to initialize driver: {e}")
            return False
    
    def login(self):
        """Login to LinkedIn."""
        try:
            actions.login(self.driver, self.email, self.password)
            logging.info("Successfully logged in to LinkedIn")
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False
    
    def search_for_institution(self, institution_name):
        """Search for profiles with the specified institution in education."""
        try:
            # Navigate to LinkedIn search page
            self.driver.get("https://www.linkedin.com/search/results/people/")
            time.sleep(2)
            
            # Click on the filters button if available
            try:
                filters_button = WebDriverWait(self.driver, SEARCH_SETTINGS["timeout_wait"]).until(
                    EC.element_to_be_clickable((By.XPATH, LINKEDIN_SELECTORS["all_filters_button"]))
                )
                filters_button.click()
                time.sleep(1)
                
                # Look for the school filter
                school_input = WebDriverWait(self.driver, SEARCH_SETTINGS["timeout_wait"]).until(
                    EC.element_to_be_clickable((By.XPATH, LINKEDIN_SELECTORS["school_input"]))
                )
                school_input.send_keys(institution_name)
                time.sleep(1)
                
                # Apply filters
                apply_button = WebDriverWait(self.driver, SEARCH_SETTINGS["timeout_wait"]).until(
                    EC.element_to_be_clickable((By.XPATH, LINKEDIN_SELECTORS["apply_button"]))
                )
                apply_button.click()
                time.sleep(2)
            except Exception as e:
                # If filters UI has changed, try direct search
                logging.warning(f"Filter UI may have changed, trying direct search: {e}")
                search_box = WebDriverWait(self.driver, SEARCH_SETTINGS["timeout_wait"]).until(
                    EC.element_to_be_clickable((By.XPATH, LINKEDIN_SELECTORS["search_box"]))
                )
                search_query = f"{institution_name} education"
                search_box.clear()
                search_box.send_keys(search_query)
                search_box.send_keys(Keys.RETURN)
                time.sleep(2)
            
            logging.info(f"Searched for institution: {institution_name}")
            return True
        except Exception as e:
            logging.error(f"Error searching for institution {institution_name}: {e}")
            return False
    
    def collect_profile_urls(self, limit=10):
        """Collect profile URLs from search results."""
        profile_urls = []
        try:
            # Wait for search results to load
            WebDriverWait(self.driver, SEARCH_SETTINGS["timeout_wait"]).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, LINKEDIN_SELECTORS["search_results"]))
            )
            
            # Collect profile links
            profile_elements = self.driver.find_elements(By.CSS_SELECTOR, LINKEDIN_SELECTORS["profile_links"])
            
            for i, element in enumerate(profile_elements):
                if i >= limit:
                    break
                url = element.get_attribute('href')
                if url and 'linkedin.com/in/' in url:
                    profile_urls.append(url.split('?')[0])  # Remove query parameters
            
            logging.info(f"Collected {len(profile_urls)} profile URLs")
            return profile_urls
        except Exception as e:
            logging.error(f"Error collecting profile URLs: {e}")
            return profile_urls
    
    def process_profile(self, profile_url):
        """Process a single profile to extract education details."""
        try:
            person = Person(profile_url, driver=self.driver, close_on_complete=False)
            
            # Check if this person has any of the target institutions in their education
            relevant_education = []
            for edu in person.educations:
                school = edu.institution if hasattr(edu, 'institution') else ""
                
                # Check if any target institution is in the school name
                for target in TARGET_INSTITUTIONS:
                    if target.lower() in school.lower():
                        relevant_education.append({
                            'institution': school,
                            'degree': edu.degree if hasattr(edu, 'degree') else "",
                            'date_range': edu.date_range if hasattr(edu, 'date_range') else ""
                        })
                        break
            
            if relevant_education:
                # Collect general profile data
                profile_data = {
                    'name': person.name,
                    'url': profile_url,
                    'title': person.job_title,
                    'company': person.company,
                    'education': relevant_education
                }
                
                self.alumni_data.append(profile_data)
                logging.info(f"Found relevant education for {person.name}")
                return True
            
            logging.info(f"No relevant education found for {person.name}")
            return False
        except Exception as e:
            logging.error(f"Error processing profile {profile_url}: {e}")
            return False
    
    def export_to_csv(self, filename=None):
        """Export the collected alumni data to CSV."""
        try:
            if not self.alumni_data:
                logging.warning("No alumni data to export")
                return False
            
            filename = filename or OUTPUT_SETTINGS["csv_filename"]
            
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                # Create a flat structure for CSV
                fieldnames = ['name', 'url', 'title', 'company', 'institution', 'degree', 'date_range']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                
                for profile in self.alumni_data:
                    for edu in profile['education']:
                        row = {
                            'name': profile['name'],
                            'url': profile['url'],
                            'title': profile['title'],
                            'company': profile['company'],
                            'institution': edu['institution'],
                            'degree': edu['degree'],
                            'date_range': edu['date_range']
                        }
                        writer.writerow(row)
            
            # Also save the raw data to JSON for complete record
            with open(filename.replace('.csv', '.json'), 'w', encoding='utf-8') as json_file:
                json.dump(self.alumni_data, json_file, indent=2)
            
            logging.info(f"Exported {len(self.alumni_data)} alumni profiles to {filename}")
            return True
        except Exception as e:
            logging.error(f"Error exporting to CSV: {e}")
            return False
    
    def run(self, profiles_per_institution=None):
        """Run the complete alumni search process."""
        profiles_per_institution = profiles_per_institution or SEARCH_SETTINGS["profiles_per_institution"]
        
        if not self.initialize_driver():
            return False
        
        try:
            if not self.login():
                return False
            
            # Allow some time after login
            time.sleep(5)
            
            for institution in TARGET_INSTITUTIONS:
                logging.info(f"Searching for alumni of: {institution}")
                
                if not self.search_for_institution(institution):
                    continue
                
                profile_urls = self.collect_profile_urls(limit=profiles_per_institution)
                
                for url in profile_urls:
                    self.process_profile(url)
                    # Be nice to LinkedIn's servers
                    time.sleep(SEARCH_SETTINGS["delay_between_profiles"])
            
            self.export_to_csv()
            return True
        except Exception as e:
            logging.error(f"Error in run process: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    # Get credentials from environment or input
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")
    
    if not email:
        email = input("Enter your LinkedIn email: ")
    if not password:
        password = input("Enter your LinkedIn password: ")
    
    scraper = AlumniScraper(email, password)
    logging.info("Starting LinkedIn NDU Alumni Scraper")
    scraper.run() 