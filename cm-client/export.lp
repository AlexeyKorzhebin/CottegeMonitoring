<?lua
-- Export objects to JSON (for file download or MQTT meta format)
-- Call with ?format=file for download, or from daemon for meta

local grp = grp
local json = require('json')
local ts = os.time()

local function format_obj(o)
  return {
    id = o.id,
    address = o.address or '',
    name = o.name or '',
    datatype = o.datatype or 0,
    units = o.units or '',
    tags = o.tagcache or o.tags or '',
    comment = o.comment or '',
    value = o.value
  }
end

local all = grp.all() or {}
local sorted = {}
for _, o in ipairs(all) do
  if o.address then
    table.insert(sorted, o)
  end
end
table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)

local schema_hash = ''
local ok, encdec = pcall(require, 'encdec')
if ok and encdec and encdec.sha256 then
  local addrs = {}
  for _, o in ipairs(sorted) do
    table.insert(addrs, o.address)
  end
  schema_hash = 'sha256:' .. (encdec.sha256(json.encode(addrs)) or '')
end

local objects = {}
for _, o in ipairs(sorted) do
  table.insert(objects, format_obj(o))
end

local payload = {
  ts = ts,
  schema_hash = schema_hash,
  count = #objects,
  objects = objects
}

local action = getvar and getvar('action') or ''
if action == 'export_file' then
  if setheader then
    setheader('Content-Type', 'application/json; charset=utf-8')
    setheader('Content-Disposition', 'attachment; filename="cottage-monitoring-export.json"')
  end
  print(json.encode(payload))
else
  print(json.encode({ error = 'use ?action=export_file' }))
end
?>
