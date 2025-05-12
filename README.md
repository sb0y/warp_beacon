# warp_beacon [![Upload Python Package](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml) [![Docker Image CI](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml) [![Build DEB package](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml)
> because content should travel freely

Telegram bot that expands media links from external social networks.
Works with links sent in private messages or group chats.

Just send a media link to the bot, and it will reply with a video or audio file.

| | | |
|:-------------------------:|:-------------------------:|:-------------------------:|
|<img width="700" alt="Yotube Video usage example" src="https://github.com/user-attachments/assets/280b058f-325b-4386-9556-f145f6db9cfa"> Yotube Video usage example |<img width="700" alt="Youtube Music usage example" src="https://github.com/user-attachments/assets/3a462a3b-8c80-460f-aa66-c39db24f7a24"> Youtube Music usage example|<img width="703" alt="image" src="https://github.com/user-attachments/assets/384206ea-1371-48d5-a717-92aff06fa339"> Instagram Reels usage example |
|<img width="700" alt="Instagram Photo post usage example" src="https://github.com/user-attachments/assets/29324b94-7314-4a38-8790-3483011d355d"> Instagram Photo post usage example|<img width="700" alt="Instagram Photo Carousel usage" src="https://github.com/user-attachments/assets/2598e329-e16e-455e-91e9-a027e8994283"> Instagram Photo Carousel usage example|<img width="757" alt="Instagram Photo bulk Strories download usage example" src="https://github.com/user-attachments/assets/2c8c91ac-6ade-4d1d-a677-2b36bb40ff39"> Instagram Photo bulk Strories download usage example|
|<img width="700" alt="Instagram specific Story download usage example" src="https://github.com/user-attachments/assets/03dc70c5-6933-4122-9c7c-5f7d734d117b"> Instagram specific Story download usage example|<img width="700" alt="Group chat usage example" src="https://github.com/user-attachments/assets/649fcb1e-785b-4efd-9153-69644c6d898b"> Group chat usage example|

### **Warp Beacon manifesto**

> Once, the Internet was built as a borderless network — a space where knowledge, culture, and ideas could flow freely across the globe.  
> But over time, freedom gave way to artificial walls, anti-bot shields, and region locks.
>
> **warp_beacon** is our answer to that shift.
>
> This is a tool for those who refuse to accept "access denied by geolocation" or "content unavailable in your region."  
> It is a bridge over ML filters, CAPTCHAs, and man-made barriers.
>
> We don’t break the rules — we restore the original spirit of the Internet:  
> 📡 **free exchange of information**,  
> 🌍 **unrestricted access to global content**,  
> 🤖 **tools that serve the user**, not the platform.
>
> **warp_beacon** — the freedom to deliver content where it’s needed most.

## Configuration example ##

In order to setup your own instance, you will need:

1. Obtain your own brand new `TG_TOKEN`. To do that, write to [@BotFather](https://t.me/BotFather).
2. Obtain `TG_API_ID`, `TG_API_HASH`, `TG_BOT_NAME`. Learn more [here](https://core.telegram.org/api/obtaining_api_id).

All bot configuration stored in [warp_beacon.conf](https://github.com/sb0y/warp_beacon/blob/main/etc/warp_beacon.conf) file.

```env
TG_TOKEN="you telegram token received from @BotFather"
# these 3 settings should be obtained at https://my.telegram.org/apps
# learn more: https://core.telegram.org/api/obtaining_api_id
###
TG_API_ID=""
TG_API_HASH=""
TG_BOT_NAME=""
# bot admin username, e.g.: @BelisariusCawl
# Used for communication between the bot and the administrator.
# For example, if authorization is required for YouTube, bot can send an authorization code via message to this address.
TG_BOT_ADMIN_USERNAME=""
###
INSTAGRAM_LOGIN="instagram login (email or cell phone)"
INSTAGRAM_PASSWORD="instgram password"
MONGODB_HOST="mongodb"
MONGODB_PORT="27017"
MONGODB_USER="root"
MONGODB_PASSWORD="changeme"
# more information about accounts.json and proxies.json
# can be found in project wiki
# https://github.com/sb0y/warp_beacon/wiki/Introduction-in-account.json-file
SERVICE_ACCOUNTS_FILE=/var/warp_beacon/accounts.json
PROXY_FILE=/var/warp_beacon/proxies.json

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
## Upgrading ##
If you are using `image-prod` (set in `docker-compose.yml` by default), just rebuild your image:
```bash
cd your_warp_beacon_sources_directory/
sudo docker compose build --no-cache
```
Recreate existing container:
```bash
sudo docker compose up -d
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

# Wiki
* [MongoDB backup and restore](https://github.com/sb0y/warp_beacon/wiki/MongoDB-backup-and-restore)
* [Introduction in account.json file](https://github.com/sb0y/warp_beacon/wiki/Introduction-in-account.json-file)

# Support Warp Beacon project

[<img src="https://opencollective.com/webpack/donate/button@2x.png?color=blue" alt="Donate" width="300px">](https://opencollective.com/warp_beacon) [<img src="https://raw.githubusercontent.com/sb0y/warp_beacon/refs/heads/main/assets/cc-group-black.png?raw=true" alt="CryptoCloud Accepted" width="250px">](https://pay.cryptocloud.plus/pos/W5BMtNQt5bJFoW2E)

<!-- [![Backers on Open Collective](https://opencollective.com/warp_beacon/backers/badge.svg)](https://opencollective.com/warp_beacon) -->
<!-- #[![Sponsors on Open Collective](https://opencollective.com/warp_beacon/sponsors/badge.svg)](https://opencollective.com/warp_beacon) -->

