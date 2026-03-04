<?
-- Приём POST JSON и сохранение через config.setall
require('apps')
local json = require('json')
local body = getvar('config') or getvar('body')
if not body then
  if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
  print(json.encode({ ok = false, msg = 'missing config' }))
  return
end
local ok, cfg = pcall(json.decode, body)
if not ok or not cfg then
  if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
  print(json.encode({ ok = false, msg = 'invalid json' }))
  return
end
config.setall('cottage-monitoring', cfg)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print(json.encode({ ok = true }))
?>
