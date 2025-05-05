import json
import os
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
import seaborn as sns
import re

def load_profiles(json_path="output/extracted_profiles.json"):
    """Load profiles from JSON file"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
        print(f"Loaded {len(profiles)} profiles from {json_path}")
        return profiles
    except FileNotFoundError:
        print(f"Error: File {json_path} not found. Run the scraper first.")
        return []
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {json_path}")
        return []

def create_dataframe(profiles):
    """Convert profiles to pandas DataFrame"""
    df = pd.DataFrame(profiles)
    
    # Fill missing values
    df = df.fillna("")
    
    # Extract institution names to ensure consistent format
    df['searched_institution'] = df['searched_institution'].apply(lambda x: str(x).strip())
    
    return df

def print_basic_stats(df):
    """Print basic statistics about the profiles"""
    print("\n--- BASIC STATISTICS ---")
    print(f"Total profiles: {len(df)}")
    
    # Count by institution
    print("\nProfiles by institution:")
    institution_counts = df['searched_institution'].value_counts()
    for institution, count in institution_counts.items():
        print(f"  {institution}: {count}")

    # Count by page found
    print("\nProfiles by page number:")
    page_counts = df['page_found'].value_counts().sort_index()
    for page, count in page_counts.items():
        print(f"  Page {page}: {count}")

def analyze_job_titles(df):
    """Analyze job titles from profiles"""
    print("\n--- JOB TITLE ANALYSIS ---")
    
    # Extract job titles, ignoring empty values
    job_titles = [title for title in df['job_title'] if title and str(title).strip()]
    
    if not job_titles:
        print("No job title data available")
        return

    # Count the most common job titles
    title_counter = Counter(job_titles)
    print("\nTop 10 job titles:")
    for title, count in title_counter.most_common(10):
        print(f"  {title}: {count}")
    
    # Analyze job levels
    job_levels = analyze_job_levels(job_titles)
    print("\nJob levels distribution:")
    for level, count in job_levels.most_common():
        print(f"  {level}: {count}")
    
    # Plot job levels
    plt.figure(figsize=(10, 6))
    levels = [level for level, _ in job_levels.most_common()]
    counts = [count for _, count in job_levels.most_common()]
    
    plt.bar(levels, counts)
    plt.title('Job Level Distribution')
    plt.xlabel('Job Level')
    plt.ylabel('Count')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('job_levels.png')
    plt.close()
    print("\nJob level chart saved as 'job_levels.png'")

def analyze_job_levels(job_titles):
    """Categorize job titles into levels"""
    leadership_keywords = ['chief', 'ceo', 'cfo', 'cto', 'cio', 'president', 'founder']
    director_keywords = ['director', 'vp', 'vice president', 'head of']
    manager_keywords = ['manager', 'lead', 'senior', 'principal']
    associate_keywords = ['associate', 'specialist', 'analyst', 'consultant']
    
    job_levels = Counter()
    
    for title in job_titles:
        title_lower = title.lower()
        
        if any(keyword in title_lower for keyword in leadership_keywords):
            job_levels['C-Suite/Leadership'] += 1
        elif any(keyword in title_lower for keyword in director_keywords):
            job_levels['Director/VP'] += 1
        elif any(keyword in title_lower for keyword in manager_keywords):
            job_levels['Manager/Senior'] += 1
        elif any(keyword in title_lower for keyword in associate_keywords):
            job_levels['Associate/Specialist'] += 1
        else:
            job_levels['Other'] += 1
    
    return job_levels

def analyze_companies(df):
    """Analyze companies from profiles"""
    print("\n--- COMPANY ANALYSIS ---")
    
    # Extract companies, ignoring empty values
    companies = [company for company in df['company'] if company and str(company).strip()]
    
    if not companies:
        print("No company data available")
        return

    # Count the most common companies
    company_counter = Counter(companies)
    print("\nTop 10 companies:")
    for company, count in company_counter.most_common(10):
        print(f"  {company}: {count}")
    
    # Plot top companies
    plt.figure(figsize=(12, 6))
    top_companies = [company for company, _ in company_counter.most_common(15)]
    company_counts = [count for _, count in company_counter.most_common(15)]
    
    plt.barh(top_companies, company_counts)
    plt.title('Top 15 Companies')
    plt.xlabel('Count')
    plt.ylabel('Company')
    plt.tight_layout()
    plt.savefig('top_companies.png')
    plt.close()
    print("\nTop companies chart saved as 'top_companies.png'")

def analyze_locations(df):
    """Analyze locations from profiles"""
    print("\n--- LOCATION ANALYSIS ---")
    
    # Extract locations, ignoring empty values
    locations = [loc for loc in df['location'] if loc and str(loc).strip()]
    
    if not locations:
        print("No location data available")
        return

    # Extract regions (just take the first part of the location, typically the city or area)
    regions = []
    for loc in locations:
        parts = str(loc).split(',')
        if parts:
            regions.append(parts[0].strip())
    
    # Count the most common regions
    region_counter = Counter(regions)
    print("\nTop 10 regions:")
    for region, count in region_counter.most_common(10):
        print(f"  {region}: {count}")
    
    # Plot top regions
    plt.figure(figsize=(12, 6))
    top_regions = [region for region, _ in region_counter.most_common(10)]
    region_counts = [count for _, count in region_counter.most_common(10)]
    
    plt.barh(top_regions, region_counts)
    plt.title('Top 10 Regions')
    plt.xlabel('Count')
    plt.ylabel('Region')
    plt.tight_layout()
    plt.savefig('top_regions.png')
    plt.close()
    print("\nTop regions chart saved as 'top_regions.png'")

def analyze_education_to_job_correlation(df):
    """Analyze correlation between educational institution and job level/company"""
    print("\n--- EDUCATION TO JOB CORRELATION ---")
    
    # Only proceed if we have job titles and institutions
    if 'job_title' not in df.columns or 'searched_institution' not in df.columns:
        print("Missing job title or institution data")
        return
    
    # Remove rows without job titles
    df_filtered = df[df['job_title'].notna() & (df['job_title'] != "")]
    
    if len(df_filtered) == 0:
        print("No valid job title data available")
        return
    
    # Categorize job titles into levels
    df_filtered['job_level'] = df_filtered['job_title'].apply(categorize_job_level)
    
    # Create a crosstab of institution vs. job level
    crosstab = pd.crosstab(df_filtered['searched_institution'], df_filtered['job_level'])
    
    # Plot the crosstab as a heatmap
    plt.figure(figsize=(12, 8))
    sns.heatmap(crosstab, annot=True, cmap="YlGnBu", fmt='d')
    plt.title('Institution vs Job Level')
    plt.tight_layout()
    plt.savefig('institution_job_correlation.png')
    plt.close()
    print("\nInstitution to job correlation heatmap saved as 'institution_job_correlation.png'")

def categorize_job_level(job_title):
    """Categorize a job title into a job level"""
    job_title = str(job_title).lower()
    
    if any(keyword in job_title for keyword in ['chief', 'ceo', 'cfo', 'cto', 'cio', 'president', 'founder']):
        return 'C-Suite/Leadership'
    elif any(keyword in job_title for keyword in ['director', 'vp', 'vice president', 'head of']):
        return 'Director/VP'
    elif any(keyword in job_title for keyword in ['manager', 'lead', 'senior', 'principal']):
        return 'Manager/Senior'
    elif any(keyword in job_title for keyword in ['associate', 'specialist', 'analyst', 'consultant']):
        return 'Associate/Specialist'
    else:
        return 'Other'

def export_to_csv(df, output_path="alumni_analysis.csv"):
    """Export the data to CSV for further analysis"""
    try:
        df.to_csv(output_path, index=False)
        print(f"\nData exported to {output_path}")
    except Exception as e:
        print(f"Error exporting to CSV: {e}")

def main():
    # Create output directory for charts if it doesn't exist
    os.makedirs('analysis_output', exist_ok=True)
    
    # Load profiles
    profiles = load_profiles()
    if not profiles:
        return
    
    # Convert to DataFrame
    df = create_dataframe(profiles)
    
    # Print basic statistics
    print_basic_stats(df)
    
    # Analyze job titles
    analyze_job_titles(df)
    
    # Analyze companies
    analyze_companies(df)
    
    # Analyze locations
    analyze_locations(df)
    
    # Analyze education to job correlation
    analyze_education_to_job_correlation(df)
    
    # Export data to CSV
    export_to_csv(df)
    
    print("\nAnalysis complete!")

if __name__ == "__main__":
    main() 