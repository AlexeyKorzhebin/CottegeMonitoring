<?
-- Возврат текущего конфига в JSON для index.lp
require('apps')
local json = require('json')
local cfg = config.getall('cottage-monitoring') or {}
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
-- не отдаём пароль на клиент
if cfg.mqtt_password then cfg.mqtt_password = '***' end
print(json.encode(cfg))
?>
