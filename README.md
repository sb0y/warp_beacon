# warp_beacon [![Upload Python Package](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/python-publish.yml) [![Docker Image CI](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/docker-image.yml) [![Build DEB package](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml/badge.svg)](https://github.com/sb0y/warp_beacon/actions/workflows/build-deb.yml)

Telegram bot for external social networks media links expanding.
Works with a links in personal messages and also with group chats.

Just send a media link to the chat with bot and get a video or audio reply.

| | |
|:-------------------------:|:-------------------------:|
|<img width="750" alt="Youtube Video usage example" src="https://github.com/user-attachments/assets/ea2ed57a-1004-4442-bb83-265566afe3c2"> Yotube Video usage example |  <img width="750" alt="Youtube Audio usage example" src="https://github.com/user-attachments/assets/13769989-6b0e-4490-ba31-82a2326d99c6"> Youtube Audio usage example |<img width="664" alt="Instagram Reels usage example" src="https://github.com/user-attachments/assets/869a2378-5e30-4add-91e5-236dfac473f6"> Instagram Reels usage example|
|<img width="646" alt="Instagram Photo post usage example" src="https://github.com/user-attachments/assets/35aa52f8-b0b8-4254-938b-189bcd0c9fa6"> Instagram Photo post usage example| <img width="771" alt="Instagram Photo Carousel usage example" src="https://github.com/user-attachments/assets/62c716dd-e3bd-4eb7-8835-0fcb058ca06d"> Instagram Photo Carousel usage example| <img width="757" alt="Instagram Photo bulk Strories download usage example" src="https://github.com/user-attachments/assets/2c8c91ac-6ade-4d1d-a677-2b36bb40ff39"> Instagram Photo bulk Strories download usage example|
|<img width="670" alt="Instagram specific Story download usage example" src="https://github.com/user-attachments/assets/27519994-b56c-4b92-8631-f24fe158bfcd"> Instagram specific Story download usage example|

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

# Support Warp Beacon project

[<img src="https://cdn.cryptocloud.plus/brand/cc-group-black.png" alt="CryptoCloud Accepted" width="250px">](https://pay.cryptocloud.plus/pos/W5BMtNQt5bJFoW2E)
