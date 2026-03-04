<?
-- Export objects to JSON (for file download or MQTT meta format)
-- Call with ?action=export_file for download
require('apps')
local json = require('json')

local function safe_json_val(v)
  if v == nil then return nil end
  local t = type(v)
  if t == 'number' or t == 'string' or t == 'boolean' then return v end
  if t == 'table' then return v end
  return tostring(v)
end

local ok, err = pcall(function()
  if not grp or not grp.all then
    error('grp API unavailable')
  end
  local all = grp.all() or {}
  local sorted = {}
  for _, o in ipairs(all) do
    if o and o.address then
      table.insert(sorted, o)
    end
  end
  table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)

  local schema_hash = ''
  local encdec_ok, encdec = pcall(require, 'encdec')
  if encdec_ok and encdec and encdec.sha256 then
    local addrs = {}
    for _, o in ipairs(sorted) do
      table.insert(addrs, o.address or '')
    end
    schema_hash = 'sha256:' .. (encdec.sha256(json.encode(addrs)) or '')
  end

  local objects = {}
  for _, o in ipairs(sorted) do
    table.insert(objects, {
      id = o.id,
      address = o.address or '',
      name = o.name or '',
      datatype = o.datatype or 0,
      units = o.units or '',
      tags = o.tagcache or o.tags or '',
      comment = o.comment or '',
      value = safe_json_val(o.value)
    })
  end

  local payload = {
    ts = os.time(),
    schema_hash = schema_hash,
    count = #objects,
    objects = objects
  }

  local action = (getvar and getvar('action')) or ''
  if action == 'export_file' then
    if setheader then
      setheader('Content-Type', 'application/json; charset=utf-8')
      setheader('Content-Disposition', 'attachment; filename="cottage-monitoring-export.json"')
    end
    print(json.encode(payload))
  else
    print(json.encode({ error = 'use ?action=export_file' }))
  end
end)

if not ok then
  if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
  print(json.encode({ error = tostring(err) }))
end
?>
