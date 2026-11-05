# Website-AI-Assistant

Run virtual environment: source venv/bin/activate

Install requirements: pip install -r requirements.txt

Test Wordpress Authentication: python scripts/test_wp_auth.py

Scrape Websites: python scripts/01_ingest_wordpress.py

Scrape the first 10 documents in a clean way: python scripts/preview_jsonl.py

Search specific pages by title: python scripts/search_jsonl.py title

Scraped markdown review file: python scripts/export_review_markdown.py

## Deploy the backend automatically

The GitHub Actions workflow in `.github/workflows/deploy-backend.yml` builds and
tests backend changes pushed to `main`, pushes the image to ACR, and updates the
existing Azure Container App. It builds on GitHub's runner and does not use ACR
Tasks. Complete the one-time OIDC identity and GitHub secret setup in
[the deployment guide](docs/azure-github-actions.md) before pushing the workflow.

## Test the chat widget on WordPress

The embeddable widget is in `vl-rag-assistant/simple_frontend.html`. On a
hosted page it sends chat requests to
`https://vancouver-laser-api.yellowdesert-40ea49d6.westus2.azurecontainerapps.io/chat`.
Localhost pages continue to use the local backend at `http://127.0.0.1:8000`.

1. Create a separate WordPress test page, such as `/ai-assistant-test/`.
2. With Elementor, add an HTML widget and paste the entire contents of
   `vl-rag-assistant/simple_frontend.html` into it. With the block editor, use a
   Custom HTML block and an account allowed to save JavaScript.
3. Preview the page on the website and open the floating **Ask VL** button.
   Send a treatment question, then a follow-up to check conversation context.
4. Check the page on desktop and mobile. To share it with testers while
   restricting page access, use WordPress's built-in page visibility controls.

The backend allows `https://www.vancouverlaser.com` and
`https://vancouverlaser.com` by default. If `ALLOWED_ORIGINS` is configured in
Azure, it must include the test page's origin (scheme and domain, without its
path). For a staging site, add its exact origin to the comma-separated list.
Terminal requests do not verify browser CORS access.

The more detailed internal evaluation UI is in `al_assistant_test.html`; its
report submission requires a separate WordPress REST endpoint. The simple
widget does not require that endpoint. API keys stay in the backend and must
not be pasted into the page.
