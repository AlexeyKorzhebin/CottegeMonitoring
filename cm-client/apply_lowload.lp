<?
-- Применяет настройки для снижения нагрузки (batch + throttle + sleeps)
-- Вызов: GET/POST http://lm/apps/data/cottage-monitoring/apply_lowload.lp
require('apps')
config.set('cottage-monitoring', 'throttle', 20)
config.set('cottage-monitoring', 'event_sleep', 0.03)
config.set('cottage-monitoring', 'loop_sleep', 0.25)
config.set('cottage-monitoring', 'batch_interval', 1.5)
config.set('cottage-monitoring', 'batch_max_size', 50)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
local json = require('json')
print(json.encode({ ok = true, msg = 'throttle=20, event_sleep=0.03, loop_sleep=0.25, batch_interval=1.5 applied. Restart daemon.' }))
?>
