# itsfivepmsomewhere

Standalone "It's Five PM Somewhere" app extracted from `PaysonCarpenter.com`.

## Run locally

1. Create a virtual environment and install dependencies:
   - `pip install -r requirements.txt`
2. Start the app:
   - `python app.py`

The app runs on `http://localhost:5000/`.

## Deploy to Railway

- Create a new Railway project from this repo.
- Railway will use `Procfile` to launch gunicorn bound to `0.0.0.0:$PORT` with a single worker profile to avoid memory and boot crashes.
