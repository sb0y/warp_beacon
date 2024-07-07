#
# Regular cron jobs for the warp-beacon package
#
0 4	* * *	root	[ -x /usr/bin/warp-beacon_maintenance ] && /usr/bin/warp-beacon_maintenance
