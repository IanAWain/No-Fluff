# No Fluff

A practical Flask project management app for delivery assessments and client handovers.

## Features

- Project dashboard with owner, client, due date and status
- Assessment workspace using four project types:
  - Paint by Numbers
  - Making Movies
  - Quest
  - Walking in Fog
- PDF report, PowerPoint handover deck and email generation
- One ZIP containing all generated client files
- Mobile-safe downloads for iPhone and iPad Safari
- Partial generation: PDF and PowerPoint failures do not block the other output or email
- SQLite storage with no external database required

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/flask_app.py
```

On Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\app\flask_app.py
```

Open `http://127.0.0.1:8000`.

## Test

```bash
python -m unittest discover -s app -p "test_*.py" -v
```

## Configuration

Copy `.env.example` values into your deployment environment. Set a strong `SECRET_KEY` in production.
