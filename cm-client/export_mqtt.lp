<?
require('apps')
local json = require('json')
-- Check MQTT connected and set force_export for daemon to publish meta+snapshot
local connected = false
local ok, err = pcall(function()
  if storage and storage.get then
    connected = storage.get('mqtt_connected')
    if connected and storage.set then
      storage.set('force_export', 1)
    end
  end
end)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
if not ok then
  print(json.encode({ ok = false, mqtt_connected = false, msg = 'storage error: ' .. tostring(err) }))
elseif connected then
  print(json.encode({ ok = true, mqtt_connected = true }))
else
  print(json.encode({ ok = false, mqtt_connected = false, msg = 'MQTT недоступен' }))
end
?>
