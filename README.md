# Website-AI-Assistant

Run virtual environment: source venv/bin/activate

Install requirements: pip install -r requirements.txt

Test Wordpress Authentication: python scripts/test_wp_auth.py

Scrape Websites: python scripts/ingest_wordpress.py

Scrape the first 10 documents in a clean way: python scripts/preview_jsonl.py

Search specific pages by title: python scripts/search_jsonl.py title

Scraped markdown review file: python scripts/export_review_markdown.py