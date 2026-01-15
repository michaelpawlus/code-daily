# code-daily

A gamified coding habit tracker that connects to GitHub, tracks commit streaks, and provides motivation through streaks, XP, achievements, and reminders.

## Features (Planned)

- 🔥 Track daily commit streaks
- 📊 View weekly/monthly commit statistics
- 🏆 Earn achievements for milestones
- ⚡ Simple CLI and web interface

## Tech Stack

- Python 3.10+
- FastAPI (web framework)
- SQLite (local storage)
- HTMX + Tailwind (frontend)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/code-daily.git
cd code-daily

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env example and add your GitHub token
cp .env.example .env

# Run the app
python src/main.py
```

## Configuration

Create a `.env` file with:

```
GITHUB_TOKEN=your_personal_access_token
GITHUB_USERNAME=your_username
```

## Development Status

🚧 Under active development - building MVP

## License

MIT
