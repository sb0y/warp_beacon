FROM ubuntu:22.04 AS base
LABEL maintainer="Andrey Bagrintsev <andrey@bagrintsev.me>"

COPY ./docker_app/entrypoint.sh /usr/local/bin/
COPY ./etc/accounts.json /init_accounts.json
COPY ./etc/proxies.json /init_proxies.json
VOLUME /tmp
WORKDIR /var/tmp
VOLUME /var/warp_beacon

ENTRYPOINT [ "/usr/local/bin/entrypoint.sh" ]

ARG TERM=xterm
ARG LC_ALL=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive 

RUN set -x \
	&& echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/90assumeyes \
	&& echo "deb http://us.archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse\n \
	deb http://us.archive.ubuntu.com/ubuntu/ jammy-updates main restricted universe multiverse\n \
	deb http://us.archive.ubuntu.com/ubuntu/ jammy-backports main restricted universe multiverse\n \
	deb http://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse\n" /etc/apt/sources.list \
	&& apt-get update -y \
	&& apt-get install python-is-python3 python3-pip ffmpeg pkg-config \
	libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libavfilter-dev libswscale-dev libswresample-dev -y \
	&& mkdir -p /var/warp_beacon/

# Build prod image
FROM base AS image-prod
RUN set -x \
	&& python3 -m pip install av==12.3.0 --no-binary av \
	&& python3 -m pip install warp-beacon --upgrade

# Build dev image
FROM base AS image-dev
RUN set -x \
	&& python3 -m pip install av==12.3.0 --no-binary av \
	&& python3 -m pip install warp-beacon --upgrade \
	&& ln -sf `python3 -c 'import os, warp_beacon; print(os.path.dirname(os.path.abspath(warp_beacon.__file__)))'` /var/warp_beacon/src \
	&& find /var/warp_beacon/src/ | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs rm -rf
VOLUME /var/warp_beacon/src