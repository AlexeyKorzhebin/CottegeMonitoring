<?
require('apps')
-- Pause watchdog soft/hard for ~5 min (cooldown via last_restart).
-- Also clears force-restart so daemon can stay up during deploy.
local t = os.time()
storage.set('cm_force_restart', nil)
storage.set('cm_watchdog_soft_ts', 0)
storage.set('cm_watchdog_last_restart', t)
storage.set('cm_watchdog_last_alert', t)
storage.set('cm_heartbeat', t)
storage.set('cm_mqtt_connected', true)
storage.set('mqtt_connected', true)
storage.set('cm_started_ts', t)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print('{"paused":true,"ts":' .. t .. '}')
?>
