# code-daily: 14-Day Development Plan

A gamified coding habit tracker that connects to GitHub (and eventually other platforms), tracks commit streaks, and provides motivation through streaks, XP, achievements, and reminders.

## Why Build This

- **Meta-motivating**: Building it reinforces your daily commit habit
- **Clear MVP**: GitHub API is well-documented
- **Quick wins**: Can have something working in days, then iterate
- **Portfolio-worthy**: Demonstrates API integration, gamification UX
- **Platform-agnostic**: Can expand to GitLab, Bitbucket later

## Minimal Viable Product (MVP)

1. Connect to GitHub API
2. Fetch user's commit history
3. Calculate current streak
4. Display streak with simple UI
5. Show basic stats (commits today, this week, this month)

## Tech Stack

- **Language:** Python
- **Web Framework:** FastAPI (lightweight, modern)
- **Database:** SQLite (simple, no setup)
- **Frontend:** HTMX + Tailwind (minimal JS, fast iteration)
- **Deployment:** Railway or Render (free tier)

## Day-by-Day Breakdown (First 2 Weeks)

| Day | Task | Commit Message |
|-----|------|----------------|
| 1 | Create repo, README, project structure | `init: project setup and README` |
| 2 | GitHub OAuth setup / personal access token config | `feat: add GitHub authentication config` |
| 3 | Basic API client to fetch user events | `feat: GitHub API client for user events` |
| 4 | Parse commit events from API response | `feat: parse commit events from user activity` |
| 5 | Calculate streak logic (consecutive days) | `feat: streak calculation algorithm` |
| 6 | Simple CLI output showing streak | `feat: CLI display of current streak` |
| 7 | Add weekly/monthly commit counts | `feat: add weekly and monthly stats` |
| 8 | Create basic Flask/FastAPI web endpoint | `feat: web API endpoint for stats` |
| 9 | Simple HTML page to display streak | `feat: basic web UI for streak display` |
| 10 | Add streak "fire" visualization | `feat: streak visualization with icons` |
| 11 | Store historical data (SQLite) | `feat: SQLite storage for history` |
| 12 | Show streak history graph | `feat: streak history visualization` |
| 13 | Add daily goal/target setting | `feat: configurable daily commit goal` |
| 14 | Basic achievements system | `feat: achievement badges for milestones` |

## Future Iterations (After MVP)

- Browser extension for GitHub profile
- Push notifications / reminders
- Leaderboard with friends
- Integration with other platforms (GitLab, Bitbucket)
- Mobile-friendly PWA
- XP system with levels

## Project Structure

```
code-daily/
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── github_client.py
│   ├── streak_calculator.py
│   └── main.py
├── tests/
│   └── __init__.py
└── .gitignore
```

## Verification Milestones

- **After Day 7:** CLI should display your actual GitHub streak
- **After Day 14:** Web UI should show streak with visualization
