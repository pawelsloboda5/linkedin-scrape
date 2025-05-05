# LinkedIn Scraper Configuration

# Target educational institutions to search for
TARGET_INSTITUTIONS = [
    "National Defense University",
    "Industrial College of the Armed Forces",
    "Eisenhower School for National Security and Resource Strategy",
    "Information Resources Management College",
    "Joint Forces Staff College"
]

# Search parameters
SEARCH_SETTINGS = {
    "profiles_per_institution": 5,  # Number of profiles to scrape per institution
    "delay_between_profiles": 3,    # Delay in seconds between profile scrapes
    "timeout_wait": 10,             # Wait timeout for page elements in seconds
    "max_pages_per_institution": 5, # Number of pages to scrape per institution
    "page_load_delay": 2            # Delay in seconds after loading a new page
}

# Output settings
OUTPUT_SETTINGS = {
    "csv_filename": "ndu_alumni.csv",
    "log_filename": "alumni_search.log",
    "json_filename": "extracted_profiles.json"
}

# Browser settings
BROWSER_SETTINGS = {
    "chrome_driver_path": "C:\\WebDriver\\bin\\chromedriver.exe"
}

# OpenAI API settings - Note OpenAI API is not required if we're just collecting screenshots
OPENAI_SETTINGS = {
    # Switch between standard OpenAI and Azure OpenAI
    "use_azure": False,  # Set to True for Azure OpenAI, False for standard OpenAI
    
    # Standard OpenAI settings (used when use_azure is False)
    "api_url": "https://api.openai.com/v1/chat/completions",
    "model": "gpt-4.1-mini",
    
    # Azure OpenAI settings (used when use_azure is True)
    "azure_api_url": "https://<resource-name>.openai.azure.com/openai/deployments/<deployment-id>/chat/completions?api-version=2024-10-21", 
    "azure_deployment_id": "gpt-4-vision",  # This should match your deployment name in Azure
    
    # Common settings
    "max_tokens": 1000,
    "temperature": 0.7,
    "enabled": True,  # Set to True if you want to use OpenAI API
}

# LinkedIn uses dynamic class names that change frequently
# These XPaths are less likely to break with UI changes
LINKEDIN_SELECTORS = {
    "all_filters_button": "//button[contains(text(), 'All filters')]",
    "school_input": "//label[contains(text(), 'School')]/following-sibling::input",
    "apply_button": "//button[contains(text(), 'Apply')]",
    "search_box": "//input[contains(@class, 'search-global-typeahead')]",
    
    # LinkedIn pagination elements
    "next_page_button": [
        "button.artdeco-pagination__button--next",
        "button[aria-label='Next']",
        ".artdeco-pagination__button--next",
        "//button[contains(@class, 'artdeco-pagination__button--next')]",
        "//button[@aria-label='Next']"
    ],
    
    # Updated selectors for profile links - multiple options to try
    "profile_links": [
        ".entity-result__title a",
        ".reusable-search__result-container a.app-aware-link",
        "li.reusable-search__result-container a[href*='/in/']",
        "//span[contains(@class,'entity-result__title')]/a",
        "//a[contains(@class,'app-aware-link') and contains(@href,'/in/')]"
    ],
    
    # Updated selectors for search results container
    "search_results": [
        ".search-results-container",
        "ul.reusable-search__entity-result-list",
        ".entity-result__content",
        "//div[contains(@class,'search-results-container')]",
        "//ul[contains(@class,'reusable-search__entity-result-list')]"
    ]
} 