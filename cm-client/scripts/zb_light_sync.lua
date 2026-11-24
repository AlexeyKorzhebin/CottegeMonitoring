--[[
  zb_light_sync.lua

  Event script. Tag filter: zb_light_sync.

  Install (LM UI / scripting DB):
    Scripting → Event → New. Paste this file (or db:insert into scripting).
    Type: Event. Tag filter: zb_light_sync.
    Objects: KNX relay controls 1/1/13 (Тима), 1/1/15 (Холл), 1/1/14 (Кабинет).
    create-zb-ceiling-light-objects.lua adds that tag to the relays.

  Behaviour (design §6.3 / §7):
    Fires when a tagged relay changes (event.dst = relay GA).
    Relay false/OFF → return (no send).
    Relay true/ON → last-write-wins per zone param:
      control.updatetime > status.updatetime → publish set from control
      status.updatetime > control.updatetime → set storage.zb_light_from_sync_align,
        grp.update(control, status value), clear flag (LM catches up to z2m UI;
        zigbee_send fragment skips publish while the flag is set)
      equal / missing objects / missing updatetime → no-op
    Does not write the relay. Does not touch other zones.

  Publish path — NO MQTT password in this file.
    Prefer global ZB_CEILING_PUBLISH(ga, value) if it exists.
    Live install: after merging zigbee_send_ceiling_fragment.lua into zigbee_send,
    define in THIS event script (same VM cannot see zigbee_send globals):

      function ZB_CEILING_PUBLISH(ga, value)
        zigbee_send_ceiling_maybe(ga, value, function(topic, payload)
          mclient:publish(topic, payload, 0, false)
        end)
      end

    using the existing mosquitto client / login from live zigbee_send (keep
    credentials off git). Optional dofile of zigbee_send_ceiling_fragment.lua
    from an FTP path loads payload helpers only.
    Fallback: log topic/payload and 'zb_light_sync: need ZB_CEILING_PUBLISH'.
]]

local ALIGN_FLAG = 'zb_light_from_sync_align'

local RELAY_ZONES = {
  -- Тима: group Ceiling_lamps_tima (not two device publishes)
  ['1/1/13'] = {
    zone = 'Тима',
    topic = 'zigbee2mqtt/Ceiling_lamps_tima/set',
    params = {
      { param = 'brightness', control = '36/1/1', status = '36/2/1' },
      { param = 'color_temp', control = '36/1/2', status = '36/2/2' },
      { param = 'rgb',        control = '36/1/3', status = '36/2/3' },
    },
  },
  ['1/1/15'] = {
    zone = 'Холл',
    topic = 'zigbee2mqtt/Ceiling_lamp_hall_2_floor/set',
    params = {
      { param = 'brightness', control = '36/1/4', status = '36/2/4' },
      { param = 'color_temp', control = '36/1/5', status = '36/2/5' },
      { param = 'rgb',        control = '36/1/6', status = '36/2/6' },
    },
  },
  ['1/1/14'] = {
    zone = 'Кабинет',
    topic = 'zigbee2mqtt/Ceiling_lamp_office/set',
    params = {
      { param = 'brightness', control = '36/1/7', status = '36/2/7' },
      { param = 'color_temp', control = '36/1/8', status = '36/2/8' },
      { param = 'rgb',        control = '36/1/9', status = '36/2/9' },
    },
  },
}

-- Payload helpers duplicated from zigbee_send_ceiling_fragment.lua (no json/mqtt).
local function PctToBri254(pct)
  local n = tonumber(pct)
  if n == nil then return nil end
  local bri = math.floor(n * 2.54 + 0.5)
  if bri < 0 then bri = 0 end
  if bri > 254 then bri = 254 end
  return bri
end

local function Uint32ToColor(value)
  local n = tonumber(value)
  if n == nil then return nil end
  n = math.floor(n + 0.5)
  if n < 0 then n = 0 end
  if n > 16777215 then n = 16777215 end
  return {
    r = math.floor(n / 65536),
    g = math.floor((n % 65536) / 256),
    b = n % 256,
  }
end

local function payload_desc(param, value)
  if param == 'brightness' then
    return 'brightness=' .. tostring(PctToBri254(value))
  end
  if param == 'color_temp' then
    return 'color_temp=' .. tostring(value)
  end
  if param == 'rgb' then
    local c = Uint32ToColor(value)
    if not c then return 'rgb=nil' end
    return string.format('color={r=%d,g=%d,b=%d}', c.r, c.g, c.b)
  end
  return tostring(value)
end

local function safe_log(msg)
  if log then
    pcall(log, msg)
  end
end

local function set_align_flag(on)
  local v = on and true or false
  if not storage then return end
  if storage.set then
    pcall(storage.set, ALIGN_FLAG, v)
  end
  storage.zb_light_from_sync_align = v
end

local fragment_tried = false
local function maybe_dofile_fragment()
  if fragment_tried then return end
  fragment_tried = true
  if type(ZB_CEILING_PUBLISH) == 'function' then return end
  local paths = {
    'zigbee_send_ceiling_fragment.lua',
    '/home/ftp/scripts/zigbee_send_ceiling_fragment.lua',
    '/www/apps/data/cottage-monitoring/scripts/zigbee_send_ceiling_fragment.lua',
  }
  for i = 1, #paths do
    if pcall(dofile, paths[i]) then
      return
    end
  end
end

local function publish_control(ga, value, topic, param)
  set_align_flag(false)
  maybe_dofile_fragment()
  if type(ZB_CEILING_PUBLISH) == 'function' then
    pcall(ZB_CEILING_PUBLISH, ga, value)
    return
  end
  safe_log(
    'zb_light_sync: need ZB_CEILING_PUBLISH ga='
      .. tostring(ga)
      .. ' topic='
      .. tostring(topic)
      .. ' param='
      .. tostring(param)
      .. ' value='
      .. tostring(value)
      .. ' payload='
      .. payload_desc(param, value)
  )
end

local function align_control(control_ga, status_value)
  set_align_flag(true)
  local ok, err = pcall(function()
    grp.update(control_ga, status_value)
  end)
  set_align_flag(false)
  if not ok then
    safe_log(
      'zb_light_sync: align failed '
        .. tostring(control_ga)
        .. ' '
        .. tostring(err)
    )
  end
end

local function find_obj(addr)
  if not addr or not grp or not grp.find then return nil end
  local ok, obj = pcall(function()
    return grp.find(addr)
  end)
  if ok then return obj end
  return nil
end

local function read_updatetime(obj)
  if not obj then return nil end
  local t = obj.updatetime
  if t == nil then return nil end
  if type(t) == 'number' then return t end
  return tonumber(t)
end

-- 'publish' | 'align' | 'noop'
local function lww_action(ctrl, stat)
  local cu = read_updatetime(ctrl)
  local su = read_updatetime(stat)
  if cu == nil or su == nil then return 'noop' end
  if cu > su then return 'publish' end
  if su > cu then return 'align' end
  return 'noop'
end

local function relay_is_on(v)
  if v == true or v == 1 then return true end
  if type(v) == 'string' then
    local u = string.upper(v)
    return u == 'ON' or u == 'TRUE' or u == '1'
  end
  return false
end

local function event_dst()
  if not event then return nil end
  return event.dst or event.dstraw
end

local function event_value()
  if not event then return nil end
  if not event.getvalue then return nil end
  local ok, v = pcall(event.getvalue)
  if ok then return v end
  ok, v = pcall(event.getvalue, event)
  if ok then return v end
  return nil
end

function zb_light_sync_run()
  if not event then return end
  local dst = event_dst()
  if not dst then return end
  local zone = RELAY_ZONES[dst]
  if not zone then return end
  if not relay_is_on(event_value()) then return end

  for i = 1, #zone.params do
    local p = zone.params[i]
    local ctrl = find_obj(p.control)
    local stat = find_obj(p.status)
    local action = lww_action(ctrl, stat)
    if action == 'publish' then
      publish_control(p.control, ctrl.value, zone.topic, p.param)
    elseif action == 'align' then
      align_control(p.control, stat.value)
    end
  end
end

if event then
  zb_light_sync_run()
end
