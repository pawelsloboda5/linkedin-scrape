# LinkedIn Alumni Scraper with OpenAI Vision

This tool automatically scrapes LinkedIn for alumni from specific educational institutions using a screenshot-based approach with OpenAI's Vision API to extract profile information.

## Features

- Automatically logs into LinkedIn
- Searches for alumni from specified educational institutions
- Takes screenshots of search results
- Uses OpenAI Vision API to extract profile information from screenshots
- Supports both standard OpenAI API and Azure OpenAI API
- Saves extracted data to JSON for easy analysis

## Requirements

- Python 3.8+
- Chrome browser
- ChromeDriver compatible with your Chrome version
- OpenAI API key with access to GPT-4 Vision models

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up ChromeDriver:
   - Download ChromeDriver from [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads)
   - Make sure the version matches your Chrome browser
   - Place it in the location specified in `config.py` (default: `C:\WebDriver\bin\chromedriver.exe`)

## Usage

1. Configure the tool in `config.py`:
   - Customize `TARGET_INSTITUTIONS` to specify which institutions to search for
   - Configure OpenAI settings based on whether you're using standard OpenAI or Azure OpenAI

2. Run the main scraper script:
   ```
   python scrape_profile.py
   ```

3. The script will:
   - Login to LinkedIn
   - Search for alumni from each specified institution
   - Take screenshots of search results pages
   - Send screenshots to OpenAI Vision API for analysis
   - Save extracted profiles to `output/extracted_profiles.json`

## Configuration Options

### Target Institutions
Update the list of target institutions in `config.py`:

```python
TARGET_INSTITUTIONS = [
    "National Defense University",
    "Industrial College of the Armed Forces",
    "Eisenhower School for National Security and Resource Strategy",
    "Information Resources Management College",
    "Joint Forces Staff College"
]
```

### OpenAI Settings
The tool supports both standard OpenAI API and Azure OpenAI:

```python
OPENAI_SETTINGS = {
    # Switch between standard OpenAI and Azure OpenAI
    "use_azure": False,  # Set to True for Azure OpenAI, False for standard OpenAI
    
    # Standard OpenAI settings (used when use_azure is False)
    "api_url": "https://api.openai.com/v1/chat/completions",
    "model": "gpt-4.1-mini",  # Or other vision-capable models
    
    # Azure OpenAI settings (used when use_azure is True)
    "azure_api_url": "https://<resource-name>.openai.azure.com/openai/deployments/<deployment-id>/chat/completions?api-version=2024-10-21", 
    "azure_deployment_id": "gpt-4-vision",  # This should match your deployment name in Azure
    
    # Common settings
    "max_tokens": 1000,
    "temperature": 0.7,
    "enabled": True,  # Set to True if you want to use OpenAI API
}
```

## Environment Variables

You can set these environment variables to avoid entering them each time:
- `LINKEDIN_EMAIL`: Your LinkedIn email
- `LINKEDIN_PASSWORD`: Your LinkedIn password
- `OPENAI_API_KEY`: Your OpenAI API key

## Understanding the Results

- Screenshots of search results are saved to the `screenshots` directory
- Extracted profile data is saved to `output/extracted_profiles.json`
- The JSON file contains an array of profile objects with the following structure:
  ```json
  {
    "name": "John Doe",
    "job_title": "Director of Operations",
    "company": "Example Company",
    "location": "Washington, DC",
    "education": "National Defense University",
    "connections": "500+",
    "searched_institution": "National Defense University",
    "page_found": 1
  }
  ```

## Benefits of the Screenshot Approach

- More resilient to LinkedIn UI changes than traditional scraping
- Leverages AI vision capabilities to extract structured data from visual content
- Avoids getting blocked by LinkedIn's anti-scraping measures
- Works with complex, dynamically loaded UI elements

## Analyzing the Data

After running the scraper, you can analyze the extracted data using the included `data_analyze.py` script:

```
python data_analyze.py
```

This will generate statistical insights and visualizations from the collected profiles.

## Troubleshooting

- If login fails, ensure your LinkedIn credentials are correct
- If OpenAI API calls fail, check your API key and model settings
- If screenshots aren't working, verify ChromeDriver is properly installed and compatible with your Chrome version 