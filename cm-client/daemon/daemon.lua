-- Cottage Monitoring MQTT Client Daemon v1.1.2
-- Compact MQTT+cmd+meta+localbus + event batching. Always pump loop(); treat only numeric nonzero as error.
storage.set('cm_force_restart', nil)
storage.set('cm_started_ts', os.time())
storage.set('cm_heartbeat', os.time())
storage.set('cm_mqtt_connected', false)
storage.set('mqtt_connected', false)
storage.set('cm_last_error', '')
storage.set('cm_reconnect_count', 0)
storage.set('cm_boot', 'v112_start')

local config = require('config')
local json = require('json')
local mqtt = require('mosquitto')
local grp = grp
local lb = require('localbus').new(0.5)

local RECONNECT_MIN, RECONNECT_MAX, KEEPALIVE = 2, 60, 60
local CHUNK_SIZE, HEALTH_INTERVAL, HB_INTERVAL = 100, 60, 3

local function cfg(k, d) return config.get('cottage-monitoring', k, d) end
local function set_err(e) pcall(storage.set, 'cm_last_error', tostring(e or '')) end
local function loop_failed(rc)
  -- LM binding: success may be true/nil/0; only numeric ~= 0 is an error
  return type(rc) == 'number' and rc ~= 0
end
-- IMPORTANT: never use `ok and v or nil` — when v is false, Lua yields nil.
local function safe_getvalue(addr)
  local okv, v = pcall(grp.getvalue, addr)
  if okv then return v end
  return nil
end
-- Normalize common bool encodings from MQTT/JSON (do NOT map nil→false:
-- nil must stay nil so non-bool commands are not corrupted).
local function coerce_cmd_value(v)
  if v == 0 or v == '0' or v == 'false' or v == 'False' then return false end
  if v == 1 or v == '1' or v == 'true' or v == 'True' then return true end
  return v
end

local C = {
  house_id = cfg('house_id', '') or '',
  device_id = cfg('device_id', '') or '',
  env_mode = cfg('env_mode', 'prod') or 'prod',
  mqtt_host = cfg('mqtt_host', '') or '',
  mqtt_port = tonumber(cfg('mqtt_port', 8883)) or 8883,
  mqtt_username = cfg('mqtt_username', '') or '',
  mqtt_password = cfg('mqtt_password', '') or '',
  client_id = cfg('client_id', '') or '',
  buffer_size = tonumber(cfg('buffer_size', 1000)) or 1000,
  loop_sleep = tonumber(cfg('loop_sleep', 0.25)) or 0.25,
  throttle = tonumber(cfg('throttle', 20)) or 20,
  event_sleep = tonumber(cfg('event_sleep', 0.03)) or 0.03,
  batch_interval = tonumber(cfg('batch_interval', 1.5)) or 1.5,
  batch_max_size = tonumber(cfg('batch_max_size', 50)) or 50,
  mqtt_cafile = cfg('mqtt_cafile', '') or '',
}
do
  local tv = tostring(cfg('mqtt_tls_verify', '') or ''):lower()
  C.mqtt_tls_verify = (tv == '1' or tv == 'true' or tv == 'yes')
end
if C.client_id == '' or C.client_id == 'auto' then C.client_id = C.house_id .. '-' .. C.device_id end
C.base = ((C.env_mode == 'dev') and 'dev/' or '') .. 'cm/' .. C.house_id .. '/' .. C.device_id .. '/v1/'

local S = {
  client = nil, connected = false, seq = 0,
  reconnect_delay = RECONNECT_MIN,
  reconnect_count = 0,
  next_reconnect_ts = 0, started_ts = os.time(),
  last_health_pub_ts = 0, meta_sent = false,
  last_evt_ts = 0, evt_count = 0,
  last_hb_ts = 0, last_batch_flush_ts = os.time(),
}
local buffer = {}
local event_batch = {}

local function hb(force)
  local now = os.time()
  if not force and (now - S.last_hb_ts) < HB_INTERVAL then return end
  S.last_hb_ts = now
  pcall(storage.set, 'cm_heartbeat', now)
  pcall(storage.set, 'cm_mqtt_connected', S.connected and true or false)
  pcall(storage.set, 'mqtt_connected', S.connected and true or false)
end

local function do_pub(rel, payload, qos, retain)
  local full = C.base .. rel
  if S.connected and S.client then
    pcall(function() S.client:publish(full, payload, qos or 1, retain or false) end)
  elseif C.buffer_size > 0 then
    table.insert(buffer, { topic = full, payload = payload, qos = qos or 1, retain = retain or false })
    while #buffer > C.buffer_size do table.remove(buffer, 1) end
  end
end

-- Flush KNX event batch: events/batch + state/batch + retained state/ga (deduped by GA).
local function flush_batch()
  if #event_batch == 0 then return end
  local state_by_ga = {}
  local events_arr = {}
  for _, item in ipairs(event_batch) do
    table.insert(events_arr, item.evt)
    state_by_ga[item.ga_safe] = item.state
  end
  if #events_arr > 0 then
    do_pub('events/batch', json.encode({ events = events_arr }), 0, false)
  end
  local states_arr = {}
  for ga_safe, st in pairs(state_by_ga) do
    st.ga = ga_safe
    table.insert(states_arr, st)
  end
  if #states_arr > 0 then
    do_pub('state/batch', json.encode({ states = states_arr }), 1, false)
    local pub_cnt = 0
    for _, st in ipairs(states_arr) do
      do_pub('state/ga/' .. st.ga, json.encode({
        ts = st.ts, value = st.value, datatype = st.datatype or 0,
      }), 1, true)
      pub_cnt = pub_cnt + 1
      if pub_cnt >= 30 then pub_cnt = 0; os.sleep(0.02) end
    end
  end
  event_batch = {}
  S.last_batch_flush_ts = os.time()
end

local function publish_meta()
  local all = grp.all() or {}
  local sorted = {}
  for _, o in ipairs(all) do if o.address then table.insert(sorted, o) end end
  table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)
  local addrs = {}
  for _, o in ipairs(sorted) do table.insert(addrs, o.address or '') end
  local schema_hash = ''
  local ok, encdec = pcall(require, 'encdec')
  if ok and encdec and encdec.sha256 then schema_hash = 'sha256:' .. (encdec.sha256(json.encode(addrs)) or '') end
  local count, ts = #sorted, os.time()
  local function fmt(o)
    return { id = o.id, address = o.address or '', name = o.name or '', datatype = o.datatype or 0,
      units = o.units or '', tags = o.tagcache or o.tags or '', comment = o.comment or '' }
  end
  if count <= CHUNK_SIZE then
    local objects = {}
    for _, o in ipairs(sorted) do table.insert(objects, fmt(o)) end
    do_pub('meta/objects', json.encode({ ts = ts, schema_version = 1, schema_hash = schema_hash, count = count, objects = objects }), 1, true)
  else
    local total = math.ceil(count / CHUNK_SIZE)
    for n = 1, total do
      local a, b = (n - 1) * CHUNK_SIZE + 1, math.min(n * CHUNK_SIZE, count)
      local objects = {}
      for i = a, b do table.insert(objects, fmt(sorted[i])) end
      do_pub('meta/objects/chunk/' .. n, json.encode({ ts = ts, schema_version = 1, schema_hash = schema_hash, count = count, chunk_no = n, chunk_total = total, objects = objects }), 1, true)
      if n < total then os.sleep(0.02) end
    end
  end
  local pub_cnt = 0
  for _, o in ipairs(sorted) do
    local val = o.value
    if val == nil then val = safe_getvalue(o.address) end
    do_pub('state/ga/' .. (o.address or ''):gsub('/', '-'), json.encode({ ts = ts, value = val, datatype = o.datatype or 0 }), 1, true)
    pub_cnt = pub_cnt + 1
    if pub_cnt >= 30 then pub_cnt = 0; os.sleep(0.02) end
  end
end

local function setup_client()
  local client = mqtt.new(C.client_id, true)
  client:login_set(C.mqtt_username, C.mqtt_password)
  client:version_set(mqtt.PROTOCOL_V311)
  if C.mqtt_tls_verify then
    local ca = C.mqtt_cafile
    if ca == '' then
      ca = '/data/apps/store/data/cottage-monitoring/certs/isrg-root-x1.pem'
    end
    pcall(function() client:tls_set(ca) end)
    pcall(function() client:tls_insecure_set(false) end)
  else
    pcall(function() client:tls_insecure_set(true) end)
  end
  client:will_set(C.base .. 'status/offline', json.encode({ ts = os.time(), status = 'offline' }), 1, true)
  client:callback_set('ON_CONNECT', function()
    S.connected = true
    S.reconnect_delay = RECONNECT_MIN
    S.next_reconnect_ts = 0
    pcall(storage.set, 'cm_last_connect_ts', os.time())
    pcall(storage.set, 'cm_boot', 'ON_CONNECT')
    pcall(storage.set, 'cm_last_error', '')
    hb(true)
    pcall(function()
      client:publish(C.base .. 'status/online', json.encode({ ts = os.time(), status = 'online', device_id = C.device_id, version = '1.1.2' }), 1, true)
      client:subscribe(C.base .. 'cmd', 1)
      client:subscribe(C.base .. 'rpc/req/' .. C.client_id, 1)
      local flush_cnt = 0
      for _, e in ipairs(buffer) do
        client:publish(e.topic, e.payload, e.qos, e.retain)
        flush_cnt = flush_cnt + 1
        if flush_cnt >= 20 then flush_cnt = 0; os.sleep(0.02) end
      end
    end)
    buffer = {}
  end)
  client:callback_set('ON_DISCONNECT', function()
    S.connected = false
    pcall(storage.set, 'cm_last_disconnect_ts', os.time())
    pcall(storage.set, 'cm_boot', 'ON_DISCONNECT')
    hb(true)
  end)
  client:callback_set('ON_MESSAGE', function(mid, topic, payload)
    if topic:match('/cmd$') then
      local ok, msg = pcall(json.decode, payload)
      if not ok or not msg then return end
      local items = msg.items
      if not items and msg.ga ~= nil then items = { { ga = msg.ga, value = msg.value } } end
      if not items then return end
      local results = {}
      for _, it in ipairs(items) do
        local wval = coerce_cmd_value(it.value)
        local rok, rerr = pcall(grp.write, it.ga, wval)
        local row = { ga = it.ga, applied = (rok == true), value = wval }
        if not rok then row.error = tostring(rerr) end
        table.insert(results, row)
      end
      local rid = tostring(msg.request_id or '')
      local ack_rel = (rid ~= '') and ('cmd/ack/' .. rid) or 'cmd/ack'
      do_pub(ack_rel, json.encode({ request_id = msg.request_id, results = results, ts = os.time() }), 1, false)
    elseif topic:match('/rpc/req/') then
      local ok, msg = pcall(json.decode, payload)
      if not ok or not msg then return end
      local req_id = msg.request_id or ''
      local rpc_cid = topic:match('/rpc/req/([^/]+)')
      if rpc_cid then
        pcall(publish_meta)
        do_pub('rpc/resp/' .. rpc_cid .. '/' .. req_id, json.encode({ request_id = req_id, ok = true }), 0, false)
      end
    end
  end)
  return client
end


lb:sethandler('groupwrite', function(event)
  if C.throttle > 0 then
    local now = os.time()
    if now ~= S.last_evt_ts then S.last_evt_ts = now; S.evt_count = 0 end
    S.evt_count = S.evt_count + 1
    if S.evt_count > C.throttle then return end
  end
  local dst = event.dst or event.dstraw
  local obj = grp.find(dst)
  if not obj then return end
  local val = event.value
  if val == nil then val = safe_getvalue(dst) end
  local ts = os.time()
  S.seq = S.seq + 1
  local ga = obj.address or dst
  local ga_safe = tostring(ga):gsub('/', '-')
  local evt = {
    ts = ts, seq = S.seq, type = 'knx.groupwrite', ga = ga,
    id = obj.id, name = obj.name, datatype = obj.datatype or 0, value = val,
  }
  local state = { ts = ts, value = val, datatype = obj.datatype or 0 }
  if C.batch_interval > 0 then
    table.insert(event_batch, { evt = evt, ga_safe = ga_safe, state = state })
    if C.batch_max_size > 0 and #event_batch >= C.batch_max_size then
      flush_batch()
    end
  else
    do_pub('events', json.encode(evt), 0, false)
    do_pub('state/ga/' .. ga_safe, json.encode(state), 1, true)
  end
  if C.event_sleep > 0 then os.sleep(C.event_sleep) end
end)

S.client = setup_client()
hb(true)
pcall(function() S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE) end)

while true do
  local ok_iter, err_iter = pcall(function()
    if storage.get('cm_force_restart') then storage.set('cm_force_restart', nil); error('cm_force_restart') end
    hb(false)
    lb:step()
    if C.batch_interval > 0 and #event_batch > 0 then
      if (os.time() - S.last_batch_flush_ts) >= C.batch_interval then
        flush_batch()
      end
    end
    local lok, lrc = pcall(function() return S.client:loop(100) end)
    if not lok then
      S.connected = false
      set_err('loop_ex:' .. tostring(lrc))
      S.next_reconnect_ts = os.time() + S.reconnect_delay
    elseif loop_failed(lrc) then
      S.connected = false
      set_err('loop_rc=' .. tostring(lrc))
      S.next_reconnect_ts = os.time() + S.reconnect_delay
    end
    if not S.connected then
      local now = os.time()
      if now >= S.next_reconnect_ts then
        S.reconnect_count = S.reconnect_count + 1
        pcall(storage.set, 'cm_reconnect_count', S.reconnect_count)
        pcall(storage.set, 'cm_boot', 'reconnect#' .. S.reconnect_count)
        pcall(function()
          if S.client.reconnect then
            local rc = S.client:reconnect()
            if type(rc) == 'number' and rc ~= 0 then S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE) end
          else
            S.client:connect(C.mqtt_host, C.mqtt_port, KEEPALIVE)
          end
        end)
        S.next_reconnect_ts = now + S.reconnect_delay
        S.reconnect_delay = math.min(S.reconnect_delay * 2, RECONNECT_MAX)
      end
    end
    if S.connected and not S.meta_sent then S.meta_sent = true; pcall(publish_meta) end
    if S.connected and (os.time() - S.last_health_pub_ts) >= HEALTH_INTERVAL then
      do_pub('status/health', json.encode({
        ts = os.time(), status = 'online', version = '1.1.2',
        uptime = os.time() - S.started_ts, reconnects = S.reconnect_count, mqtt_connected = true,
      }), 1, true)
      S.last_health_pub_ts = os.time()
    end
  end)
  if not ok_iter then
    set_err(tostring(err_iter))
    if tostring(err_iter):find('cm_force_restart') then error(err_iter) end
  end
  os.sleep(C.loop_sleep)
end
