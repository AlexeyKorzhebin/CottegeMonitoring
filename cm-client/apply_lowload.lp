<?
-- Применяет настройки для снижения нагрузки (throttle, event_sleep, loop_sleep)
-- Вызов: GET/POST http://lm/apps/data/cottage-monitoring/apply_lowload.lp
require('apps')
config.set('cottage-monitoring', 'throttle', 30)
config.set('cottage-monitoring', 'event_sleep', 0.02)
config.set('cottage-monitoring', 'loop_sleep', 0.15)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
local json = require('json')
print(json.encode({ ok = true, msg = 'throttle=30, event_sleep=0.02, loop_sleep=0.15 applied. Restart daemon.' }))
?>
