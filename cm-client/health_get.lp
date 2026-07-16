<?
require('apps')
local json = require('json')

local function num(key)
  local v = storage.get(key)
  if v == nil or v == '' then return nil end
  return tonumber(v)
end

local function bool(key)
  local v = storage.get(key)
  return v == true or v == 'true' or v == 1 or v == '1'
end

local now = os.time()
local heartbeat = num('cm_heartbeat')
local started = num('cm_started_ts')
local mqtt = bool('cm_mqtt_connected') or bool('mqtt_connected')

local out = {
  ok = true,
  ts = now,
  mqtt_connected = mqtt,
  heartbeat = heartbeat,
  heartbeat_age = heartbeat and (now - heartbeat) or nil,
  started_ts = started,
  uptime = started and (now - started) or nil,
  reconnect_count = num('cm_reconnect_count') or 0,
  last_connect_ts = num('cm_last_connect_ts'),
  last_disconnect_ts = num('cm_last_disconnect_ts'),
  last_error = tostring(storage.get('cm_last_error') or ''),
  watchdog_restarts = num('cm_watchdog_restarts') or 0,
  watchdog_last_reason = tostring(storage.get('cm_watchdog_last_reason') or ''),
  watchdog_last_restart = num('cm_watchdog_last_restart'),
}

if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print(json.encode(out))
?>
