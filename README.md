# warp_beacon [![Upload Python Package](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml) [![Docker Image CI](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml) 

Telegram bot for external social networks media scrapling.
Works with links in personal messages and also with group chats.

Just send to bot media link and get video.

All bot configuration stored in [variables.env](https://github.com/sb0y/warp_beacon/blob/main/variables.env) file.

## Configuration example ##

```env
TG_TOKEN="you telegram token received from @BotFather"
INSTAGRAM_LOGIN="instagram login (email or cell phone)"
INSTAGRAM_PASSWORD="instgram password"
INSTAGRAM_VERIFICATION_CODE="instagram 2FA if required, default empty"
MONGODB_HOST="mongodb"
MONGODB_PORT="27017"
MONGODB_USER="root"
MONGODB_PASSWORD="changeme"
VIDEO_STORAGE_DIR="/var/warp_beacon/videos"
WORKERS_POOL_SIZE=3
```
## Deployed example bot ##
[Try it 🚀](https://t.me/anus_sebe_zablokiruy_bot)

## How to run ##
Any Linux machine will suit in.

Install docker and git
```
apt update
apt install docker-compose git
```

Download sources
```bash
git clone https://github.com/sb0y/warp_beacon.git
```
Go to sources directory
```bash
cd warp_beacon
```

Run app
```bash
docker-compose up -d
```

Check logs
```bash
docker-compose logs warp_beacon -f
```
