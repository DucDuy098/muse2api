# Deploy Muse2API Studio lên VPS (2 vCPU / 4GB)

## 1. Cài gói hệ thống
```bash
sudo apt update
sudo apt install -y python3.11-venv postgresql nginx certbot python3-certbot-nginx chromium
```

## 2. Clone repo + venv backend
```bash
sudo mkdir -p /opt/muse2api && sudo chown $USER /opt/muse2api
git clone <repo> /opt/muse2api && cd /opt/muse2api
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # KHÔNG cài requirements-gui.txt trên VPS
cp .env.example .env   # rồi điền MUSE2API_DB_URL, MUSE2API_PUBLIC_BASE, proxy nếu cần
```

## 3. Postgres local
```bash
sudo -u postgres psql -c "CREATE USER muse2api WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE muse2api OWNER muse2api;"
# .env: MUSE2API_DB_URL=postgresql://muse2api:...@localhost/muse2api
```
Migration tự chạy lúc service khởi động (`db.py` `run_migrations`).

## 4. Seed user owner đầu tiên
```bash
./.venv/bin/python scripts/create_owner.py
```

## 5. Build frontend (static export)
```bash
cd frontend
npm ci
echo "NEXT_PUBLIC_API_BASE=" > .env.local   # rỗng = same-origin qua Nginx
npm run build   # sinh ra frontend/out/
```

## 6. systemd + Nginx
```bash
sudo cp deploy/muse2api.service /etc/systemd/system/
sudo useradd -r -s /bin/false muse2api 2>/dev/null || true
sudo chown -R muse2api:muse2api /opt/muse2api
sudo systemctl daemon-reload
sudo systemctl enable --now muse2api

sudo cp deploy/nginx.conf /etc/nginx/sites-available/muse2api
sudo ln -s /etc/nginx/sites-available/muse2api /etc/nginx/sites-enabled/
# sửa server_name trong nginx.conf thành domain thật trước
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d app.yourdomain.com
```

## Kiểm tra
- `curl https://app.yourdomain.com/healthz` → `{"status":"ok",...}`
- Mở `https://app.yourdomain.com/login`, đăng nhập bằng user vừa seed
- `systemctl status muse2api` — service chạy, Chromium khởi động theo yêu cầu đầu tiên

## Cập nhật sau này
```bash
cd /opt/muse2api && git pull
./.venv/bin/pip install -r requirements.txt
cd frontend && npm ci && npm run build
sudo systemctl restart muse2api
```
