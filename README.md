# BankBook AI OS — Brain (Backend)

South Africa's AI Financial Operating System. Runs on WhatsApp via Evolution API.

## Features

- **Bond Affordability Calculator** — SA Prime Rate (11.75%), 20-year term, 30% income rule
- **User Profile Management** — Salary, debt, and financial snapshot per WhatsApp number
- **Property Vault** — Track properties, bond balances, and home equity
- **Insurance Tracker** — Log policies, premiums, and get savings estimates

## Stack

- **Language:** Python 3.11
- **Framework:** FastAPI
- **Database:** PostgreSQL (Neon recommended)
- **ORM:** SQLModel (SQLAlchemy + Pydantic)
- **Server:** Gunicorn + Uvicorn workers

## Local Setup

```bash
cp .env.example .env
# Add your Neon DATABASE_URL to .env

pip install -r requirements.txt
uvicorn main:app --reload
```

API docs available at `http://localhost:8000/docs`

## Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Add `DATABASE_URL` as an environment variable (your Neon connection string)
5. Deploy

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| POST | `/profile` | Create or update user profile |
| GET | `/profile/{whatsapp_id}` | Get user profile |
| POST | `/calculate-affordability` | Bond affordability calculation |
| POST | `/property` | Add a property |
| GET | `/properties/{whatsapp_id}` | List user's properties |
| POST | `/insurance` | Add an insurance policy |
| GET | `/insurance/{whatsapp_id}` | List user's insurance policies |

## Windmill / Automation Integration

Point your Windmill webhook flow at:
- `POST /profile` — when user shares salary
- `POST /calculate-affordability` — when user asks "can I afford this house?"

See `/docs` for full request/response schemas.
