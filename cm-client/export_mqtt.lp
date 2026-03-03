<?lua
local json = require('json')
-- Check MQTT connected and set force_export for daemon to publish meta+snapshot
local connected = storage.get('mqtt_connected')
if connected then
  storage.set('force_export', 1)
  print(json.encode({ ok = true, mqtt_connected = true }))
else
  print(json.encode({ ok = false, mqtt_connected = false, msg = 'MQTT недоступен' }))
end
?>
