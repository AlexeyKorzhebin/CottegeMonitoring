<?
-- Heal profile: snapshot instead of dropping groupwrites (no throttle / event_sleep)
-- Вызов: GET/POST http://lm/apps/data/cottage-monitoring/apply_lowload.lp
require('apps')
config.set('cottage-monitoring', 'throttle', 0)
config.set('cottage-monitoring', 'event_sleep', 0)
config.set('cottage-monitoring', 'loop_sleep', 0.25)
config.set('cottage-monitoring', 'batch_interval', 1.5)
config.set('cottage-monitoring', 'batch_max_size', 50)
config.set('cottage-monitoring', 'snapshot_interval', 300)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
local json = require('json')
print(json.encode({ ok = true, msg = 'heal: throttle=0, event_sleep=0, snapshot_interval=300, batch=1.5. Restart daemon.' }))
?>
