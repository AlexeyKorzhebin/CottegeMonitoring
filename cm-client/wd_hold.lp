<?
require('apps')
-- Hold watchdog without faking mqtt_connected (for live bring-up).
local t = os.time()
storage.set('cm_force_restart', nil)
storage.set('cm_watchdog_soft_ts', 0)
storage.set('cm_watchdog_last_restart', t)
storage.set('cm_watchdog_last_alert', t)
storage.set('cm_last_disconnect_ts', nil)
storage.set('cm_heartbeat', t)
storage.set('cm_mqtt_connected', false)
storage.set('mqtt_connected', false)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print('{"hold":true,"ts":' .. t .. '}')
?>
