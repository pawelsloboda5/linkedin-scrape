import os
import logging
import json
import time
import base64
import requests
from PIL import Image
from io import BytesIO
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Import the existing scraper class
from search_alumni import AlumniScraper
from config import TARGET_INSTITUTIONS, OUTPUT_SETTINGS, SEARCH_SETTINGS, LINKEDIN_SELECTORS, OPENAI_SETTINGS

# Configure logging for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('webdriver_manager').setLevel(logging.WARNING)

# Configure OpenAI API
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logging.warning("OpenAI API key not found in environment variables.")
    if OPENAI_SETTINGS.get("enabled", False):
        # Check if we're using Azure OpenAI
        if OPENAI_SETTINGS.get("use_azure", False):
            OPENAI_API_KEY = input("Enter your Azure OpenAI API key (or leave blank to disable OpenAI features): ")
            if not OPENAI_API_KEY:
                logging.info("Azure OpenAI features will be disabled")
                OPENAI_SETTINGS["enabled"] = False
            else:
                logging.info("Azure OpenAI API key provided")
        else:
            OPENAI_API_KEY = input("Enter your OpenAI API key (or leave blank to disable OpenAI features): ")
            if not OPENAI_API_KEY:
                logging.info("OpenAI features will be disabled")
                OPENAI_SETTINGS["enabled"] = False
            else:
                logging.info("OpenAI API key provided")
    else:
        logging.info("OpenAI features are disabled in config")
else:
    if OPENAI_SETTINGS.get("use_azure", False):
        logging.info("Azure OpenAI API key found in environment variables")
    else:
        logging.info("OpenAI API key found in environment variables")

class ScreenshotAlumniScraper(AlumniScraper):
    """Enhanced version of AlumniScraper that uses screenshots and OpenAI Vision API."""
    
    def __init__(self, email, password, chrome_driver_path=None):
        super().__init__(email, password, chrome_driver_path)
        self.vision_data = []
        
    def take_screenshot(self, filename=None):
        """Take a screenshot of the current page and save it"""
        if filename is None:
            timestamp = int(time.time())
            filename = f"search_results_{timestamp}.png"
        
        filepath = os.path.join("screenshots", filename)
        
        # Create screenshots directory if it doesn't exist
        os.makedirs("screenshots", exist_ok=True)
        
        self.driver.save_screenshot(filepath)
        logging.info(f"Screenshot saved to {filepath}")
        return filepath
    
    def take_profile_screenshot(self, profile_index, institution_name, page_num):
        """Take a screenshot of a specific profile entry in the search results"""
        try:
            # Create profile_screenshots directory if it doesn't exist
            os.makedirs("profile_screenshots", exist_ok=True)
            
            # Create a directory for the current institution if it doesn't exist
            institution_dir = os.path.join("profile_screenshots", institution_name.replace(' ', '_'))
            os.makedirs(institution_dir, exist_ok=True)
            
            # Use JavaScript to find and get the position of the profile element
            js_script = """
            const profileCards = document.querySelectorAll('div.lMypdfcjUtfJtdoPGRBhqTmWVQeCY');
            if (profileCards.length > arguments[0]) {
                const element = profileCards[arguments[0]];
                // Make sure the element is in view
                element.scrollIntoView({behavior: 'auto', block: 'center'});
                
                // Return position data for the element
                const rect = element.getBoundingClientRect();
                return {
                    top: rect.top,
                    left: rect.left,
                    width: rect.width,
                    height: rect.height,
                    found: true
                };
            }
            return {found: false};
            """
            
            # Execute JavaScript to get the element position
            result = self.driver.execute_script(js_script, profile_index)
            
            if not result.get('found', False):
                logging.warning(f"Could not find profile element at index {profile_index + 1} using JavaScript")
                return None
                
            # Take a small pause to ensure the element is fully rendered after scrolling
            time.sleep(1)
            
            # Take full screenshot
            png = self.driver.get_screenshot_as_png()
            img = Image.open(BytesIO(png))
            
            # Calculate the boundaries of the element using the JavaScript results
            left = int(result['left'])
            top = int(result['top'])
            right = int(result['left'] + result['width'])
            bottom = int(result['top'] + result['height'])
            
            # Log the crop dimensions
            logging.info(f"Cropping screenshot to: left={left}, top={top}, right={right}, bottom={bottom}")
            
            # Crop the screenshot to include just the profile element
            img = img.crop((left, top, right, bottom))
            
            # Save the cropped screenshot
            filename = f"{institution_name.replace(' ', '_')}_page{page_num}_profile{profile_index + 1}.png"
            filepath = os.path.join(institution_dir, filename)
            img.save(filepath)
            
            logging.info(f"Profile screenshot saved to {filepath}")
            return filepath
        
        except Exception as e:
            logging.error(f"Error taking profile screenshot: {e}")
            
            # Fallback method: take a screenshot of the entire page and save it
            fallback_filename = f"{institution_name.replace(' ', '_')}_page{page_num}_profile{profile_index + 1}_fallback.png"
            fallback_filepath = os.path.join(institution_dir, fallback_filename)
            self.driver.save_screenshot(fallback_filepath)
            logging.info(f"Saved fallback screenshot to {fallback_filepath}")
            return fallback_filepath
    
    def analyze_screenshot_with_openai(self, screenshot_path):
        """Send screenshot to OpenAI Vision API for analysis using modern OpenAI client library"""
        # Skip API call if OpenAI is disabled
        if not OPENAI_SETTINGS.get("enabled", False):
            logging.info("OpenAI API is disabled, skipping analysis")
            return []
            
        if not OPENAI_API_KEY:
            logging.error("OpenAI API key not set")
            return []
        
        # Read the image and encode it as base64
        with open(screenshot_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        try:
            # Import OpenAI client
            from openai import OpenAI, AzureOpenAI
            
            # Initialize the client based on whether we're using Azure or standard OpenAI
            if OPENAI_SETTINGS.get("use_azure", False):
                # Get Azure settings
                azure_api_url = OPENAI_SETTINGS.get("azure_api_url", "")
                azure_deployment_id = OPENAI_SETTINGS.get("azure_deployment_id", "")
                
                # Check if the URL has placeholders that need to be replaced
                if "<resource-name>" in azure_api_url or "<deployment-id>" in azure_api_url:
                    logging.error("Azure OpenAI URL contains placeholders. Please update your config.py with actual values.")
                    return []
                
                # Extract resource name and api version from the URL
                # URL format: https://<resource-name>.openai.azure.com/openai/deployments/<deployment-id>/chat/completions?api-version=<api-version>
                import re
                resource_match = re.search(r'https://([^.]+)', azure_api_url)
                api_version_match = re.search(r'api-version=([^&]+)', azure_api_url)
                
                if not resource_match or not api_version_match:
                    logging.error("Could not parse Azure OpenAI URL correctly. Please check the format.")
                    return []
                    
                resource_name = resource_match.group(1)
                api_version = api_version_match.group(1)
                
                logging.info(f"Using Azure OpenAI at {resource_name} with deployment {azure_deployment_id}")
                
                client = AzureOpenAI(
                    api_key=OPENAI_API_KEY,
                    azure_endpoint=f"https://{resource_name}.openai.azure.com",
                    api_version=api_version
                )
                model = azure_deployment_id
            else:
                logging.info("Using standard OpenAI API")
                client = OpenAI(api_key=OPENAI_API_KEY)
                model = OPENAI_SETTINGS.get("model", "gpt-4-vision-preview")
            
            logging.info(f"Calling OpenAI API with model: {model}")
            
            # Create the completion request with the image
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "This is a screenshot of LinkedIn search results page. Please identify all LinkedIn profiles visible in this image. For each profile, extract the following information:\n\n1. Full name\n2. Job title\n3. Company/Organization\n4. Location\n5. Education details (if visible)\n6. Any other relevant information (connections, etc.)\n\nFormat the response as a JSON array of profile objects, with each profile having these fields. Please be thorough and extract information for all profiles visible in the image. Only include profiles where you can clearly see the information. Return in this format: {\"profiles\": [...]}."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=OPENAI_SETTINGS.get("max_tokens", 1000),
                temperature=OPENAI_SETTINGS.get("temperature", 0.7)
            )
            
            # Extract profiles from the response
            try:
                # Get the content from the response
                content = response.choices[0].message.content
                
                # Try to parse the JSON
                try:
                    # First attempt - direct JSON parsing
                    data = json.loads(content)
                    profiles = data.get("profiles", [])
                except json.JSONDecodeError:
                    # Second attempt - extract JSON from markdown
                    try:
                        # Look for content between triple backticks
                        json_match = content.split("```json")[1].split("```")[0].strip()
                        data = json.loads(json_match)
                        profiles = data.get("profiles", [])
                    except (IndexError, json.JSONDecodeError):
                        # Third attempt - look for array content
                        try:
                            # If the "profiles" key is missing, look for a direct array
                            start_idx = content.find('[')
                            end_idx = content.rfind(']') + 1
                            if start_idx >= 0 and end_idx > start_idx:
                                json_content = content[start_idx:end_idx]
                                profiles = json.loads(json_content)
                            else:
                                raise json.JSONDecodeError("No JSON array found", content, 0)
                        except (json.JSONDecodeError, ValueError):
                            logging.error("Failed to parse OpenAI response as JSON")
                            logging.debug(f"Raw response: {content}")
                            return []
                
                logging.info(f"Successfully extracted {len(profiles)} profiles from the screenshot")
                return profiles
                
            except Exception as e:
                logging.error(f"Error parsing OpenAI response: {e}")
                return []
        
        except Exception as e:
            logging.error(f"Error calling OpenAI API: {e}")
            return []
    
    def click_next_page(self):
        """Click the 'Next' button to navigate to the next page of results"""
        try:
            for selector in LINKEDIN_SELECTORS["next_page_button"]:
                try:
                    # Try CSS selector first
                    if not selector.startswith("//"):
                        next_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    # Then try XPath if it starts with //
                    else:
                        next_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    
                    logging.info(f"Found 'Next' button with selector: {selector}")
                    next_button.click()
                    time.sleep(SEARCH_SETTINGS["page_load_delay"])
                    return True
                except (TimeoutException, WebDriverException) as e:
                    continue
            
            logging.warning("Could not find or click 'Next' button with any selector")
            return False
        except Exception as e:
            logging.error(f"Error clicking next page button: {e}")
            return False
    
    def get_profile_count_on_page(self):
        """Get the number of profile entries on the current page"""
        try:
            # Try CSS selector for the profile card container first
            profile_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.lMypdfcjUtfJtdoPGRBhqTmWVQeCY")
            if profile_elements and len(profile_elements) > 0:
                logging.info(f"Found {len(profile_elements)} profile elements using CSS selector: div.lMypdfcjUtfJtdoPGRBhqTmWVQeCY")
                return len(profile_elements)
            
            # If CSS selector fails, try the XPath patterns as fallback
            xpath_patterns = [
                "//div[contains(@class, 'search-results-container')]//li[contains(@class, 'reusable-search__result-container')]",
                "//ul[contains(@class, 'reusable-search__entity-result-list')]/li",
                "//div[contains(@class, 'search-results')]/div/ul/li",
                "//div[contains(@class, 'search-results')]/div/div/ul/li",
                "//main//ul/li[contains(@class, 'reusable-search__result-container')]",
                "/html/body/div[5]/div[3]/div[2]/div/div[1]/main/div/div/div[1]/div/ul/li"
            ]
            
            for xpath in xpath_patterns:
                profile_elements = self.driver.find_elements(By.XPATH, xpath)
                if profile_elements and len(profile_elements) > 0:
                    logging.info(f"Found {len(profile_elements)} profile elements using XPath: {xpath}")
                    return len(profile_elements)
            
            logging.warning("No profile elements found with any selector")
            return 0
        except Exception as e:
            logging.error(f"Error getting profile count: {e}")
            return 0
    
    def extract_profile_urls_with_js(self):
        """
        Extract profile URLs using JavaScript
        This is a more reliable way to get the profile URLs when XPath/CSS selectors fail
        """
        try:
            # JavaScript to extract all profile URLs from the page using the exact classes from the HTML
            js_script = """
            // First try the new class names
            let profileCards = document.querySelectorAll('div.lMypdfcjUtfJtdoPGRBhqTmWVQeCY');
            
            // If that doesn't work, try older known selectors as fallback
            if (!profileCards || profileCards.length === 0) {
                profileCards = document.querySelectorAll('li.reusable-search__result-container');
            }
            
            const results = [];
            
            profileCards.forEach(card => {
                // Try to find the profile link using the exact class from the HTML
                const profileLink = 
                    card.querySelector('a.nuXDIvMbeMYWApPugutCOKmVhZzvTYUM') || 
                    card.querySelector('a[href*="/in/"]') ||
                    card.querySelector('a[data-test-app-aware-link]');
                
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    // Extract the name, being careful with the DOM structure
                    let name = 'Unknown';
                    try {
                        name = profileLink.textContent?.trim() || 'Unknown';
                    } catch (e) {
                        // If we can't get the name directly, try to find it in a span
                        const nameSpan = profileLink.querySelector('span[dir="ltr"] span:not(.visually-hidden)');
                        if (nameSpan) {
                            name = nameSpan.textContent?.trim() || 'Unknown';
                        }
                    }
                    
                    // Try to get job title and company using exact classes
                    let jobTitle = '';
                    let company = '';
                    let location = '';
                    
                    const jobTitleEl = card.querySelector('div.QmHtvHCBOiVUdutUPDZihOIsguJlXpIDOWlyM');
                    if (jobTitleEl) {
                        jobTitle = jobTitleEl.textContent?.trim() || '';
                    }
                    
                    const summaryEl = card.querySelector('p.CHpjKodTFmcxnHVPBHSawvwXwVHKzXMWfpzTZI');
                    if (summaryEl) {
                        company = summaryEl.textContent?.trim() || '';
                    }
                    
                    const locationEl = card.querySelector('div.DbgAxgMCMeLqXAmIGwDoxglkpoIEUQClYZqk');
                    if (locationEl) {
                        location = locationEl.textContent?.trim() || '';
                    }
                    
                    results.push({
                        url: href,
                        name: name,
                        job_title: jobTitle,
                        company: company,
                        location: location
                    });
                }
            });
            
            return results;
            """
            
            profiles = self.driver.execute_script(js_script)
            logging.info(f"Extracted {len(profiles)} profile URLs using JavaScript")
            return profiles
        except Exception as e:
            logging.error(f"Error extracting profile URLs with JavaScript: {e}")
            return []
    
    def search_with_screenshots(self, institution_name):
        """Search for an institution and take screenshots for analysis with pagination"""
        if self.search_for_institution(institution_name):
            # Initial page load pause
            time.sleep(SEARCH_SETTINGS["page_load_delay"])
            
            profiles = []
            js_extracted_profiles = []
            current_page = 1
            max_pages = SEARCH_SETTINGS["max_pages_per_institution"]
            
            while current_page <= max_pages:
                logging.info(f"Processing page {current_page} for {institution_name}")
                
                # Take a screenshot of the current page
                screenshot_path = self.take_screenshot(f"{institution_name.replace(' ', '_')}_results_page{current_page}.png")
                
                # Wait for search results to load
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//main//ul/li"))
                    )
                except (TimeoutException, WebDriverException) as e:
                    logging.warning(f"Search results not found on page {current_page}: {e}")
                
                # Try to extract profile URLs with JavaScript as a reliable fallback
                page_profiles = self.extract_profile_urls_with_js()
                if page_profiles:
                    # Add institution and page info to each profile
                    for profile in page_profiles:
                        profile["searched_institution"] = institution_name
                        profile["page_found"] = current_page
                    
                    js_extracted_profiles.extend(page_profiles)
                    logging.info(f"Added {len(page_profiles)} profile URLs from {institution_name} (page {current_page})")
                
                # Only analyze with OpenAI if enabled
                if OPENAI_SETTINGS.get("enabled", False):
                    # Analyze the full page screenshot with OpenAI
                    logging.info(f"Sending full page screenshot to OpenAI for analysis: {screenshot_path}")
                    current_profiles = self.analyze_screenshot_with_openai(screenshot_path)
                    
                    if current_profiles:
                        # Add institution to each profile
                        for profile in current_profiles:
                            profile["searched_institution"] = institution_name
                            profile["page_found"] = current_page
                        
                        profiles.extend(current_profiles)
                        logging.info(f"Added {len(current_profiles)} profiles from {institution_name} (page {current_page})")
                else:
                    # If OpenAI is disabled, just log that we captured screenshots
                    logging.info(f"OpenAI analysis is disabled. Full page screenshot captured: {screenshot_path}")
                
                # Go to next page if we haven't reached the maximum
                if current_page < max_pages:
                    if self.click_next_page():
                        current_page += 1
                        # Wait for the new page to load
                        time.sleep(SEARCH_SETTINGS["page_load_delay"])
                    else:
                        logging.info(f"No more pages available for {institution_name} after page {current_page}")
                        break
                else:
                    break
            
            # If we didn't get profiles from OpenAI but have JS-extracted profiles, use those
            if not profiles and js_extracted_profiles:
                profiles = js_extracted_profiles
                logging.info(f"Using {len(profiles)} profiles extracted via JavaScript")
            
            # Save both types of profiles in separate files
            if js_extracted_profiles:
                os.makedirs("output", exist_ok=True)
                with open(f"output/js_extracted_profiles_{institution_name.replace(' ', '_')}.json", "w", encoding='utf-8') as f:
                    json.dump(js_extracted_profiles, f, indent=2)
                logging.info(f"Saved {len(js_extracted_profiles)} JavaScript-extracted profiles to output/js_extracted_profiles_{institution_name.replace(' ', '_')}.json")
            
            return profiles
        return []
    
    def run_with_screenshots(self):
        """Run the alumni search with screenshot analysis"""
        if not self.initialize_driver():
            return False
        
        try:
            if not self.login():
                return False
            
            # Allow some time after login
            time.sleep(5)
            
            all_profiles = []
            
            for institution in TARGET_INSTITUTIONS:
                try:
                    logging.info(f"Searching for alumni of: {institution}")
                    
                    profiles = self.search_with_screenshots(institution)
                    all_profiles.extend(profiles)
                    
                    # Save the current progress after each institution
                    self.save_profiles(all_profiles)
                    
                    # Be nice to LinkedIn's servers
                    time.sleep(SEARCH_SETTINGS["delay_between_profiles"])
                except Exception as e:
                    logging.error(f"Error processing institution {institution}: {e}")
                    
                    # Attempt to recover by restarting the browser session
                    logging.info("Attempting to restart browser session...")
                    try:
                        if self.driver:
                            self.driver.quit()
                        time.sleep(2)
                        if self.initialize_driver() and self.login():
                            logging.info("Successfully restarted browser session")
                            time.sleep(5)  # Wait after login
                        else:
                            logging.error("Failed to restart browser session")
                            break
                    except Exception as restart_error:
                        logging.error(f"Failed to restart browser: {restart_error}")
                        break
            
            # Final save of all extracted profiles
            if all_profiles:
                self.save_profiles(all_profiles)
            else:
                logging.warning("No profiles were extracted")
                
            return True
            
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_profiles(self, profiles):
        """Save extracted profiles to a JSON file"""
        if profiles:
            os.makedirs("output", exist_ok=True)
            with open(f"output/{OUTPUT_SETTINGS['json_filename']}", "w", encoding='utf-8') as f:
                json.dump(profiles, f, indent=2)
            logging.info(f"Saved {len(profiles)} profiles to output/{OUTPUT_SETTINGS['json_filename']}")

if __name__ == "__main__":
    # Get credentials from environment or input
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")
    
    if not email:
        email = input("Enter your LinkedIn email: ")
    if not password:
        password = input("Enter your LinkedIn password: ")
    
    scraper = ScreenshotAlumniScraper(email, password)
    logging.info("Starting LinkedIn Screenshot Alumni Scraper")
    scraper.run_with_screenshots() 