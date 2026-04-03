<div align="center">

<br/>

```
███████╗██████╗ ██╗   ██╗███╗   ███╗███████╗████████╗██████╗ ██╗ ██████╗███████╗
██╔════╝██╔══██╗██║   ██║████╗ ████║██╔════╝╚══██╔══╝██╔══██╗██║██╔════╝██╔════╝
█████╗  ██║  ██║██║   ██║██╔████╔██║█████╗     ██║   ██████╔╝██║██║     ███████╗
██╔══╝  ██║  ██║██║   ██║██║╚██╔╝██║██╔══╝     ██║   ██╔══██╗██║██║     ╚════██║
███████╗██████╔╝╚██████╔╝██║ ╚═╝ ██║███████╗   ██║   ██║  ██║██║╚██████╗███████║
╚══════╝╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝╚══════╝
```

**AI-powered academic analytics platform for college advisors.**  
Know who needs attention. Act early. Spread help smartly.

<br/>

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.x-092E20?style=flat-square&logo=django&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.x-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)
![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=flat-square)

<br/>

</div>

---

## What Is EduMetrics?

EduMetrics is an academic advisory intelligence platform built for college advisors. It reads data from a college's existing systems — attendance, assignments, quizzes, library usage — and surfaces **who needs attention this week**, complete with plain-English explanations of why.

The platform is designed around a core belief: **advisors have limited time and many students.** EduMetrics makes sure that time is spent on the students who need it most, with the right context to act effectively.

```
College Database (read-only)          EduMetrics Analytics Engine
┌─────────────────────────┐           ┌────────────────────────────────┐
│  Attendance records     │  ──────▶  │  Layer 1: Raw signal extraction │
│  Assignment submissions │           │  Layer 2: Score computation      │
│  Quiz attempts          │           │  Layer 3: Flagging + alerts      │
│  Library visit logs     │           │  Layer 4: ML prediction (Stage 2)│
└─────────────────────────┘           └──────────────┬─────────────────┘
                                                      │
                                                      ▼
                                       Advisor Portal (React + Tailwind)
                                       ┌──────────────────────────────┐
                                       │  Daily flagged student list   │
                                       │  Student deep-dive analytics  │
                                       │  Intervention logging         │
                                       │  Pre/post exam analysis       │
                                       │  HOD & parent reports         │
                                       └──────────────────────────────┘
```

---

## The Problem We're Solving

Most colleges track student data. Very few use it proactively. An advisor managing 60+ students has no practical way to know that **Arjun's attendance dropped 18% over the last 3 weeks**, or that **Meera hasn't submitted an assignment in 12 days**, until it shows up as a fail on a result sheet — by which point intervention is too late.

EduMetrics closes that gap. Every Sunday, the system recalculates metrics for every student. Every Monday, the advisor opens a dashboard that tells them exactly who to reach out to, why, and with what context.

---

## Key Features

### Stage 1 — Rule-Based Flagging Engine *(current)*
- **Weekly risk scoring** across 4 signal sources: attendance, assignments, quizzes, library
- **Three-layer framework**: raw signals → computed scores → risk labels (Critical / Watch / Monitor / Safe)
- **Plain-English flag reasons** — not just a number, but *why* the student was flagged
- **Exculpatory context** — high assignment load reduces latency penalty automatically
- **Pre-midterm analysis** — predicted exam scores generated 2 weeks before exams
- **Post-midterm analysis** — actual vs predicted gap, underperformers flagged immediately
- **Pre / post end-term analysis** — pass/fail risk, semester narrative generation
- **Automatic scheduling** — weekly and exam-window analyses run on cron, zero manual triggers

### Stage 2 — ML Layer *(upcoming)*
- Learned risk weights replacing fixed formula weights (Logistic Regression, Random Forest, XGBoost)
- Archetype classifier — by Week 3, predict which behavioral archetype a student is trending toward
- Backlog subject predictor — predict failure at subject level, not just overall
- Recovery probability model — post-midterm prediction of end-term recovery likelihood
- Intervention effectiveness model — learn which advisor actions work for which student profiles

### Stage 3 — Advisor Portal *(upcoming)*
- **Student Galaxy view** — scatter plot where every student is a point, colored by risk
- **Intervention logger** — pick from saved list, voice type, or free text
- **Gmail integration** — one-click email to student or parent with AI-generated starter template
- **HOD report generator** — Claude API generates formal class summary on demand
- **Semester report** — full narrative of a student's semester arc, downloadable

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EduMetrics System                         │
│                                                                   │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │   React +    │    │  Django / Flask   │    │  PostgreSQL   │  │
│  │  Tailwind    │◀──▶│   REST API        │◀──▶│  (Supabase)   │  │
│  │  Frontend    │    │                  │    │               │  │
│  └──────────────┘    └────────┬─────────┘    └───────────────┘  │
│                               │                                   │
│                    ┌──────────▼──────────┐                       │
│                    │   Analytics Engine   │                       │
│                    │   (Python)           │                       │
│                    │                      │                       │
│                    │  engine/features.py  │                       │
│                    │  engine/scores.py    │                       │
│                    │  engine/risk.py      │                       │
│                    │  engine/flags.py     │                       │
│                    │  engine/scheduler.py │                       │
│                    └──────────┬──────────┘                       │
│                               │                                   │
│            ┌──────────────────┼──────────────────┐               │
│            ▼                  ▼                   ▼               │
│     ┌────────────┐   ┌──────────────┐   ┌──────────────────┐    │
│     │  ML Models │   │  Cron Jobs   │   │   Claude API     │    │
│     │ (sklearn / │   │ (Render /    │   │ (report & email  │    │
│     │  XGBoost)  │   │  GitHub Act.)│   │  generation)     │    │
│     └────────────┘   └──────────────┘   └──────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Risk Flagging Framework

EduMetrics computes a 0–100 **Overall Risk Score** from three component scores:

```
Overall Risk Score  =  0.45 × Disengagement Score
                    +  0.40 × Academic Risk Score
                    +  0.15 × Behavioral Consistency Score
```

### Disengagement Score
```
0.35 × attendance gap from threshold
0.25 × submission rate gap
0.20 × quiz attempt gap
0.12 × submission latency penalty  (reduced when active load is high)
0.08 × library engagement gap
```

### Academic Risk Score
```
0.50 × assignment quality gap
0.25 × attendance trend penalty (slope over 3 weeks)
0.15 × quiz score gap
0.10 × plagiarism flag
```

### Behavioral Consistency Score
```
Standard deviation of weekly attendance over last 4 weeks
+ Standard deviation of weekly submission rate over last 4 weeks
(normalised 0–100)
```

### Risk Labels

| Score | Label | Action |
|-------|-------|--------|
| 70 – 100 | 🔴 Critical | Advisor must act this week |
| 45 – 69 | 🟠 Watch | Monitor closely, prepare intervention |
| 25 – 44 | 🟡 Monitor | On the radar, review next week |
| 0 – 24 | 🟢 Safe | No action needed |

> **Note on weights:** These are the Stage 1 manually tuned values. In Stage 2, ML models will learn these weights from actual semester outcome data, replacing guesses with evidence.

---

## Semester Analysis Windows

EduMetrics runs five types of analysis, all triggered automatically:

| Window | When | What Runs |
|--------|------|-----------|
| **Weekly Pulse** | Every Sunday | All metrics recalculated, snapshots written, alert queue updated |
| **Pre-Midterm** | Week 6 | Predicted exam scores generated, at-risk students prioritised |
| **Post-Midterm** | Week 9 | Actual vs predicted gap, underperformer flags, baseline reset |
| **Pre-End Term** | Week 14 | Pass/fail risk per subject, intervention recommendations |
| **Post-End Term** | Week 17 | Semester outcomes, year-on-year comparison, narrative generation |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | React 18 + Vite | Component-based, fast, great ecosystem for dashboards |
| Styling | Tailwind CSS | Utility-first, consistent design tokens, no CSS files |
| Backend | Django 4 or Flask | Python-native so ML and API live in same codebase |
| Database | PostgreSQL (Supabase) | Relational — student data is deeply relational; Supabase is always-on free tier |
| ML | scikit-learn, XGBoost, Prophet | Industry standard tabular ML; Prophet for time-series GPA forecasting |
| HTTP client | Axios | API calls from frontend |
| Auth | JWT (djangorestframework-simplejwt) | Role-based access: advisor / HOD / admin |
| Scheduling | Render Cron Jobs | Serverless cron — no always-on server needed for background jobs |
| AI layer | Anthropic Claude API | Report generation, email templates, flag explanations |
| Deployment | Render (backend) + Vercel (frontend) | Free tiers sufficient for college-scale deployment |

---

## Project Structure

```
EduMetrics/
│
├── backend/                        # Django or Flask API
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py             # Login, JWT, role management
│   │   │   ├── students.py         # Caseload, student detail endpoints
│   │   │   ├── analytics.py        # Dashboard, alerts, trends
│   │   │   ├── insights.py         # Claude API — briefings, reports
│   │   │   └── recalculate.py      # Cron-triggered analysis endpoint
│   │   ├── engine/
│   │   │   ├── features.py         # Layer 1 → Layer 2 feature extraction
│   │   │   ├── scores.py           # Disengagement, Academic Risk, Behavioral scores
│   │   │   ├── risk.py             # Overall risk score + label
│   │   │   ├── flags.py            # Plain-English flag reason generator
│   │   │   ├── snapshots.py        # Write computed results to analytics DB
│   │   │   └── scheduler.py        # Maps analysis windows to trigger weeks
│   │   ├── jobs/
│   │   │   ├── weekly_pulse.py     # Runs every Sunday
│   │   │   ├── pre_midterm.py      # Week 6
│   │   │   ├── post_midterm.py     # Week 9
│   │   │   ├── pre_endterm.py      # Week 14
│   │   │   └── post_endterm.py     # Week 17
│   │   ├── ml/
│   │   │   ├── train.py            # Model training pipeline (Stage 2)
│   │   │   ├── predict.py          # Inference on new student data
│   │   │   └── models/             # Saved .pkl model files
│   │   ├── simulator/
│   │   │   ├── advance_week.py     # Advances DB state by one week
│   │   │   ├── run_exam.py         # Generates midterm/endterm marks
│   │   │   └── state.py            # Tracks current sim week per section
│   │   └── services/
│   │       └── claude.py           # Anthropic API wrapper
│   ├── generate_dataset.py         # Synthetic data generation script
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                       # React + Tailwind
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx       # Daily flags + summary stats
│   │   │   ├── StudentDetail.jsx   # Deep-dive metrics + AI insights
│   │   │   ├── WeeklyAnalysis.jsx  # What changed this week
│   │   │   ├── AlertQueue.jsx      # Ranked at-risk list
│   │   │   ├── Interventions.jsx   # Log + manage interventions
│   │   │   ├── Schedule.jsx        # 18-week timeline
│   │   │   └── Galaxy.jsx          # Student scatter plot (Stage 3)
│   │   ├── components/
│   │   │   ├── StudentCard.jsx
│   │   │   ├── RiskBadge.jsx
│   │   │   ├── MetricBar.jsx
│   │   │   ├── Sparkline.jsx
│   │   │   ├── AIInsightPanel.jsx
│   │   │   └── InterventionLogger.jsx
│   │   ├── api/
│   │   │   └── client.js           # Axios instance with JWT interceptor
│   │   └── store/
│   │       └── auth.js             # Zustand auth store
│   ├── tailwind.config.js
│   └── .env.example
│
├── database/
│   ├── schema.sql                  # All CREATE TABLE statements
│   └── migrations/
│
└── README.md
```

---

## Database Schema

### Dummy College DB *(read-only — EduMetrics never writes here)*

```sql
students          student_id, batch_id, name, roll_number, gender, email,
                  parent_email, year, branch, semester

attendance        student_id, batch_id, semester, week, week_start_date,
                  subject, lectures_held, present, absent, late, attendance_pct

assignments       student_id, batch_id, semester, assignment_id, subject,
                  due_week, due_date, active_load, status, submission_date,
                  latency_hours, marks_obtained, max_marks, quality_pct, plagiarism_pct

quizzes           student_id, batch_id, semester, quiz_id, subject, week,
                  quiz_date, attempted, marks_obtained, max_marks, score_pct

library_visits    student_id, batch_id, semester, week, week_start_date,
                  physical_visits

book_borrows      borrow_id, student_id, batch_id, semester, book_title,
                  borrow_date, return_date, borrow_week, return_week

exams             student_id, batch_id, semester, subject, exam_type,
                  exam_week, exam_date, marks_obtained, max_marks, score_pct
```

### Analytics DB *(EduMetrics writes here)*

```sql
snapshots         student_id, semester, week, disengagement_score,
                  academic_risk_score, behavioral_score, overall_risk_score,
                  risk_label, flag_reasons (JSON), computed_at

alerts            student_id, advisor_id, alert_type, message, is_read, created_at

interventions     intervention_id, student_id, advisor_id, week,
                  intervention_type, notes, timestamp

advisor_notes     note_id, student_id, advisor_id, note_text, created_at
```

---

## Getting Started

### Prerequisites

```
Python 3.11+
Node.js 20+
Git
PostgreSQL (or a free Supabase account)
```

### 1. Clone the repository

```bash
git clone https://github.com/your-username/EduMetrics.git
cd EduMetrics
```

### 2. Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env — fill in DATABASE_URL, SECRET_KEY, ANTHROPIC_API_KEY, CRON_SECRET
```

### 3. Generate the synthetic dataset

```bash
# Generates all CSV files + academic_dataset.xlsx
python generate_dataset.py

# Then load into your database:
# Option A — Supabase: Table Editor → Import CSV for each file
# Option B — psql: \copy table_name FROM 'file.csv' CSV HEADER
```

### 4. Run the backend

```bash
# Django
python manage.py migrate
python manage.py runserver

# Flask
flask run --port 8000
```

### 5. Frontend setup

```bash
cd ../frontend

npm install
cp .env.example .env
# Set VITE_API_BASE_URL=http://localhost:8000

npm run dev
# Runs at http://localhost:5173
```

### 6. Trigger your first weekly analysis

```bash
# Run the weekly pipeline manually
python -m app.jobs.weekly_pulse

# Or advance the simulator by one week
python -m app.simulator.advance_week --section "BTech CS Year 1" --week 3
```

---

## Environment Variables

### Backend `.env`

```env
DATABASE_URL=postgresql://user:password@host:5432/edumetrics
SECRET_KEY=your-long-random-secret-key-here
ANTHROPIC_API_KEY=sk-ant-api03-...
CRON_SECRET=random-string-used-to-authenticate-cron-calls
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Frontend `.env`

```env
VITE_API_BASE_URL=http://localhost:8000
```

Generate `SECRET_KEY` and `CRON_SECRET` with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Running the Semester Simulator

EduMetrics ships with a simulator that advances the database state week by week, letting you demo a full semester without waiting for one.

```bash
# Advance a specific section by one week
python -m app.simulator.advance_week --section "BTech CS Year 1" --week 4

# Run midterm exams for a section
python -m app.simulator.run_exam --section "BTech CS Year 2" --type midterm

# Run a full 18-week semester automatically
python -m app.simulator.run_full_semester --section "BTech CS Year 1"
```

After each advance, the weekly pipeline recalculates and the advisor dashboard reflects the updated state.

---

## Deployment

### Backend → Render (free tier)

1. New Web Service → connect GitHub repo
2. Root directory: `backend`
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app.wsgi:application` (Django) or `gunicorn app:app` (Flask)
5. Add all environment variables

### Cron Jobs → Render Cron Jobs (free tier)

| Job | Cron Schedule | Command |
|-----|--------------|---------|
| Weekly Pulse | `0 6 * * 1` | `python -m app.jobs.weekly_pulse` |
| Pre-Midterm | Set to your Week 6 date | `python -m app.jobs.pre_midterm` |
| Post-Midterm | Set to your Week 9 date | `python -m app.jobs.post_midterm` |
| Pre-End Term | Set to your Week 14 date | `python -m app.jobs.pre_endterm` |
| Post-End Term | Set to your Week 17 date | `python -m app.jobs.post_endterm` |

### Frontend → Vercel (free tier)

1. New Project → import GitHub repo
2. Framework preset: Vite
3. Root directory: `frontend`
4. Environment variable: `VITE_API_BASE_URL=https://your-app.onrender.com`
5. Deploy

---

## Roadmap

- [x] Synthetic dataset generator — 3 batches × 8 semesters × all signal types
- [x] Layer 1–3 flagging framework designed and documented
- [x] Project task checklist (all 3 stages)
- [ ] **Stage 1** — Analytics engine: feature extraction, score computation, flag generation
- [ ] **Stage 1** — Semester simulator: advance_week, run_exam scripts
- [ ] **Stage 1** — Pre/post midterm and end-term analysis pipelines
- [ ] **Stage 1** — REST API layer (Django/Flask)
- [ ] **Stage 1** — Core advisor portal: daily flags, student detail, weekly analysis
- [ ] **Stage 2** — ML risk classifier: Logistic Regression → Random Forest → XGBoost
- [ ] **Stage 2** — Backlog subject predictor per student
- [ ] **Stage 2** — Archetype classifier (Week 3 early prediction)
- [ ] **Stage 2** — Intervention effectiveness model
- [ ] **Stage 3** — Student Galaxy scatter view
- [ ] **Stage 3** — Intervention logger with voice input
- [ ] **Stage 3** — Gmail integration + parent report mailer
- [ ] **Stage 3** — WOW feature *(TBD — team ideation session)*

---

## Student Archetypes

EduMetrics synthetic data includes 7 behaviorally distinct archetypes. Each follows a specific trajectory, giving the flagging engine meaningful patterns to detect and later for ML to learn from.

| Archetype | Behavior Pattern | Expected Outcome |
|-----------|-----------------|-----------------|
| **High Performer** | Consistently high across all signals | Distinction |
| **Consistent Avg** | Stable mid-range, no dramatic swings | Pass |
| **Late Bloomer** | Poor start, strong recovery after Week 10 | Pass |
| **Slow Fader** | Good start, gradual week-on-week decline | Backlog |
| **Crammer** | Low steady-state, spikes before exams only | Borderline |
| **Crisis Student** | Fine until Week 9, then sharp drop across all signals | Fail |
| **Silent Disengager** | Okay attendance and grades, zero quiz/library engagement | Fail |

> The **Late Bloomer** and **Silent Disengager** are the hardest to catch with fixed rules and are the primary motivation for the ML layer in Stage 2.

---

## Contributing

This project is in active development.

1. Branch off `main` → `feature/your-feature-name`
2. Keep commits small and descriptive
3. Before opening a PR, verify the analytics engine runs clean: `python -m app.jobs.weekly_pulse`
4. Document any new environment variables in `.env.example`

---

## License

MIT — use freely, attribution appreciated.

---

<div align="center">

**EduMetrics** — built because students deserve advisors who know their story before it's too late.

</div>
