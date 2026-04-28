# LareeshaLuxe Backend

Django REST API backend for the LareeshaLuxe e-commerce jewelry platform.

## Prerequisites

- Python 3.12+
- pip or conda
- PostgreSQL 14+ (local or remote)

## Installation

1. **Navigate to backend directory:**

   ```bash
   cd backend
   ```

2. **Create and activate virtual environment:**

   ```bash
   # Create virtual environment
   python -m venv venv

   # Activate it
   # On Linux/Mac:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Copy `.env` from the example and set `POSTGRES_*` values** (at minimum `POSTGRES_DB` and a user/password that can connect).

5. **Create the PostgreSQL database** (if it does not exist yet), for example:

   ```bash
   createdb lareesha
   ```

   Match the database name to `POSTGRES_DB` in `.env`.

## Database Setup

### Step 1: Create Migrations

```bash
python manage.py makemigrations
```

Generates migration files based on model definitions.

### Step 2: Apply Migrations

```bash
python manage.py migrate
```

Creates tables in the configured PostgreSQL database.

### Step 3: Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

Creates an admin account to access Django admin panel at `/admin/`.

### Step 4: Seed Database with Products

```bash
pip install requests
python manage.py seed_db
```

This command:

- Creates 8 jewelry products (Rings, Necklaces, Earrings, Bracelets)
- Downloads product images from Unsplash URLs
- Stores images locally in `media/products/`
- Initializes inventory stock levels

**Note:** The `requests` library is required for downloading images. Install it before running `seed_db`.

## Running the Development Server

```bash
python manage.py runserver
```

Server runs on: `http://localhost:8000/`

### Access Points:

- **API Base:** `http://localhost:8000/api/`
- **Admin Panel:** `http://localhost:8000/admin/`
- **JWT Auth:**
  - Login: `/api/auth/login/`
  - Register: `/api/auth/register/`
  - Logout: `/api/auth/logout/`

## Project Structure

```
backend/
├── api/
│   ├── management/commands/
│   │   ├── seed_db.py              # Seed database with products
│   │   └── cleanup_reservations.py # Clean expired stock reservations
│   ├── models.py                   # Database models
│   ├── views.py                    # API views
│   ├── serializers.py              # DRF serializers
│   └── admin.py                    # Django admin configuration
├── lareesha_backend/
│   ├── settings.py                 # Django settings
│   ├── urls.py                     # URL routing
│   └── wsgi.py                     # WSGI configuration
├── media/                          # User uploaded files & product images
├── manage.py                       # Django management script
└── requirements.txt                # Python dependencies
```

## Important Notes

- **Database:** PostgreSQL (see `POSTGRES_*` in `.env`)
- **Media Files:** Product images stored in `media/products/`
- **Authentication:** JWT tokens via `rest_framework_simplejwt`
- **CORS:** Enabled for `localhost:4200` and `127.0.0.1:4200` for Angular frontend

## One-Liner Setup

To set up everything at once:

```bash
cd backend && pip install -r requirements.txt && pip install requests && python manage.py makemigrations && python manage.py migrate && python manage.py seed_db
```

## Troubleshooting

**Error: Module not found**

- Ensure virtual environment is activated
- Run `pip install -r requirements.txt`

**Error: could not connect to server / connection refused (PostgreSQL)**

- Ensure PostgreSQL is running and `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env` are correct. Create the database if it does not exist, then run `python manage.py migrate` again.

**Error: Image download failed**

- Check internet connection
- Ensure `requests` library is installed
