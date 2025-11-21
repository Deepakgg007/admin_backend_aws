# AWS EC2 Deployment Guide

## Overview
This document outlines the complete deployment process for the Z1 Backend application on AWS EC2 with Docker, MySQL, and Nginx.

## Prerequisites
- AWS EC2 instance (Ubuntu 22.04 LTS recommended)
- Domain name (e.g., krishik-abiuasd.in)
- Domain DNS configured to point to EC2 instance IP

## Step 1: Initial Setup

### 1.1 Update System
```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 1.2 Install Docker
```bash
sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ubuntu
```

### 1.3 Install Docker Compose
```bash
sudo apt-get install -y docker-compose
```

### 1.4 Install MySQL
```bash
sudo apt-get install -y mysql-server
sudo systemctl start mysql
sudo systemctl enable mysql
```

## Step 2: MySQL Configuration

### 2.1 Configure MySQL to Listen on All Interfaces
```bash
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
```

Find and change:
```
bind-address = 127.0.0.1
```

To:
```
bind-address = 0.0.0.0
```

Then restart MySQL:
```bash
sudo systemctl restart mysql
```

### 2.2 Create Database and User
```bash
sudo mysql -u root

# Inside MySQL:
CREATE DATABASE mydb;
CREATE USER 'django'@'%' IDENTIFIED BY 'Haegl@7890';
GRANT ALL PRIVILEGES ON mydb.* TO 'django'@'%';
FLUSH PRIVILEGES;
EXIT;
```

## Step 3: Clone and Setup Application

### 3.1 Clone Repository
```bash
cd /home/ubuntu
git clone https://github.com/Deepakgg007/admin_backend_aws.git
cd admin_backend_aws
```

### 3.2 Create .env File
```bash
nano .env
```

Add the following content:
```
DEBUG=False
ALLOWED_HOSTS=localhost, 127.0.0.1, 0.0.0.0, <YOUR_EC2_IP>, <YOUR_DOMAIN>, www.<YOUR_DOMAIN>

# MySQL Database Configuration
DB_NAME=mydb
DB_USER=django
DB_PASSWORD=Haegl@7890
DB_HOST=<YOUR_EC2_IP>
DB_PORT=3306

# JWT Configuration
JWT_SECRET_KEY=<YOUR_SECURE_KEY>
JWT_ACCESS_TOKEN_LIFETIME=1440
JWT_REFRESH_TOKEN_LIFETIME=1440

# Email Configuration
EMAIL_HOST_USER=<YOUR_EMAIL>
EMAIL_HOST_PASSWORD=<YOUR_EMAIL_PASSWORD>

# Security Settings
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

## Step 4: Docker Setup

### 4.1 Build and Run Docker
```bash
sudo docker-compose up -d --build
```

### 4.2 Create Superuser
```bash
sudo docker-compose exec web python manage.py createsuperuser
```

Follow the prompts to create an admin user.

## Step 5: Nginx Setup

### 5.1 Install Nginx
```bash
sudo apt-get install -y nginx
```

### 5.2 Create Nginx Config
```bash
sudo nano /etc/nginx/sites-available/z1-backend
```

Add the following configuration:
```nginx
# HTTP Server
server {
    server_name <YOUR_DOMAIN> www.<YOUR_DOMAIN> <YOUR_EC2_IP>;

    # Max upload size
    client_max_body_size 100M;

    # Logs
    access_log /var/log/nginx/z1_backend_access.log;
    error_log /var/log/nginx/z1_backend_error.log;

    # Proxy to Django (running on Docker port 8000)
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
    }

    # Serve media files directly
    location /media/ {
        alias /home/ubuntu/admin_backend_aws/media/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Serve static files directly
    location /static/ {
        alias /home/ubuntu/admin_backend_aws/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    listen 80;
}
```

### 5.3 Enable Nginx Config
```bash
sudo ln -s /etc/nginx/sites-available/z1-backend /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null
sudo nginx -t
sudo systemctl start nginx
sudo systemctl enable nginx
```

## Step 6: SSL/HTTPS Setup

### 6.1 Install Certbot
```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

### 6.2 Generate SSL Certificate
```bash
sudo certbot --nginx -d <YOUR_DOMAIN> -d www.<YOUR_DOMAIN>
```

Follow the prompts. Certbot will automatically update your Nginx config.

## Step 7: Fix Media File Permissions

Media files uploaded by the application need proper permissions for Nginx to serve them:

```bash
# Change ownership to www-data (Nginx user)
sudo chown -R www-data:www-data /home/ubuntu/admin_backend_aws/media/

# Set proper permissions
sudo chmod 755 /home/ubuntu/
sudo chmod 755 /home/ubuntu/admin_backend_aws/
sudo chmod -R 755 /home/ubuntu/admin_backend_aws/media/
sudo find /home/ubuntu/admin_backend_aws/media/ -type f -exec chmod 644 {} \;

# Verify
ls -la /home/ubuntu/admin_backend_aws/media/
```

## Step 8: Configure Django Settings

Update `z1_backend/settings.py` to include your domain in CORS and CSRF:

```python
CORS_ALLOWED_ORIGINS = [
    "https://<YOUR_DOMAIN>",
    "https://www.<YOUR_DOMAIN>",
    "http://<YOUR_EC2_IP>",
]

CSRF_TRUSTED_ORIGINS = [
    "https://<YOUR_DOMAIN>",
    "https://www.<YOUR_DOMAIN>",
    "http://<YOUR_EC2_IP>",
]
```

## Common Commands

### View Docker Logs
```bash
sudo docker-compose logs -f web
```

### Restart Services
```bash
# Restart Docker
sudo docker-compose restart web

# Restart Nginx
sudo systemctl restart nginx

# Restart MySQL
sudo systemctl restart mysql
```

### Collect Static Files
```bash
sudo docker-compose exec web python manage.py collectstatic --noinput
```

### Database Migrations
```bash
sudo docker-compose exec web python manage.py migrate
```

### Create Backup
```bash
sudo mysqldump -u django -p mydb > backup.sql
```

## Troubleshooting

### Media Files Return 403 Forbidden
Check file permissions:
```bash
sudo chown -R www-data:www-data /home/ubuntu/admin_backend_aws/media/
sudo chmod 755 /home/ubuntu/
sudo chmod 755 /home/ubuntu/admin_backend_aws/
sudo systemctl restart nginx
```

### Database Connection Issues
Verify MySQL is listening on all interfaces:
```bash
sudo ss -tlnp | grep 3306
```

Should show: `LISTEN 0:3306 0.0.0.0:*`

### Nginx 502 Bad Gateway
Check if Django container is running:
```bash
sudo docker-compose ps
```

View logs:
```bash
sudo docker-compose logs web
sudo tail -20 /var/log/nginx/z1_backend_error.log
```

## Security Notes

1. **Keep .env file secure** - Never commit to git
2. **Use strong JWT_SECRET_KEY** - Generate a random 50+ character key
3. **Enable DEBUG=False** in production
4. **Regularly update packages** - Run `apt update && apt upgrade`
5. **Monitor logs** - Check Nginx and Docker logs regularly
6. **Backup database** - Set up automated MySQL backups

## Support

For issues or questions, refer to:
- Docker Compose: https://docs.docker.com/compose/
- Nginx: https://nginx.org/en/docs/
- Let's Encrypt: https://letsencrypt.org/
