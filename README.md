# Town Exchange — Backend Setup Guide

This is the backend API for Town Exchange. It handles property listings, stories, favorites, and image uploads.

Follow every step below in order on a new computer.

---

## Before you start — install these first

1. **Python 3.10+**  
   Download: https://www.python.org/downloads/  
   On Windows, during install, tick **"Add Python to PATH"**.

2. **Git**  
   Download: https://git-scm.com/

3. **Cloudinary account (free)**  
   Sign up: https://cloudinary.com  
   You will need 3 values from the Cloudinary dashboard later.

---

## Step 1: Get the project on your computer

Open a terminal and run:

```bash
git clone <your-backend-repo-url>
cd Town_X-BE
```

You are in the right folder if you can see these files:
- `main.py`
- `requirements.txt`
- `config.py`
- `.env.example`

---

## Step 2: Create a virtual environment

This keeps Python packages for this project separate from your system.

### On Windows (PowerShell)

Run these two commands one by one:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If you get a permission error when activating, run this once and try again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### On macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

**How to know it worked:** your terminal prompt should show `(venv)` at the start.

---

## Step 3: Install Python packages

While `(venv)` is active, run:

```bash
pip install -r requirements.txt
```

Wait until it finishes. Do not close the terminal.

---

## Step 4: Get Cloudinary keys

You need 3 values from Cloudinary for image and video uploads.

1. Go to https://console.cloudinary.com/ and log in
2. On the dashboard home page, find **Product Environment Credentials**
3. Copy and save these 3 values somewhere temporarily:
   - Cloud name
   - API Key
   - API Secret

You will paste them in the next step.

---

## Step 5: Create the `.env` file

The backend reads settings from a file called `.env` inside the `Town_X-BE` folder.

### 5.1 — Create the file

**Easiest way:** copy the example file.

On Windows:

```powershell
copy .env.example .env
```

On macOS / Linux:

```bash
cp .env.example .env
```

**Or create it yourself:**
1. Open the `Town_X-BE` folder in VS Code / Cursor
2. Right-click → New File
3. Name it exactly: `.env`  
   (Not `.env.txt` — just `.env`)

### 5.2 — Open `.env` and paste this

```env
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
DATABASE_URL=sqlite:///./properties.db
```

### 5.3 — Replace with your real Cloudinary values

Change the first 3 lines using the values from Step 4. Example:

```env
CLOUDINARY_CLOUD_NAME=dxyz123abc
CLOUDINARY_API_KEY=123456789012345
CLOUDINARY_API_SECRET=abcdefghijklmnopqrstuvwxyz
DATABASE_URL=sqlite:///./properties.db
```

**What each line means:**

- `CLOUDINARY_CLOUD_NAME` — your Cloudinary cloud name (**required**)
- `CLOUDINARY_API_KEY` — your Cloudinary API key (**required**)
- `CLOUDINARY_API_SECRET` — your Cloudinary API secret (**required**)
- `DATABASE_URL` — where data is stored (optional; SQLite is fine for local dev)

**Rules:**
- No quotes around values
- No spaces before or after `=`
- Do not share or commit this file (it is already ignored by Git)
- Without valid Cloudinary values, image uploads will not work

Save the file.

---

## Step 6: Create the database tables

Run:

```bash
python migrate_db.py
```

You should see:

```
Creating database tables...
✅ Tables created successfully!
```

A file called `properties.db` will be created in `Town_X-BE`.

> Note: Tables are also created automatically when you start the server. Running this step just makes sure everything is ready.

---

## Step 7: Start the backend server

Make sure `(venv)` is still active in your terminal.

Run:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8024
```

You should see a message like: `Starting Town Exchange API...`

**Keep this terminal open.** The server must stay running.

---

## Step 8: Check that everything works

Open your browser and visit these links:

1. http://localhost:8024  
   → Should show a JSON response with `"status": "running"`

2. http://localhost:8024/health  
   → Should show `"status": "healthy"` and `"database": "connected"`

3. http://localhost:8024/docs  
   → Should show the API documentation page (Swagger UI)

If all 3 work, your backend setup is complete.

---

## Next time you work on the backend

Every new terminal session:

```bash
cd Town_X-BE
.\venv\Scripts\Activate.ps1       # Windows
# source venv/bin/activate        # macOS / Linux
uvicorn main:app --reload --host 0.0.0.0 --port 8024
```

---

## If something goes wrong

**`ModuleNotFoundError: No module named 'fastapi'`**  
→ Virtual environment is not active. Activate it and run `pip install -r requirements.txt` again.

**Server won't start — Cloudinary error**  
→ Check that `.env` exists in `Town_X-BE` and all 3 Cloudinary values are correct with no extra spaces.

**Port 8024 already in use**  
→ Another app is using that port. Stop it, or start on a different port:  
`uvicorn main:app --reload --port 8001`

**Image upload fails**  
→ Cloudinary credentials in `.env` are wrong or missing.

**`database is locked`**  
→ You have more than one backend instance running. Stop all and start only one.

---

## Project folders

```
Town_X-BE/
├── main.py              ← API entry point
├── config.py            ← settings
├── database.py          ← database connection
├── models.py            ← database models
├── crud.py              ← database operations
├── migrate_db.py        ← create tables
├── requirements.txt     ← Python packages
├── .env                 ← you create this (not in Git)
├── .env.example         ← copy this to create .env
├── config/
│   └── landingPageConfig.json
└── utils/
    └── cloudinary_config.py
```

---

## API reference

Main endpoints:

- `GET /api/properties` — list properties
- `POST /api/properties` — create a property with images
- `GET /api/stories` — list stories
- `POST /api/stories` — upload a story
- `GET /api/favourites` — list saved properties
- `GET /api/landing-config` — landing page settings

Full docs: http://localhost:8024/docs

---

## Tech stack

FastAPI · SQLAlchemy · Pydantic · Cloudinary · APScheduler · Uvicorn
