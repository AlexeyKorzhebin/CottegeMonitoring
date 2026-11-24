-- Lua 5.1-compatible harness for zb_light_sync LWW.
-- Usage: lua zb_light_sync_harness.lua /path/to/zb_light_sync.lua

local script_path = arg[1]
if not script_path then
  io.stderr:write('usage: lua zb_light_sync_harness.lua <zb_light_sync.lua>\n')
  os.exit(2)
end

local objects = {}
local storage_kv = {}
local updates = {}
local publishes = {}
local logs = {}
local writes = {}
local align_during_update = 0

storage = {
  get = function(k)
    return storage_kv[k]
  end,
  set = function(k, v)
    storage_kv[k] = v
  end,
}

grp = {
  find = function(addr)
    return objects[addr]
  end,
  update = function(addr, value)
    local flag = storage_kv['zb_light_from_sync_align'] or storage.zb_light_from_sync_align
    if flag == true or flag == 1 then
      align_during_update = align_during_update + 1
    end
    updates[#updates + 1] = { addr = addr, value = value }
    if objects[addr] then
      objects[addr].value = value
    end
  end,
  write = function(addr, value)
    writes[#writes + 1] = { addr = addr, value = value }
  end,
}

function log(msg)
  logs[#logs + 1] = tostring(msg)
end

function ZB_CEILING_PUBLISH(ga, value)
  publishes[#publishes + 1] = { ga = ga, value = value }
end

local failures = 0
local function fail(msg)
  failures = failures + 1
  io.stderr:write('FAIL: ' .. msg .. '\n')
end

local function assert_eq(got, expected, msg)
  if got ~= expected then
    fail(msg .. ' got=' .. tostring(got) .. ' expected=' .. tostring(expected))
  end
end

local function reset()
  objects = {}
  storage_kv = {}
  updates = {}
  publishes = {}
  logs = {}
  writes = {}
  align_during_update = 0
  storage.zb_light_from_sync_align = nil
end

local function obj(addr, value, ut)
  objects[addr] = { address = addr, value = value, updatetime = ut }
end

event = nil
dofile(script_path)
if type(zb_light_sync_run) ~= 'function' then
  io.stderr:write('FAIL: zb_light_sync_run is not a global function\n')
  os.exit(1)
end

-- Relay OFF: no send, no align.
reset()
obj('36/1/1', 50, 200)
obj('36/2/1', 10, 100)
event = {
  dst = '1/1/13',
  getvalue = function()
    return false
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'OFF no publish')
assert_eq(#updates, 0, 'OFF no update')
assert_eq(#writes, 0, 'OFF no write')

-- Control newer on Tima brightness; equal CCT/RGB.
reset()
obj('36/1/1', 50, 200)
obj('36/2/1', 10, 100)
obj('36/1/2', 300, 50)
obj('36/2/2', 300, 50)
obj('36/1/3', 1, 10)
obj('36/2/3', 2, 10)
event = {
  dst = '1/1/13',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 1, 'control newer: one publish')
assert_eq(publishes[1] and publishes[1].ga, '36/1/1', 'publish ga')
assert_eq(publishes[1] and publishes[1].value, 50, 'publish value')
assert_eq(#updates, 0, 'control newer: no align')

-- Status newer on hall CCT; guard must be set during grp.update and cleared after.
reset()
obj('36/1/4', 40, 10)
obj('36/2/4', 40, 10)
obj('36/1/5', 200, 10)
obj('36/2/5', 250, 99)
obj('36/1/6', 0, 10)
obj('36/2/6', 0, 10)
event = {
  dst = '1/1/15',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'status newer: no publish')
assert_eq(#updates, 1, 'status newer: one align')
assert_eq(updates[1] and updates[1].addr, '36/1/5', 'align ga')
assert_eq(updates[1] and updates[1].value, 250, 'align value')
assert_eq(align_during_update, 1, 'guard set during align')
assert_eq(storage_kv['zb_light_from_sync_align'] == true, false, 'guard cleared')
assert_eq(storage.zb_light_from_sync_align == true, false, 'field guard cleared')

-- Unknown relay: do not touch other zones.
reset()
obj('36/1/1', 1, 200)
obj('36/2/1', 1, 100)
event = {
  dst = '1/1/1',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'unknown relay no publish')
assert_eq(#updates, 0, 'unknown relay no update')

-- Missing updatetime / missing status → no-op (office).
reset()
obj('36/1/7', 50, nil)
obj('36/2/7', 10, 100)
obj('36/1/8', 1, 1)
obj('36/2/8', 1, 1)
obj('36/1/9', 1, 1)
obj('36/2/9', 1, 1)
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'missing ut no publish')
assert_eq(#updates, 0, 'missing ut no update')

-- Mixed Tima: publish brightness, align CCT, skip equal RGB; do not touch hall.
reset()
obj('36/1/1', 80, 500)
obj('36/2/1', 10, 100)
obj('36/1/2', 200, 10)
obj('36/2/2', 333, 400)
obj('36/1/3', 7, 50)
obj('36/2/3', 8, 50)
obj('36/1/4', 1, 1)
obj('36/2/4', 9, 999)
event = {
  dst = '1/1/13',
  getvalue = function()
    return 1
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 1, 'mixed publish count')
assert_eq(publishes[1] and publishes[1].ga, '36/1/1', 'mixed publish ga')
assert_eq(#updates, 1, 'mixed align count')
assert_eq(updates[1] and updates[1].addr, '36/1/2', 'mixed align ga')
assert_eq(updates[1] and updates[1].value, 333, 'mixed align value')
assert_eq(#writes, 0, 'never grp.write')
for i = 1, #updates do
  if updates[i].addr == '36/1/4' or updates[i].addr == '1/1/13' then
    fail('touched hall or relay via update')
  end
end
for i = 1, #publishes do
  if publishes[i].ga == '36/1/4' then
    fail('published hall')
  end
end

-- Fallback: no ZB_CEILING_PUBLISH → log, still no MQTT.
reset()
ZB_CEILING_PUBLISH = nil
obj('36/1/1', 50, 200)
obj('36/2/1', 10, 100)
obj('36/1/2', 1, 1)
obj('36/2/2', 1, 1)
obj('36/1/3', 1, 1)
obj('36/2/3', 1, 1)
event = {
  dst = '1/1/13',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'fallback no publish fn')
local found = false
for i = 1, #logs do
  if string.find(logs[i], 'zb_light_sync: need ZB_CEILING_PUBLISH', 1, true) then
    found = true
  end
end
assert_eq(found, true, 'fallback log')

-- event.dstraw when dst is missing (hall brightness control-newer).
reset()
function ZB_CEILING_PUBLISH(ga, value)
  publishes[#publishes + 1] = { ga = ga, value = value }
end
obj('36/1/4', 12, 80)
obj('36/2/4', 12, 10)
obj('36/1/5', 1, 1)
obj('36/2/5', 1, 1)
obj('36/1/6', 1, 1)
obj('36/2/6', 1, 1)
event = {
  dstraw = '1/1/15',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 1, 'dstraw publish')
assert_eq(publishes[1] and publishes[1].ga, '36/1/4', 'dstraw ga')

if failures > 0 then
  os.exit(1)
end
print('ALL PASS')
