--[[
  zigbee_send fragment: ceiling light param writes (no MQTT password).

  Merge into live zigbee_send on LM (full ops: Task 5 / quickstart):
    1. Scripting → Event → existing zigbee_send (tag filter zigbee_send).
       Control GAs 36/1/1–9 already have tag zigbee_send; this script fires on them.
    2. Paste helpers + ceiling_light_set below the existing device map.
       Keep the live MQTT login/password as-is — do not copy credentials into git.
    3. In the event handler, resolve dst = event.dst or event.dstraw and value =
       event.getvalue(), then call zigbee_send_ceiling_maybe(dst, value, publish).
       If it returns true, return (ceiling GA consumed: published or skipped by guard).
    4. Wire publish to the existing client, e.g. mclient:publish(topic, payload, 0, false).
    5. Save. Do not FTP this file as a replacement for zigbee_send.

  Tima write is GROUP zigbee2mqtt/Ceiling_lamps_tima/set (not tima1 + tima2).
]]

require('json')

-- Lua 5.1: round via floor(x+0.5). Inverse of mqtt_listen Bri254toPct.
local function PctToBri254(pct)
  local n = tonumber(pct)
  if n == nil then return nil end
  local bri = math.floor(n * 2.54 + 0.5)
  if bri < 0 then bri = 0 end
  if bri > 254 then bri = 254 end
  return bri
end

-- uint32 0xRRGGBB → {r,g,b} 0–255. Inverse of mqtt_listen ColorToUint32.
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

local function payload_brightness(value)
  local bri = PctToBri254(value)
  if bri == nil then return nil end
  return { brightness = bri }
end

local function payload_color_temp(value)
  local n = tonumber(value)
  if n == nil then return nil end
  return { color_temp = n }
end

local function payload_rgb(value)
  local color = Uint32ToColor(value)
  if color == nil then return nil end
  return { color = color }
end

local TOPIC_TIMA = 'zigbee2mqtt/Ceiling_lamps_tima/set'
local TOPIC_HALL = 'zigbee2mqtt/Ceiling_lamp_hall_2_floor/set'
local TOPIC_OFFICE = 'zigbee2mqtt/Ceiling_lamp_office/set'

-- control GA → z2m /set topic + payload builder
local ceiling_light_set = {
  -- Тима (group id 1: tima1+tima2). One publish, not two devices.
  ['36/1/1'] = { topic = TOPIC_TIMA, param = 'brightness', build_payload = payload_brightness },
  ['36/1/2'] = { topic = TOPIC_TIMA, param = 'color_temp', build_payload = payload_color_temp },
  ['36/1/3'] = { topic = TOPIC_TIMA, param = 'rgb', build_payload = payload_rgb },
  -- Холл
  ['36/1/4'] = { topic = TOPIC_HALL, param = 'brightness', build_payload = payload_brightness },
  ['36/1/5'] = { topic = TOPIC_HALL, param = 'color_temp', build_payload = payload_color_temp },
  ['36/1/6'] = { topic = TOPIC_HALL, param = 'rgb', build_payload = payload_rgb },
  -- Кабинет
  ['36/1/7'] = { topic = TOPIC_OFFICE, param = 'brightness', build_payload = payload_brightness },
  ['36/1/8'] = { topic = TOPIC_OFFICE, param = 'color_temp', build_payload = payload_color_temp },
  ['36/1/9'] = { topic = TOPIC_OFFICE, param = 'rgb', build_payload = payload_rgb },
}

-- zb_light_sync sets this while grp.update(control ← status) so this path
-- does not echo the align write back to z2m. storage.get is the LM API;
-- storage.zb_light_from_sync_align is the same flag if the live script uses fields.
local function zb_light_from_sync_align()
  local v
  if storage and storage.get then
    v = storage.get('zb_light_from_sync_align')
  end
  if v == nil and storage then
    v = storage.zb_light_from_sync_align
  end
  return v == true or v == 1 or v == '1' or v == 'true'
end

-- Returns true if dst is a ceiling control GA (handled here: publish or guard-skip).
-- publish_fn(topic, payload_json) is the live zigbee_send MQTT publish.
function zigbee_send_ceiling_maybe(dst, value, publish_fn)
  local entry = ceiling_light_set[dst]
  if not entry then return false end
  if zb_light_from_sync_align() then
    return true
  end
  local payload = entry.build_payload(value)
  if payload == nil or not publish_fn then
    return true
  end
  publish_fn(entry.topic, json.encode(payload))
  return true
end

--[[
  Hook into existing zigbee_send event body (names of mclient / publish may differ):

    local dst = event.dst or event.dstraw
    local value = event.getvalue()
    if zigbee_send_ceiling_maybe(dst, value, function(topic, payload)
      mclient:publish(topic, payload, 0, false)
    end) then
      return
    end
    -- ... existing FloorLamp / teapot / T-Lamp maps ...
]]
