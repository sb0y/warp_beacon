#!/bin/bash

if [[ -f /init_accounts.json ]];
then
	mv -f /init_accounts.json /var/warp_beacon/accounts.json
fi

if [[ -f /init_proxies.json ]];
then
	mv -f /init_proxies.json /var/warp_beacon/proxies.json
fi

#if [[ -L /var/warp_beacon/src ]] && [[ -e /var/warp_beacon/src ]];
#then
#	cp -Rf /var/warp_beacon/src/* /usr/local/lib/python3.10/dist-packages/warp_beacon/
#fi

exec /usr/local/bin/warp_beacon