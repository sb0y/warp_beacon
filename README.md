# warp_beacon [![Upload Python Package](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml) [![Docker Image CI](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml) [![Build DEB package](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml)

Telegram bot for external social networks media expanding.
Works with links in personal messages and also with group chats.

Just send a media link to the chat with bot and get a video or audio reply.

<img width="549" alt="image" src="https://github.com/user-attachments/assets/6d1cf0d8-4aa9-4852-90c9-6817974a7dd9">

In order to setup your own instance, you will need:

1. Obtain your own brand new `TG_TOKEN`. To do that, write to [@BotFather](https://t.me/BotFather).
2. Obtain `TG_API_ID`, `TG_API_HASH`, `TG_BOT_NAME`. Learn more [here](https://core.telegram.org/api/obtaining_api_id).

All bot configuration stored in [warp_beacon.conf](https://github.com/sb0y/warp_beacon/blob/main/etc/warp_beacon.conf) file.

## Configuration example ##

```env
TG_TOKEN="you telegram token received from @BotFather"
# these 3 settings should be obtained at https://my.telegram.org/apps
# learn more: https://core.telegram.org/api/obtaining_api_id
###
TG_API_ID=""
TG_API_HASH=""
TG_BOT_NAME=""
###
INSTAGRAM_LOGIN="instagram login (email or cell phone)"
INSTAGRAM_PASSWORD="instgram password"
INSTAGRAM_VERIFICATION_CODE="instagram 2FA if required, default empty"
MONGODB_HOST="mongodb"
MONGODB_PORT="27017"
MONGODB_USER="root"
MONGODB_PASSWORD="changeme"
VIDEO_STORAGE_DIR="/var/warp_beacon/videos"
# workers settings
# default: min(32, os.cpu_count() + 4)
#TG_WORKERS_POOL_SIZE=3
#UPLOAD_POOL_SIZE=3
#WORKERS_POOL_SIZE=3
ENABLE_DONATES=true
DONATE_LINK="your donate link which will be shown if ENABLE_DONATES where set"
```
## Deployed example bot ##
[Try it 🚀](https://t.me/anus_sebe_zablokiruy_bot)

## How to run ##
Any Linux machine will suit in.

Install docker and git
```bash
sudo apt update
# uninstall old docker packages
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done
sudo apt install ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin git
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
sudo docker compose up -d
```

Check logs
```bash
sudo docker compose logs warp_beacon -f
```

## How to install from PIP ##

```bash
sudo apt update
sudo apt install python3-pip
sudo pip install warp-beacon
```

Your configuration file will be located at `/usr/local/lib/python3.10/dist-packages/etc/warp_beacon/warp_beacon.conf`.
For convenience, we will copy it to a common directory:

```bash
mkdir /etc/warp_beacon
cp /usr/local/lib/python3.10/dist-packages/etc/warp_beacon/warp_beacon.conf /etc/warp_beacon/warp_beacon.conf
```

Run the app

```bash
source /etc/warp_beacon/warp_beacon.conf && /usr/local/bin/warp_beacon
```

Most likely you will need a systemd service so that you don't have to start the service manually and don't have to worry about service start on server reboot.

```bash
cp /usr/local/lib/python3.10/dist-packages/lib/systemd/system/warp_beacon.service /lib/systemd/system
systemctl unmask warp_beacon.service
systemctl enable warp_beacon.service
# start the service app
systemctl start warp_beacon.service
```

## How to build Python whl package ##
```bash
sudo apt install python3-pip python3-build python3-virtualenv dh-virtualenv
# If you are getting build errors you probably need the latest version of python3-build
sudo python3 -m pip install --upgrade build
python3 -m build
```

## How to build Ubuntu deb package ##

```bash
sudo apt update
sudo apt install debhelper python3-pip python3-build python3-virtualenv dh-virtualenv dh-python
# If you are getting build errors you probably need the latest version of python3-build
sudo python3 -m pip install --upgrade build
```

build deb file

```bash
dpkg-buildpackage -us -uc -b
```
