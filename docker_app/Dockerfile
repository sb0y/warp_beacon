FROM ubuntu:22.04
LABEL maintainer="Andrey Bagrintsev <andrey@bagrintsev.me>"

VOLUME /var/warp_beacon

ARG TERM=xterm
ARG LC_ALL=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive 

RUN echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes 

RUN echo "deb http://us.archive.ubuntu.com/ubuntu/ focal main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ focal-updates main restricted universe multiverse\n \
deb http://us.archive.ubuntu.com/ubuntu/ focal-backports main restricted universe multiverse\n \
deb http://security.ubuntu.com/ubuntu focal-security main restricted universe multiverse\n" /etc/apt/sources.list

RUN set -x \
	&& apt-get update -y \
	&& apt-get install python-is-python3 python3-pip python3-opencv -y

RUN set -x \
	&& mkdir -p /app/ /var/warp_beacon/ /var/warp_beacon/videos/

RUN set -x \
	&& pip install python-telegram-bot urlextract instagrapi pillow pymongo --upgrade

#WORKDIR /app

COPY ./entrypoint.sh .

ENTRYPOINT [ "/app/warp_beacon.py" ]