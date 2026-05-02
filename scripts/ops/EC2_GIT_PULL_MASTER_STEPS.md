```bash
cd /srv/django-app

git fetch origin
git checkout master
git pull origin master

source venv/bin/activate
pip install -r requirements.txt
python scripts/ops/deploy_web.py
```

```bash
python scripts/ops/django_check.py
sudo systemctl status gunicorn
```

```bash
git status
```

```bash
git stash push -m "pre-pull EC2"
git pull origin master
git stash pop
```

```bash
git checkout -- .
git clean -fd
git pull origin master
```

```bash
python scripts/ops/django_migrate.py
python scripts/ops/django_collectstatic.py
python scripts/ops/restart_gunicorn.py
```

```bash
git pull origin main
```

```bash
pip install -r back-end/requirements.txt
```
