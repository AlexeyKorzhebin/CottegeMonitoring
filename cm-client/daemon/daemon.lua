-- Cottage Monitoring MQTT Client Daemon
-- Connects to MQTT, publishes telemetry (events, state, meta), executes commands, handles RPC

local config = require('config')
local json = require('json')
local grp = grp

local CHUNK_SIZE = 100

local function get_cfg(key, default)
  return config.get('cottage-monitoring', key, default)
end

local debug_en = (get_cfg('debug', 'false') == 'true' or get_cfg('debug', false) == true)

local function dlog(...)
  if debug_en then log(...) end
end

local function dalert(fmt, ...)
  if debug_en then alert(fmt, ...) end
end

-- Config
local house_id = get_cfg('house_id', '') or ''
local device_id = get_cfg('device_id', '') or ''
local env_mode = get_cfg('env_mode', 'prod') or 'prod'
local mqtt_host = get_cfg('mqtt_host', '') or ''
local mqtt_port = tonumber(get_cfg('mqtt_port', 8883)) or 8883
local mqtt_username = get_cfg('mqtt_username', '') or ''
local mqtt_password = get_cfg('mqtt_password', '') or ''
local client_id = get_cfg('client_id', '') or ''
local buffer_size = tonumber(get_cfg('buffer_size', 1000)) or 1000
local snapshot_interval = tonumber(get_cfg('snapshot_interval', 0)) or 0
local throttle = tonumber(get_cfg('throttle', 0)) or 0

if client_id == '' or client_id == 'auto' then
  client_id = (house_id or '') .. '-' .. (device_id or '')
end

-- Topic prefix: dev/ for dev mode, empty for prod
local base_topic = ((env_mode == 'dev') and 'dev/' or '') .. 'cm/' .. house_id .. '/' .. device_id .. '/v1/'

-- Buffer (RAM) when MQTT disconnected
local buffer = {}

local function buf_add(entry)
  if buffer_size <= 0 then return end
  table.insert(buffer, entry)
  while #buffer > buffer_size do
    table.remove(buffer, 1)
  end
end

-- MQTT client
local mqtt = require('mosquitto')
local mqtt_client = nil
local seq = 0

local function next_seq()
  seq = seq + 1
  return seq
end

local function mqtt_publish(topic, payload, qos, retain)
  if not mqtt_client then return false end
  local ok, err = pcall(function()
    mqtt_client:publish(topic, payload, qos or 1, retain or false)
  end)
  if not ok then
    dlog('publish error:', err)
    return false
  end
  return true
end

local mqtt_connected_flag = false
local last_snapshot_ts = 0
local last_evt_ts = 0
local evt_count_this_sec = 0

local function do_publish(topic, payload, qos, retain)
  local full_topic = base_topic .. topic
  if mqtt_client and mqtt_connected_flag then
    return mqtt_publish(full_topic, payload, qos, retain)
  else
    buf_add({ topic = full_topic, payload = payload, qos = qos or 1, retain = retain or false })
    return false
  end
end

-- Format meta object (no value)
local function format_meta_obj(o)
  return {
    id = o.id,
    address = o.address or '',
    name = o.name or '',
    datatype = o.datatype or 0,
    units = o.units or '',
    tags = o.tagcache or o.tags or '',
    comment = o.comment or ''
  }
end

local function get_schema_hash(sorted_objs)
  local addrs = {}
  for _, o in ipairs(sorted_objs) do
    table.insert(addrs, o.address or '')
  end
  local ok, encdec = pcall(require, 'encdec')
  if ok and encdec and encdec.sha256 then
    return 'sha256:' .. (encdec.sha256(json.encode(addrs)) or '')
  end
  return ''
end

local function publish_meta_and_snapshot()
  local all = grp.all() or {}
  local sorted = {}
  for _, o in ipairs(all) do
    if o.address then table.insert(sorted, o) end
  end
  table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)

  local schema_hash = get_schema_hash(sorted)
  local count = #sorted
  local ts = os.time()

  if count <= CHUNK_SIZE then
    local objects = {}
    for _, o in ipairs(sorted) do
      table.insert(objects, format_meta_obj(o))
    end
    local payload = json.encode({
      ts = ts,
      schema_version = 1,
      schema_hash = schema_hash,
      count = count,
      objects = objects
    })
    do_publish('meta/objects', payload, 1, true)
  else
    local chunk_total = math.ceil(count / CHUNK_SIZE)
    for chunk_no = 1, chunk_total do
      local start = (chunk_no - 1) * CHUNK_SIZE + 1
      local finish = math.min(start + CHUNK_SIZE - 1, count)
      local objects = {}
      for i = start, finish do
        table.insert(objects, format_meta_obj(sorted[i]))
      end
      local payload = json.encode({
        ts = ts,
        schema_version = 1,
        schema_hash = schema_hash,
        count = count,
        chunk_no = chunk_no,
        chunk_total = chunk_total,
        objects = objects
      })
      do_publish('meta/objects/chunk/' .. chunk_no, payload, 1, true)
    end
  end

  -- Snapshot: state for each object
  for _, o in ipairs(sorted) do
    local val = o.value
    if val == nil then
      local ok, v = pcall(grp.getvalue, o.address)
      val = ok and v or nil
    end
    local state_payload = json.encode({
      ts = ts,
      value = val,
      datatype = o.datatype or 0
    })
    local ga_safe = (o.address or ''):gsub('/', '-')
    do_publish('state/ga/' .. ga_safe, state_payload, 1, true)
  end
end

local function publish_snapshot_only()
  local all = grp.all() or {}
  local sorted = {}
  for _, o in ipairs(all) do
    if o.address then table.insert(sorted, o) end
  end
  table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)
  local ts = os.time()
  for _, o in ipairs(sorted) do
    local val = o.value
    if val == nil then
      local ok, v = pcall(grp.getvalue, o.address)
      val = ok and v or nil
    end
    local state_payload = json.encode({ ts = ts, value = val, datatype = o.datatype or 0 })
    local ga_safe = (o.address or ''):gsub('/', '-')
    do_publish('state/ga/' .. ga_safe, state_payload, 1, true)
  end
end

-- Localbus
local lb = require('localbus').new(0.5)

lb:sethandler('groupwrite', function(event)
  if throttle > 0 then
    local now = os.time()
    if now ~= last_evt_ts then last_evt_ts = now; evt_count_this_sec = 0 end
    evt_count_this_sec = evt_count_this_sec + 1
    if evt_count_this_sec > throttle then return end
  end
  local dst = event.dst or event.dstraw
  local obj = grp.find(dst)
  if not obj then return end
  local val = event.value
  if val == nil and event.datahex then
    local ok_dt, knxdt = pcall(require, 'knxdatatype')
    local ok_d, dt = pcall(require, 'dt')
    if ok_dt and knxdt and ok_d and dt then
      local dtype = obj.datatype
      if dtype == 1 or dtype == 1001 then dtype = dt.bool end
      local ok_dec, decoded = pcall(knxdt.decode, event.datahex, dtype)
      if ok_dec and decoded ~= nil then val = decoded end
    end
  end
  if val == nil then val = obj.value end
  local ts = os.time()
  local evt_payload = json.encode({
    ts = ts,
    seq = next_seq(),
    type = 'knx.groupwrite',
    ga = obj.address or tostring(dst),
    id = obj.id,
    name = obj.name or '',
    datatype = obj.datatype or 0,
    value = val
  })
  do_publish('events', evt_payload, 0, false)
  local state_payload = json.encode({
    ts = ts,
    value = val,
    datatype = obj.datatype or 0
  })
  local ga_safe = (obj.address or dst or ''):gsub('/', '-')
  do_publish('state/ga/' .. ga_safe, state_payload, 1, true)
end)

-- MQTT setup
local cid = client_id
if cid == '' or cid == '-' then cid = 'cm-' .. house_id .. '-' .. device_id end

mqtt_client = mqtt.new(cid, true)
mqtt_client:login_set(mqtt_username, mqtt_password)
mqtt_client:version_set(mqtt.PROTOCOL_V311)
mqtt_client:tls_insecure_set(true)

local lwt_payload = json.encode({ ts = os.time(), status = 'offline' })
mqtt_client:will_set(base_topic .. 'status/offline', lwt_payload, 1, true)

mqtt_client:callback_set('ON_CONNECT', function()
  mqtt_connected_flag = true
  storage.set('mqtt_connected', true)
  dlog('MQTT connected')
  mqtt_publish(base_topic .. 'status/online', json.encode({ ts = os.time(), status = 'online', version = '1.0.0' }), 1, true)
  mqtt_client:subscribe(base_topic .. 'cmd', 1)
  mqtt_client:subscribe(base_topic .. 'rpc/req/' .. cid, 1)
  -- Flush buffer
  while #buffer > 0 do
    local e = table.remove(buffer, 1)
    mqtt_client:publish(e.topic, e.payload, e.qos, e.retain)
  end
  publish_meta_and_snapshot()
end)

local reconnect_scheduled = false
mqtt_client:callback_set('ON_DISCONNECT', function()
  mqtt_connected_flag = false
  storage.set('mqtt_connected', false)
  dlog('MQTT disconnected')
  reconnect_scheduled = true
end)

mqtt_client:callback_set('ON_MESSAGE', function(mid, topic, payload, qos, retain, props)
  if not payload or payload == '' then return end
  local ok, data = pcall(json.decode, payload)
  if not ok or not data then
    dlog('invalid JSON in message')
    return
  end
  -- cmd topic
  if topic:match('/cmd$') then
    local req_id = data.request_id
    if not req_id then return end
    if data.ga and data.value ~= nil then
      log('CM cmd received: ga=' .. tostring(data.ga) .. ' value=' .. tostring(data.value) .. ' request_id=' .. tostring(req_id))
    elseif data.items then
      log('CM cmd received (batch): items=' .. #data.items .. ' request_id=' .. tostring(req_id))
      for _, it in ipairs(data.items) do
        log('CM cmd received (batch): ga=' .. tostring(it.ga) .. ' value=' .. tostring(it.value))
      end
    else
      log('CM cmd received: (invalid) request_id=' .. tostring(req_id))
    end
    local results = {}
    local status = 'ok'
    if data.ga and data.value ~= nil then
      local obj = grp.find(data.ga)
      if not obj then
        table.insert(results, { ga = data.ga, applied = false, error = 'unknown GA' })
        status = 'error'
      else
        local ok_w, err = pcall(grp.write, data.ga, data.value)
        local r = { ga = data.ga, applied = ok_w }
        if not ok_w then r.error = tostring(err) end
        table.insert(results, r)
        if not ok_w then status = 'error' end
      end
    elseif data.items then
      for _, it in ipairs(data.items) do
        local obj = grp.find(it.ga)
        if not obj then
          table.insert(results, { ga = it.ga, applied = false, error = 'unknown GA' })
          status = 'error'
        else
          local ok_w, err = pcall(grp.write, it.ga, it.value)
          local r = { ga = it.ga, applied = ok_w }
          if not ok_w then r.error = tostring(err) end
          table.insert(results, r)
          if not ok_w then status = 'error' end
        end
      end
    else
      status = 'error'
      table.insert(results, { ga = nil, applied = false, error = 'missing ga+value or items' })
    end
    local ok_enc, ack = pcall(json.encode, {
      ts = os.time(),
      request_id = tostring(req_id),
      status = status,
      results = results
    })
    if not ok_enc or not ack then
      dlog('cmd ack json.encode failed')
      return
    end
    -- QoS 1 for ack: at-least-once delivery to broker (QoS 0 can lose packets)
    local ok_pub = do_publish('cmd/ack/' .. tostring(req_id), ack, 1, false)
    if not ok_pub then
      dlog('cmd ack publish failed ', tostring(req_id))
    end
  end
  -- rpc/req
  if topic:match('/rpc/req/') then
    local method = data.method
    local req_id = data.request_id or 'unknown'
    local client_id_rpc = topic:match('/rpc/req/([^/]+)')
    if not client_id_rpc then return end
    if method == 'meta' then
      local all = grp.all() or {}
      local sorted = {}
      for _, o in ipairs(all) do
        if o.address then table.insert(sorted, o) end
      end
      table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)
      local schema_hash = get_schema_hash(sorted)
      local objects = {}
      for _, o in ipairs(sorted) do
        table.insert(objects, format_meta_obj(o))
      end
      local resp = json.encode({
        request_id = req_id,
        ok = true,
        chunk_no = 1,
        chunk_total = 1,
        result = { ts = os.time(), schema_hash = schema_hash, count = #objects, objects = objects }
      })
      do_publish('rpc/resp/' .. client_id_rpc .. '/' .. req_id, resp, 0, false)
    elseif method == 'snapshot' then
      local all = grp.all() or {}
      local sorted = {}
      for _, o in ipairs(all) do
        if o.address then table.insert(sorted, o) end
      end
      table.sort(sorted, function(a, b) return (a.address or '') < (b.address or '') end)
      local states = {}
      for _, o in ipairs(sorted) do
        local val = o.value
        if val == nil then
          local ok_v, v = pcall(grp.getvalue, o.address)
          val = ok_v and v or nil
        end
        table.insert(states, { ga = o.address, value = val, datatype = o.datatype or 0 })
      end
      local resp = json.encode({
        request_id = req_id,
        ok = true,
        chunk_no = 1,
        chunk_total = 1,
        result = { ts = os.time(), states = states }
      })
      do_publish('rpc/resp/' .. client_id_rpc .. '/' .. req_id, resp, 0, false)
    end
  end
end)

-- Main loop
storage.set('mqtt_connected', false)

if mqtt_host and mqtt_host ~= '' then
  mqtt_client:connect(mqtt_host, mqtt_port, 60)
end

dlog('Cottage Monitoring daemon starting')

while true do
  lb:step()
  if mqtt_client then
    mqtt_client:loop(100)
    if reconnect_scheduled and not mqtt_connected_flag then
      reconnect_scheduled = false
      os.sleep(2)
      if mqtt_host and mqtt_host ~= '' then
        mqtt_client:connect(mqtt_host, mqtt_port, 60)
      end
    end
  end
  if storage.get('force_export') then
    storage.set('force_export', nil)
    publish_meta_and_snapshot()
  end
  if snapshot_interval > 0 and mqtt_connected_flag then
    local now = os.time()
    if now - last_snapshot_ts >= snapshot_interval then
      last_snapshot_ts = now
      publish_snapshot_only()
    end
  end
  os.sleep(0.05)
end
