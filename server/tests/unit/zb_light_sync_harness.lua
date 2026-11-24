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

-- LM has os.sleep; desktop Lua may not. Sync pauses must be no-ops in harness.
os = os or {}
os.sleep = function(_sec) end

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

-- Status newer on hall CCT: color modes must NOT align (echo flips RGB↔CCT).
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
assert_eq(#publishes, 0, 'status newer CCT: no publish')
assert_eq(#updates, 0, 'status newer CCT: no align')

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

-- Mixed Tima: publish brightness; CCT status-newer must not align (color echo).
reset()
obj('36/1/1', 80, 500)
obj('36/2/1', 10, 100)
obj('36/1/2', 200, 10)
obj('36/2/2', 333, 400)
obj('36/1/3', 7, 5)
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
assert_eq(#updates, 0, 'mixed: no color align')
assert_eq(#writes, 0, 'never grp.write')
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

-- Office was OFF: stale CCT control newer than status, but RGB control is newest
-- (cloud set blue + relay ON). Must not publish color_temp after rgb (Tuya mode flip).
reset()
obj('36/1/7', 45, 200)
obj('36/2/7', 10, 50)
obj('36/1/8', 500, 300)
obj('36/2/8', 500, 40)
obj('36/1/9', 255, 400)
obj('36/2/9', 0, 30)
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
local saw_bri, saw_cct, saw_rgb = false, false, false
for i = 1, #publishes do
  if publishes[i].ga == '36/1/7' then saw_bri = true end
  if publishes[i].ga == '36/1/8' then saw_cct = true end
  if publishes[i].ga == '36/1/9' then saw_rgb = true end
end
assert_eq(saw_bri, true, 'office publish brightness')
assert_eq(saw_cct, false, 'office must never publish CCT from sync')
assert_eq(saw_rgb, false, 'office must never publish RGB from sync')

-- Re-assert ON while already ON: no second LWW (cloud blue→white must not
-- republish stale RGB after concurrent CCT).
publishes = {}
updates = {}
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 're-assert ON must not republish')
assert_eq(#updates, 0, 're-assert ON must not align')

-- OFF clears edge; next ON catch-up runs again.
event = {
  dst = '1/1/14',
  getvalue = function()
    return false
  end,
}
zb_light_sync_run()
assert_eq(#publishes, 0, 'OFF no publish')
obj('36/1/7', 45, 200)
obj('36/2/7', 10, 50)
obj('36/1/8', 370, 500)
obj('36/2/8', 370, 40)
obj('36/1/9', 255, 400)
obj('36/2/9', 0, 30)
publishes = {}
updates = {}
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
local saw_cct2, saw_rgb2 = false, false
for i = 1, #publishes do
  if publishes[i].ga == '36/1/8' then saw_cct2 = true end
  if publishes[i].ga == '36/1/9' then saw_rgb2 = true end
end
assert_eq(saw_cct2, false, 'sync never publishes CCT')
assert_eq(saw_rgb2, false, 'sync never publishes RGB')

-- RGB already caught up (status==control) but older CCT still cu>su.
-- Intent is RGB by updatetime → must NOT publish CCT (blue→white flip).
reset()
obj('36/1/7', 100, 200)
obj('36/2/7', 100, 200)
obj('36/1/8', 370, 300)
obj('36/2/8', 370, 40)
obj('36/1/9', 255, 400)
obj('36/2/9', 255, 400)
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
local saw_cct3, saw_rgb3 = false, false
for i = 1, #publishes do
  if publishes[i].ga == '36/1/8' then saw_cct3 = true end
  if publishes[i].ga == '36/1/9' then saw_rgb3 = true end
end
assert_eq(saw_cct3, false, 'synced RGB intent must not publish older CCT')
assert_eq(saw_rgb3, false, 'already-synced RGB need not republish')
for i = 1, #updates do
  if updates[i].addr == '36/1/8' then
    fail('older CCT must not align (would echo to z2m)')
  end
end

-- Intent RGB; CCT status newer (mqtt_listen refreshed color_temp from xy state).
-- Must not align CCT (would echo color_temp and flip blue→white).
reset()
obj('36/1/7', 100, 100)
obj('36/2/7', 100, 100)
obj('36/1/8', 573, 300)
obj('36/2/8', 573, 500)
obj('36/1/9', 255, 400)
obj('36/2/9', 0, 50)
event = {
  dst = '1/1/14',
  getvalue = function()
    return true
  end,
}
zb_light_sync_run()
for i = 1, #publishes do
  if publishes[i].ga == '36/1/8' then
    fail('must not publish CCT when RGB is intent')
  end
end
for i = 1, #updates do
  if updates[i].addr == '36/1/8' then
    fail('must not align CCT when RGB is intent')
  end
end
local saw_rgb4 = false
for i = 1, #publishes do
  if publishes[i].ga == '36/1/9' then saw_rgb4 = true end
end
assert_eq(saw_rgb4, false, 'sync never publishes RGB even if intent')

if failures > 0 then
  os.exit(1)
end
print('ALL PASS')
