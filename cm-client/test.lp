<?
-- Диагностика: http://IP/apps/data/cottage-monitoring/test.lp
local json = require('json')
local r = {}
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end

local ok_apps, err_apps = pcall(require, 'apps')
r.apps = ok_apps and 'ok' or ('fail: ' .. tostring(err_apps))

r.grp = (grp and grp.all) and 'ok' or (grp and 'no_all') or 'nil'
r.storage = (storage and storage.get) and 'ok' or (storage and 'no_get') or 'nil'

if r.grp == 'ok' then
  local ok_g, err_g = pcall(function()
    local a = grp.all() or {}
    r.grp_count = #a
  end)
  if not ok_g then r.grp_err = tostring(err_g) end
end
if r.storage == 'ok' then
  r.mqtt_connected = storage.get('mqtt_connected')
end

print(json.encode(r))
?>
