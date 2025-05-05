# LinkedIn Alumni Scraper with OpenAI Vision

This tool scrapes LinkedIn for alumni from specific educational institutions using a screenshot-based approach with OpenAI's Vision API to extract profile information.

## Features

- Automatically logs into LinkedIn
- Searches for alumni from specified educational institutions
- Takes screenshots of search results
- Uses OpenAI Vision API to extract profile information from screenshots
- Saves extracted data to JSON

## Prerequisites

- Python 3.8+
- Chrome browser
- ChromeDriver compatible with your Chrome version
- OpenAI API key with access to GPT-4 Vision

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up ChromeDriver:
   - Download ChromeDriver from [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads)
   - Make sure the version matches your Chrome browser
   - Place it in the location specified in `scrape_profile.py` (default: `C:\WebDriver\bin\chromedriver.exe`)

## Usage

1. Run the script:
   ```
   python scrape_profile.py
   ```

2. When prompted, enter:
   - Your LinkedIn email and password
   - Your OpenAI API key

3. The script will:
   - Login to LinkedIn
   - Search for alumni from the specified institutions
   - Take screenshots of search results
   - Send screenshots to OpenAI Vision API for analysis
   - Save extracted profiles to `output/extracted_profiles.json`

## Configuration

You can modify the list of target institutions in `scrape_profile.py`:

```python
institutions = [
    "National Defense University",
    "Industrial College of the Armed Forces",
    "Eisenhower School for National Security and Resource Strategy",
    "Information Resources Management College",
    "Joint Forces Staff College"
]
```

## Environment Variables

You can set these environment variables to avoid entering them each time:
- `LINKEDIN_EMAIL`: Your LinkedIn email
- `LINKEDIN_PASSWORD`: Your LinkedIn password
- `OPENAI_API_KEY`: Your OpenAI API key

## Troubleshooting

- If login fails, ensure your LinkedIn credentials are correct
- If the script has trouble finding elements, LinkedIn may have updated their UI - check the selectors
- If OpenAI API calls fail, check your API key and ensure you have access to GPT-4 Vision

## Notes

- Screenshots are saved to the `screenshots` directory
- Extracted profile data is saved to `output/extracted_profiles.json`
- This approach is more resilient to LinkedIn UI changes than traditional scraping 